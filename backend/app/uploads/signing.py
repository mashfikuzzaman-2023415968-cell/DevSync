"""Short-lived signed download URLs (§14.9): HMAC-SHA256 over the storage key, type, download
name and expiry, with a key derived from SECRET_KEY; valid for 5 minutes."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.core.security import derive_key

TTL = timedelta(minutes=5)
_INFO = "file-download-url"


@dataclass(frozen=True)
class SignedFile:
    storage_key: str
    mime_type: str
    name: str
    expires: int


def _signature(secret: str, f: SignedFile) -> str:
    key = derive_key(secret, _INFO)
    msg = "\n".join([f.storage_key, f.mime_type, f.name, str(f.expires)]).encode()
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign_url(secret: str, f: SignedFile) -> str:
    """Path + query the browser follows (`/api/v1/files/blob/<key>?…`)."""
    query = urlencode({"t": f.mime_type, "n": f.name, "e": f.expires, "s": _signature(secret, f)})
    return f"/api/v1/files/blob/{f.storage_key}?{query}"


def expiry(now: datetime) -> int:
    return int((now + TTL).timestamp())


def verify(secret: str, f: SignedFile, signature: str, now: datetime) -> bool:
    """Constant-time signature check plus expiry."""
    if f.expires < int(now.timestamp()) or f.expires > int((now + TTL * 2).timestamp()):
        return False
    return hmac.compare_digest(_signature(secret, f), signature)
