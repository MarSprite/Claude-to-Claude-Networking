"""HTTPS server with TLS, authentication, and LAN validation."""

import ssl
from typing import Optional

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport

from .config import Settings
from .security import TokenAuthenticator, LANValidator


class LANValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate connections come from LAN IPs only."""

    def __init__(self, app, lan_validator: LANValidator):
        super().__init__(app)
        self.lan_validator = lan_validator

    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Allow health check without validation
        if request.url.path == "/health":
            return await call_next(request)

        # Validate LAN IP
        is_valid, message = self.lan_validator.validate_connection(client_ip)

        if not is_valid:
            return JSONResponse(
                {"error": "Forbidden", "detail": message},
                status_code=403
            )

        return await call_next(request)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate authentication tokens."""

    def __init__(self, app, authenticator: TokenAuthenticator):
        super().__init__(app)
        self.authenticator = authenticator

    async def dispatch(self, request: Request, call_next):
        # Allow health check without auth
        if request.url.path == "/health":
            return await call_next(request)

        # Get authorization header
        auth_header = request.headers.get("Authorization")

        is_valid, message = self.authenticator.validate_authorization_header(
            auth_header
        )

        if not is_valid:
            return JSONResponse(
                {"error": "Unauthorized", "detail": message},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"}
            )

        return await call_next(request)


def create_ssl_context(settings: Settings) -> ssl.SSLContext:
    """Create SSL context for HTTPS server.

    Args:
        settings: Server settings with certificate paths.

    Returns:
        Configured SSL context.
    """
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(
        certfile=str(settings.cert_path),
        keyfile=str(settings.key_path)
    )
    # Set secure defaults
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    ssl_context.set_ciphers("ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20:DHE+CHACHA20")

    return ssl_context


def create_app(
    mcp: FastMCP,
    authenticator: TokenAuthenticator,
    lan_validator: LANValidator
) -> Starlette:
    """Create the Starlette ASGI application.

    Args:
        mcp: The FastMCP server instance.
        authenticator: Token authenticator.
        lan_validator: LAN IP validator.

    Returns:
        Configured Starlette app.
    """
    # Create SSE transport for MCP
    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        """Handle SSE connection for MCP."""
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send
        ) as (read_stream, write_stream):
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options()
            )
        return Response()

    async def handle_messages(request: Request) -> Response:
        """Handle POST messages for MCP."""
        return await sse_transport.handle_post_message(
            request.scope,
            request.receive,
            request._send
        )

    async def health_check(request: Request) -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse({
            "status": "healthy",
            "service": "c2c-bridge",
        })

    async def server_info(request: Request) -> JSONResponse:
        """Server info endpoint."""
        return JSONResponse({
            "service": "c2c-bridge",
            "version": "0.1.0",
            "endpoints": {
                "sse": "/sse",
                "messages": "/messages/",
                "health": "/health",
            },
        })

    routes = [
        Route("/health", health_check, methods=["GET"]),
        Route("/", server_info, methods=["GET"]),
        Route("/sse", handle_sse, methods=["GET"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ]

    middleware = [
        Middleware(LANValidationMiddleware, lan_validator=lan_validator),
        Middleware(AuthenticationMiddleware, authenticator=authenticator),
    ]

    app = Starlette(
        routes=routes,
        middleware=middleware,
        on_startup=[],
        on_shutdown=[],
    )

    return app


async def run_http_server(
    mcp: FastMCP,
    settings: Settings,
    authenticator: TokenAuthenticator,
    lan_validator: LANValidator,
) -> None:
    """Run the HTTPS server.

    Args:
        mcp: The FastMCP server instance.
        settings: Server settings.
        authenticator: Token authenticator.
        lan_validator: LAN IP validator.
    """
    app = create_app(mcp, authenticator, lan_validator)
    ssl_context = create_ssl_context(settings)

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        ssl_keyfile=str(settings.key_path),
        ssl_certfile=str(settings.cert_path),
        log_level="info",
        access_log=True,
    )

    server = uvicorn.Server(config)
    await server.serve()
