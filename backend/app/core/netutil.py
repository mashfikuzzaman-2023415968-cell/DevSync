"""Small network helpers."""

from __future__ import annotations

import ipaddress


def valid_ip(value: str | None) -> str | None:
    """The address if it is a valid IPv4/IPv6 literal, else None (never store junk in `inet`)."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
