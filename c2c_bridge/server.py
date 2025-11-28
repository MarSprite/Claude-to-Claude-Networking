"""Main MCP server entry point for C2C Bridge."""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import Settings, ServerMode
from .security import TLSManager, TokenAuthenticator, LANValidator
from .broker import MessageBroker, StateManager, TaskQueue, SessionManager
from .tools import (
    register_messaging_tools,
    register_discovery_tools,
    register_context_tools,
    register_task_tools,
    register_session_tools,
)


class C2CServer:
    """Claude-to-Claude communication bridge server."""

    def __init__(self, settings: Settings):
        """Initialize the C2C server.

        Args:
            settings: Server configuration settings.
        """
        self.settings = settings
        self.settings.ensure_directories()

        # Initialize MCP server
        self.mcp = FastMCP(
            "C2C-Bridge",
            instructions=f"C2C Bridge instance '{settings.instance_name}' - enables communication between Claude Code instances."
        )

        # Initialize components
        self.broker = MessageBroker()
        self.state_manager = StateManager(settings.state_file)
        self.task_queue = TaskQueue()
        self.tls_manager = TLSManager(settings.credentials_dir)
        self.authenticator = TokenAuthenticator(settings.token_path)
        self.lan_validator = LANValidator()

        # Session manager for idle timeout (default 15 min, configurable)
        idle_timeout = settings.auto_shutdown_idle if settings.auto_shutdown_idle > 0 else 900
        self.session_manager = SessionManager(
            idle_timeout_seconds=idle_timeout,
            on_session_end=self._handle_session_end,
        )
        self._shutdown_requested = False

        # Register all tools
        self._register_tools()

    def _get_instance_name(self) -> str:
        """Get the current instance name."""
        return self.settings.instance_name

    def _handle_session_end(self) -> None:
        """Handle session end callback."""
        self._shutdown_requested = True

    def _register_tools(self) -> None:
        """Register all MCP tools."""
        register_messaging_tools(
            self.mcp,
            self.broker,
            self._get_instance_name
        )
        register_discovery_tools(
            self.mcp,
            self.broker,
            self.state_manager,
            self._get_instance_name
        )
        register_context_tools(
            self.mcp,
            self.state_manager,
            self.broker,
            self._get_instance_name
        )
        register_task_tools(
            self.mcp,
            self.task_queue,
            self.broker,
            self._get_instance_name
        )
        register_session_tools(
            self.mcp,
            self.session_manager,
            self._get_instance_name
        )

    async def _ensure_credentials(self) -> tuple[str, Optional[str]]:
        """Ensure TLS certificates and auth token exist.

        Returns:
            Tuple of (token, None) or (token, error_message).
        """
        # Generate TLS certificate if needed
        if not self.tls_manager.certificates_exist():
            print("\n=== Generating TLS Certificates ===")
            ips = self.tls_manager.get_local_ips()
            print(f"Local IPs detected: {', '.join(ips)}")

            cert_path, key_path = self.tls_manager.generate_self_signed_cert(
                ip_addresses=ips
            )
            print(f"Certificate: {cert_path}")
            print(f"Private key: {key_path}")
            print("===================================\n")

        # Generate auth token if needed
        if not self.authenticator.token_exists():
            token = self.authenticator.generate_token()
            print("\n=== Authentication Token Generated ===")
            print(f"Token: {token}")
            print(f"Saved to: {self.settings.token_path}")
            print("")
            print("IMPORTANT: Copy the credentials/ folder to")
            print("the connecting machine and use this token.")
            print("======================================\n")
        else:
            token = self.authenticator.get_token()

        return token, None

    async def _register_self(self) -> None:
        """Register this instance with the broker."""
        await self.broker.register_instance(
            self.settings.instance_name,
            {"mode": self.settings.mode}
        )
        await self.state_manager.update_instance_state(
            self.settings.instance_name,
            status="online",
            extra={"mode": self.settings.mode}
        )

    def _print_server_info(self, token: str, idle_timeout: int) -> None:
        """Print server connection information."""
        ips = self.tls_manager.get_local_ips()

        print("\n" + "=" * 50)
        print("C2C Bridge - Collaboration Session Active")
        print("=" * 50)
        print(f"Instance Name: {self.settings.instance_name}")
        print(f"Mode: {self.settings.mode}")
        print(f"Port: {self.settings.port}")
        print(f"Idle Timeout: {idle_timeout // 60} minutes")
        print("")
        print("Connection URLs:")
        for ip in ips:
            if ip != "127.0.0.1":
                print(f"  https://{ip}:{self.settings.port}/sse")
        print("")
        print(f"Auth Token: {token}")
        print("")
        print("Session will auto-shutdown after idle timeout.")
        print("Remote can extend or end session via MCP tools.")
        print("=" * 50)
        print("\n[Session active - waiting for connections...]\n")

    async def run_stdio(self) -> None:
        """Run as stdio MCP server (local mode)."""
        await self._register_self()
        print(f"C2C Bridge '{self.settings.instance_name}' running in stdio mode...")
        await self.mcp.run(transport="stdio")

    async def run_server(self) -> None:
        """Run as HTTPS server (server mode)."""
        token, error = await self._ensure_credentials()
        if error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)

        await self._register_self()

        # Start session
        idle_timeout = self.settings.auto_shutdown_idle if self.settings.auto_shutdown_idle > 0 else 900
        await self.session_manager.start_session()
        self._print_server_info(token, idle_timeout)

        # Import and run HTTP server
        from .http_server import run_http_server

        # Run server with session monitoring
        server_task = asyncio.create_task(
            run_http_server(
                mcp=self.mcp,
                settings=self.settings,
                authenticator=self.authenticator,
                lan_validator=self.lan_validator,
                session_manager=self.session_manager,
            )
        )

        shutdown_task = asyncio.create_task(
            self.session_manager.wait_for_shutdown()
        )

        # Wait for either server error or session end
        done, pending = await asyncio.wait(
            [server_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Print session end message
        status = await self.session_manager.get_status()
        print("\n" + "=" * 50)
        print("Session Ended")
        print("=" * 50)
        if "end_reason" in status:
            reason = status.get("end_reason", "unknown")
            if reason == "idle_timeout":
                print("Reason: Idle timeout reached")
            elif reason == "remote_request":
                print("Reason: Ended by remote instance")
            else:
                print(f"Reason: {reason}")
        print(f"Tasks completed: {status.get('tasks_completed', 0)}")
        print(f"Messages sent: {status.get('messages_sent', 0)}")
        print("=" * 50 + "\n")

    async def run_hybrid(self) -> None:
        """Run as both stdio and HTTPS server."""
        token, error = await self._ensure_credentials()
        if error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)

        await self._register_self()

        # Start session
        idle_timeout = self.settings.auto_shutdown_idle if self.settings.auto_shutdown_idle > 0 else 900
        await self.session_manager.start_session()
        self._print_server_info(token, idle_timeout)

        # Import HTTP server
        from .http_server import run_http_server

        # Run both concurrently with session monitoring
        await asyncio.gather(
            self.mcp.run(transport="stdio"),
            run_http_server(
                mcp=self.mcp,
                settings=self.settings,
                authenticator=self.authenticator,
                lan_validator=self.lan_validator,
                session_manager=self.session_manager,
            ),
        )

    async def run_client(self) -> None:
        """Run as client connecting to remote server."""
        if not self.settings.server_url:
            print("Error: --server-url required in client mode", file=sys.stderr)
            sys.exit(1)

        token = self.settings.token or self.authenticator.get_token()
        if not token:
            print("Error: --token required in client mode", file=sys.stderr)
            sys.exit(1)

        await self._register_self()

        print(f"\nC2C Bridge '{self.settings.instance_name}' connecting to {self.settings.server_url}...")
        print("Note: In client mode, use the remote server's MCP tools.")
        print("Configure your Claude Code to connect directly to the server URL.\n")

        # In client mode, we still run stdio for local Claude Code
        # The actual connection to remote is handled by Claude Code's MCP config
        await self.mcp.run(transport="stdio")

    async def run(self) -> None:
        """Run the server based on configured mode."""
        mode = ServerMode(self.settings.mode)

        if mode == ServerMode.SERVER:
            await self.run_server()
        elif mode == ServerMode.CLIENT:
            await self.run_client()
        elif mode == ServerMode.HYBRID:
            await self.run_hybrid()
        else:
            await self.run_stdio()


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="C2C Bridge - Claude-to-Claude Communication Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Start as server:
    python -m c2c_bridge.server --name main-dev --mode server

  Connect as client:
    python -m c2c_bridge.server --name testing --mode client \\
        --server-url https://192.168.1.100:8443 --token <token>

  Run in hybrid mode (local + remote):
    python -m c2c_bridge.server --name workstation --mode hybrid
        """,
    )

    parser.add_argument(
        "--name", "-n",
        required=True,
        help="Instance name (required, e.g., 'main-dev', 'testing')"
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["server", "client", "hybrid"],
        default="server",
        help="Server mode: server, client, or hybrid (default: server)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8443,
        help="HTTPS server port (default: 8443)"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--server-url", "-s",
        help="Remote server URL (required for client mode)"
    )

    parser.add_argument(
        "--token", "-t",
        help="Authentication token (for client mode)"
    )

    parser.add_argument(
        "--credentials-dir",
        type=Path,
        help="Directory for credentials (default: ./credentials)"
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Directory for runtime data (default: ./data)"
    )

    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL verification (for self-signed certs)"
    )

    parser.add_argument(
        "--auto-shutdown",
        type=int,
        default=0,
        help="Auto-shutdown after N seconds idle (0=disabled)"
    )

    parser.add_argument(
        "--generate-creds",
        action="store_true",
        help="Generate credentials and exit"
    )

    return parser


def main() -> None:
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Create settings from arguments
    settings = Settings.from_args(args)

    # Create server
    server = C2CServer(settings)

    # Handle credential generation
    if args.generate_creds:
        asyncio.run(server._ensure_credentials())
        cert_info = server.tls_manager.get_certificate_info()
        print("\nCertificate Info:")
        for key, value in cert_info.items():
            print(f"  {key}: {value}")
        return

    # Run server
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
