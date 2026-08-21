"""Scoped, single-use approval tokens.

The token authorises exactly one irreversible operation on one incident. Only
its id and a SHA-256 hash are stored, so a database dump cannot be replayed as
an approval; the raw secret is returned once, at creation, and never again.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

#: How long an approval token stays usable. Short by design: the token exists to
#: cover one operation, not to be stored anywhere.
APPROVAL_TOKEN_TTL = timedelta(minutes=15)

_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class ScopedToken:
    token_id: uuid.UUID
    #: The raw secret. Present only on the object returned by `issue()`.
    token: str
    token_hash: str
    scope: str
    expires_at: datetime


def scope_for(incident_id: uuid.UUID, action: str) -> str:
    return f"incident:{incident_id}:{action}"


def hash_token(token: str, *, scope: str) -> str:
    """Hash the secret together with its scope, so a token cannot be reused elsewhere."""
    return hashlib.sha256(f"{scope}:{token}".encode()).hexdigest()


def issue(
    incident_id: uuid.UUID, *, action: str = "approve", ttl: timedelta = APPROVAL_TOKEN_TTL
) -> ScopedToken:
    scope = scope_for(incident_id, action)
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    return ScopedToken(
        token_id=uuid.uuid4(),
        token=token,
        token_hash=hash_token(token, scope=scope),
        scope=scope,
        expires_at=datetime.now(UTC) + ttl,
    )


def verify(token: str, *, expected_hash: str, scope: str, expires_at: datetime | None) -> bool:
    """Constant-time check of a presented token against its stored hash."""
    if expires_at is not None:
        deadline = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if datetime.now(UTC) > deadline:
            return False
    return hmac.compare_digest(hash_token(token, scope=scope), expected_hash)
