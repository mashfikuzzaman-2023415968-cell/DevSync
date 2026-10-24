"""Small network helpers: IP validation, network lists and the trusted client address."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from starlette.types import Scope

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def valid_ip(value: str | None) -> str | None:
    """The address if it is a valid IPv4/IPv6 literal, else None (never store junk in `inet`)."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def parse_networks(value: str) -> tuple[IPNetwork, ...]:
    """Parse a comma-separated list of IPs/CIDRs ("10.0.0.0/8, 2001:db8::/32, 192.0.2.7").

    Raises ``ValueError`` for anything else, including ``*`` and networks with host bits set
    (``10.0.0.1/8`` is ambiguous), so a typo stops startup instead of silently widening or
    narrowing access (fail closed).
    """
    networks: list[IPNetwork] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=True))
        except ValueError as exc:
            raise ValueError(f"{item!r} is not a valid IP address or network") from exc
    return tuple(networks)


def _address(value: str) -> IPAddress | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped  # "::ffff:10.0.0.1" is 10.0.0.1
    return address


def ip_in_networks(ip: str | None, networks: Iterable[IPNetwork]) -> bool:
    """True when ``ip`` is a valid address inside one of ``networks`` (False for junk)."""
    address = _address(ip) if ip else None
    if address is None:
        return False
    return any(address.version == net.version and address in net for net in networks)


def trusted_client_ip(scope: Scope, trusted_proxies: Iterable[IPNetwork]) -> str | None:
    """The client's address, believing `X-Forwarded-For` only from a trusted proxy (§14.3).

    Nginx overwrites `X-Forwarded-For` with its own `$remote_addr`, so the right-most entry
    is the address Nginx saw. When the immediate peer is not a trusted proxy the header is
    ignored. Returns None when no valid address is known; callers must then deny.
    """
    client = scope.get("client")
    peer = str(client[0]) if client else ""
    if _address(peer) is None:
        return None
    proxies = tuple(trusted_proxies)
    if ip_in_networks(peer, proxies):
        forwarded = [v for k, v in scope.get("headers", []) if k == b"x-forwarded-for"]
        if forwarded:
            last = forwarded[-1].decode("latin-1").split(",")[-1].strip()
            address = _address(last)
            return str(address) if address is not None else None
    address = _address(peer)
    return str(address) if address is not None else None
