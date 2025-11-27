"""TLS certificate generation and management for secure LAN communication."""

import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class TLSManager:
    """Manages TLS certificates for secure communication."""

    def __init__(self, credentials_dir: Path):
        """Initialize TLS manager.

        Args:
            credentials_dir: Directory to store certificates and keys.
        """
        self.credentials_dir = Path(credentials_dir)
        self.cert_path = self.credentials_dir / "server.crt"
        self.key_path = self.credentials_dir / "server.key"

    def ensure_credentials_dir(self) -> None:
        """Ensure credentials directory exists with proper permissions."""
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        # Set restrictive permissions (owner only)
        self.credentials_dir.chmod(0o700)

    def certificates_exist(self) -> bool:
        """Check if certificates already exist."""
        return self.cert_path.exists() and self.key_path.exists()

    def get_local_ips(self) -> List[str]:
        """Get all local IP addresses for this machine."""
        ips = ["127.0.0.1"]

        try:
            # Get hostname and resolve to IP
            hostname = socket.gethostname()
            host_ips = socket.gethostbyname_ex(hostname)[2]
            ips.extend(ip for ip in host_ips if ip not in ips)
        except socket.error:
            pass

        # Try to get IPs from network interfaces
        try:
            import subprocess
            result = subprocess.run(
                ["ip", "-4", "addr", "show"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'inet ' in line:
                    # Extract IP from line like "    inet 192.168.1.100/24 ..."
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        ip = parts[1].split('/')[0]
                        if ip not in ips:
                            ips.append(ip)
        except Exception:
            pass

        return ips

    def generate_self_signed_cert(
        self,
        hostname: Optional[str] = None,
        ip_addresses: Optional[List[str]] = None,
        validity_days: int = 365
    ) -> tuple[Path, Path]:
        """Generate self-signed certificate with SANs for LAN IPs.

        Args:
            hostname: Hostname for the certificate (defaults to machine hostname).
            ip_addresses: List of IP addresses to include in SANs.
            validity_days: How long the certificate should be valid.

        Returns:
            Tuple of (certificate_path, key_path).
        """
        self.ensure_credentials_dir()

        if hostname is None:
            hostname = socket.gethostname()

        if ip_addresses is None:
            ip_addresses = self.get_local_ips()

        # Generate RSA private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # Build subject
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "C2C-Bridge"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "LAN Communication"),
        ])

        # Build Subject Alternative Names (SANs)
        san_list: List[x509.GeneralName] = [
            x509.DNSName(hostname),
            x509.DNSName("localhost"),
        ]

        for ip in ip_addresses:
            try:
                san_list.append(x509.IPAddress(ipaddress.ip_address(ip)))
            except ValueError:
                continue  # Skip invalid IPs

        # Build certificate
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            )
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    key_cert_sign=True,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False
                ),
                critical=True
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False
            )
            .sign(private_key, hashes.SHA256())
        )

        # Save private key
        self.key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
        self.key_path.chmod(0o600)  # Owner read/write only

        # Save certificate
        self.cert_path.write_bytes(
            cert.public_bytes(serialization.Encoding.PEM)
        )
        self.cert_path.chmod(0o644)  # Owner read/write, others read

        return self.cert_path, self.key_path

    def get_certificate_info(self) -> dict:
        """Get information about the current certificate."""
        if not self.cert_path.exists():
            return {"exists": False}

        cert_data = self.cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Extract SANs
        sans = []
        try:
            san_ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    sans.append(f"DNS:{name.value}")
                elif isinstance(name, x509.IPAddress):
                    sans.append(f"IP:{name.value}")
        except x509.ExtensionNotFound:
            pass

        return {
            "exists": True,
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "serial_number": cert.serial_number,
            "not_valid_before": cert.not_valid_before_utc.isoformat(),
            "not_valid_after": cert.not_valid_after_utc.isoformat(),
            "sans": sans,
            "cert_path": str(self.cert_path),
            "key_path": str(self.key_path),
        }
