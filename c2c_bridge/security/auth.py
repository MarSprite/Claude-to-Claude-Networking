"""Token-based authentication for C2C Bridge."""

import hashlib
import secrets
from pathlib import Path
from typing import Optional


class TokenAuthenticator:
    """Handles pre-shared token authentication."""

    def __init__(self, token_path: Path):
        """Initialize token authenticator.

        Args:
            token_path: Path to store/read the authentication token.
        """
        self.token_path = Path(token_path)
        self._token_hash: Optional[str] = None
        self._cached_token: Optional[str] = None

    def generate_token(self, length: int = 32) -> str:
        """Generate a new cryptographically secure token.

        Args:
            length: Length of the token in bytes (will be base64 encoded).

        Returns:
            The generated token string.
        """
        token = secrets.token_urlsafe(length)

        # Store hash of token for validation
        self._token_hash = self._hash_token(token)
        self._cached_token = token

        # Ensure parent directory exists
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

        # Save token to file for manual distribution
        self.token_path.write_text(token)
        self.token_path.chmod(0o600)  # Owner read/write only

        return token

    def token_exists(self) -> bool:
        """Check if a token file exists."""
        return self.token_path.exists()

    def load_token(self) -> Optional[str]:
        """Load token from file.

        Returns:
            The token string or None if not found.
        """
        if not self.token_path.exists():
            return None

        self._cached_token = self.token_path.read_text().strip()
        self._token_hash = self._hash_token(self._cached_token)
        return self._cached_token

    def get_token(self) -> Optional[str]:
        """Get the current token (from cache or file).

        Returns:
            The token string or None if not available.
        """
        if self._cached_token:
            return self._cached_token
        return self.load_token()

    def validate_token(self, token: str) -> bool:
        """Validate a token against stored hash.

        Args:
            token: The token to validate.

        Returns:
            True if token is valid, False otherwise.
        """
        if not self._token_hash:
            self.load_token()
            if not self._token_hash:
                return False

        return secrets.compare_digest(
            self._hash_token(token),
            self._token_hash
        )

    def validate_authorization_header(self, auth_header: Optional[str]) -> tuple[bool, str]:
        """Validate an Authorization header.

        Args:
            auth_header: The Authorization header value (e.g., "Bearer <token>").

        Returns:
            Tuple of (is_valid, error_message).
        """
        if not auth_header:
            return False, "Missing Authorization header"

        parts = auth_header.split(" ", 1)
        if len(parts) != 2:
            return False, "Invalid Authorization header format"

        scheme, token = parts
        if scheme.lower() != "bearer":
            return False, f"Unsupported authentication scheme: {scheme}"

        if not self.validate_token(token):
            return False, "Invalid token"

        return True, "OK"

    def _hash_token(self, token: str) -> str:
        """Hash a token using SHA-256.

        Args:
            token: The token to hash.

        Returns:
            The hexadecimal hash string.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def rotate_token(self) -> str:
        """Generate a new token, replacing the old one.

        Returns:
            The new token string.
        """
        return self.generate_token()
