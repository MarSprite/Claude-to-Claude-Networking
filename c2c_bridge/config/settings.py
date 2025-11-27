"""Configuration management for C2C Bridge."""

import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ServerMode(str, Enum):
    """Server operation mode."""
    SERVER = "server"  # Run as server (accept connections)
    CLIENT = "client"  # Run as client (connect to server)
    HYBRID = "hybrid"  # Run as both (local stdio + remote HTTP server)


class Settings(BaseModel):
    """Configuration settings for C2C Bridge."""

    # Instance identification
    instance_name: str = Field(
        ...,
        description="User-specified name for this instance"
    )

    # Server mode
    mode: ServerMode = Field(
        default=ServerMode.SERVER,
        description="Server operation mode"
    )

    # Network settings
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind to (server mode)"
    )
    port: int = Field(
        default=8443,
        description="Port for HTTPS server"
    )
    server_url: Optional[str] = Field(
        default=None,
        description="URL of remote server (client mode)"
    )

    # Paths
    base_dir: Path = Field(
        default_factory=lambda: Path.cwd(),
        description="Base directory for the project"
    )
    credentials_dir: Optional[Path] = Field(
        default=None,
        description="Directory for TLS certificates and tokens"
    )
    data_dir: Optional[Path] = Field(
        default=None,
        description="Directory for runtime data"
    )

    # Security
    token: Optional[str] = Field(
        default=None,
        description="Authentication token (client mode)"
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates (disable for self-signed)"
    )

    # Server behavior
    auto_shutdown_idle: int = Field(
        default=0,
        description="Auto-shutdown after N seconds idle (0=disabled)"
    )

    class Config:
        use_enum_values = True

    def model_post_init(self, __context) -> None:
        """Set default paths after initialization."""
        if self.credentials_dir is None:
            self.credentials_dir = self.base_dir / "credentials"
        if self.data_dir is None:
            self.data_dir = self.base_dir / "data"

    @property
    def cert_path(self) -> Path:
        """Path to TLS certificate."""
        return self.credentials_dir / "server.crt"

    @property
    def key_path(self) -> Path:
        """Path to TLS private key."""
        return self.credentials_dir / "server.key"

    @property
    def token_path(self) -> Path:
        """Path to authentication token file."""
        return self.credentials_dir / "auth_token.txt"

    @property
    def state_file(self) -> Path:
        """Path to persistent state file."""
        return self.data_dir / "state.json"

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.credentials_dir.chmod(0o700)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, instance_name: str, **overrides) -> "Settings":
        """Create settings from environment variables.

        Args:
            instance_name: Required instance name.
            **overrides: Additional settings to override.

        Returns:
            Settings instance.
        """
        env_settings = {
            "instance_name": instance_name,
            "mode": os.getenv("C2C_MODE", "server"),
            "host": os.getenv("C2C_HOST", "0.0.0.0"),
            "port": int(os.getenv("C2C_PORT", "8443")),
            "server_url": os.getenv("C2C_SERVER_URL"),
            "token": os.getenv("C2C_TOKEN"),
            "auto_shutdown_idle": int(os.getenv("C2C_AUTO_SHUTDOWN", "0")),
        }

        # Handle paths
        base_dir = os.getenv("C2C_BASE_DIR")
        if base_dir:
            env_settings["base_dir"] = Path(base_dir)

        creds_dir = os.getenv("C2C_CREDENTIALS_DIR")
        if creds_dir:
            env_settings["credentials_dir"] = Path(creds_dir)

        data_dir = os.getenv("C2C_DATA_DIR")
        if data_dir:
            env_settings["data_dir"] = Path(data_dir)

        # Apply overrides
        env_settings.update(overrides)

        return cls(**env_settings)

    @classmethod
    def from_args(cls, args) -> "Settings":
        """Create settings from parsed command line arguments.

        Args:
            args: Parsed argparse namespace.

        Returns:
            Settings instance.
        """
        settings_dict = {
            "instance_name": args.name,
            "mode": args.mode,
            "port": args.port,
        }

        if hasattr(args, "host") and args.host:
            settings_dict["host"] = args.host

        if hasattr(args, "server_url") and args.server_url:
            settings_dict["server_url"] = args.server_url

        if hasattr(args, "token") and args.token:
            settings_dict["token"] = args.token

        if hasattr(args, "credentials_dir") and args.credentials_dir:
            settings_dict["credentials_dir"] = Path(args.credentials_dir)

        if hasattr(args, "data_dir") and args.data_dir:
            settings_dict["data_dir"] = Path(args.data_dir)

        if hasattr(args, "auto_shutdown") and args.auto_shutdown:
            settings_dict["auto_shutdown_idle"] = args.auto_shutdown

        if hasattr(args, "no_verify_ssl") and args.no_verify_ssl:
            settings_dict["verify_ssl"] = False

        return cls(**settings_dict)
