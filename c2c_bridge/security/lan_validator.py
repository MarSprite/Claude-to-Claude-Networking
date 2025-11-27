"""LAN IP validation for restricting connections to local network."""

import ipaddress
from typing import List, Optional


class LANValidator:
    """Validates that connections come from LAN IP addresses only."""

    # RFC 1918 private IP ranges + loopback
    DEFAULT_PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
        ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
    ]

    def __init__(self, allowed_ranges: Optional[List[str]] = None):
        """Initialize LAN validator.

        Args:
            allowed_ranges: Optional list of CIDR ranges to allow.
                           Defaults to RFC 1918 private ranges.
        """
        if allowed_ranges:
            self.allowed_ranges = [
                ipaddress.ip_network(r, strict=False) for r in allowed_ranges
            ]
        else:
            self.allowed_ranges = self.DEFAULT_PRIVATE_RANGES.copy()

    def add_allowed_range(self, cidr: str) -> None:
        """Add an additional allowed CIDR range.

        Args:
            cidr: CIDR notation range (e.g., "192.168.1.0/24").
        """
        self.allowed_ranges.append(ipaddress.ip_network(cidr, strict=False))

    def is_lan_ip(self, ip_str: str) -> bool:
        """Check if IP address is within allowed LAN ranges.

        Args:
            ip_str: IP address string to check.

        Returns:
            True if IP is in an allowed range, False otherwise.
        """
        try:
            # Handle IPv4-mapped IPv6 addresses (e.g., ::ffff:192.168.1.1)
            ip = ipaddress.ip_address(ip_str)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped

            return any(ip in network for network in self.allowed_ranges)
        except ValueError:
            return False

    def validate_connection(self, client_ip: str) -> tuple[bool, str]:
        """Validate incoming connection from client IP.

        Args:
            client_ip: The client's IP address.

        Returns:
            Tuple of (is_valid, message).
        """
        if self.is_lan_ip(client_ip):
            return True, f"Connection accepted from LAN IP: {client_ip}"
        return False, f"Connection rejected: {client_ip} is not a LAN address"

    def get_allowed_ranges(self) -> List[str]:
        """Get list of allowed IP ranges as strings.

        Returns:
            List of CIDR notation strings.
        """
        return [str(r) for r in self.allowed_ranges]

    @staticmethod
    def extract_client_ip(
        remote_addr: str,
        x_forwarded_for: Optional[str] = None,
        trust_proxy: bool = False
    ) -> str:
        """Extract the client IP from request information.

        Args:
            remote_addr: The direct remote address.
            x_forwarded_for: X-Forwarded-For header value if present.
            trust_proxy: Whether to trust X-Forwarded-For header.

        Returns:
            The client IP address string.
        """
        if trust_proxy and x_forwarded_for:
            # Take the first IP in the chain (original client)
            return x_forwarded_for.split(",")[0].strip()
        return remote_addr
