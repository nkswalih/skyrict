from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from identity.core.config import settings
from identity.core.redis import redis_client

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _email_digest(email: str) -> str:
    return hashlib.sha256(email.lower().encode("utf-8")).hexdigest()


def _otp_key(email: str) -> str:
    return f"signup_otp:{_email_digest(email)}"


def _otp_attempts_key(email: str) -> str:
    return f"signup_otp_attempts:{_email_digest(email)}"


def _otp_resend_key(email: str) -> str:
    return f"signup_otp_resend:{_email_digest(email)}"


def _vt_key(token: str) -> str:
    return f"signup_vt:{token}"


def _flow_key(token: str) -> str:
    return f"signup_flow:{token}"


def _flow_sends_key(token: str) -> str:
    return f"signup_flow_sends:{token}"


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _as_int(value: object) -> int:
    try:
        return int(_as_str(value) or 0)
    except (TypeError, ValueError):
        return 0


def generate_otp() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def generate_signup_flow_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class SignupFlow:
    """A wizard that cleared its challenge, and how much of its mail budget is spent.

    ``email`` is the address the challenge was solved *for*. Binding it here is
    what stops one solved challenge from being spent on someone else's inbox.
    """

    email: str
    sends: int


class VerificationStore:
    def __init__(self, client: Redis | None = None) -> None:
        self._client = client if client is not None else redis_client

    async def set_otp(self, email: str, otp_hash: str) -> None:
        await self._client.set(_otp_key(email), otp_hash, ex=settings.OTP_EXPIRE_SECONDS)
        await self._client.set(_otp_attempts_key(email), "0", ex=settings.OTP_EXPIRE_SECONDS)

    async def get_otp_hash(self, email: str) -> str | None:
        return _as_str(await self._client.get(_otp_key(email)))

    async def delete_otp(self, email: str) -> None:
        await self._client.delete(_otp_key(email), _otp_attempts_key(email))

    async def get_attempts(self, email: str) -> int:
        return _as_int(await self._client.get(_otp_attempts_key(email)))

    async def increment_attempts(self, email: str) -> int:
        key = _otp_attempts_key(email)
        count = _as_int(await self._client.incr(key))
        ttl = _as_int(await self._client.ttl(key))
        if ttl < 0:
            await self._client.expire(key, settings.OTP_EXPIRE_SECONDS)
        return count

    async def is_resend_blocked(self, email: str) -> bool:
        return bool(await self._client.exists(_otp_resend_key(email)))

    async def mark_resend(self, email: str) -> None:
        await self._client.set(_otp_resend_key(email), "1", ex=settings.OTP_RESEND_COOLDOWN_SECONDS)

    async def resend_in(self, email: str) -> int:
        return max(_as_int(await self._client.ttl(_otp_resend_key(email))), 0)

    async def set_signup_flow(self, token: str, email: str) -> None:
        """Record a wizard that cleared its challenge, with a fresh send budget."""
        await self._client.set(
            _flow_key(token),
            json.dumps({"email": email}),
            ex=settings.SIGNUP_FLOW_TTL_SECONDS,
        )
        await self._client.set(_flow_sends_key(token), "0", ex=settings.SIGNUP_FLOW_TTL_SECONDS)

    async def get_signup_flow(self, token: str) -> SignupFlow | None:
        """The flow a proof names, or None if it was never issued or has expired."""
        raw = _as_str(await self._client.get(_flow_key(token)))
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("email"), str):
            return None
        return SignupFlow(
            email=payload["email"],
            sends=_as_int(await self._client.get(_flow_sends_key(token))),
        )

    async def consume_signup_flow_send(self, token: str) -> int:
        """Charge one send against the flow's budget and return the new total.

        INCR rather than a read-modify-write so two concurrent sends cannot both
        read the same remaining budget. The TTL is deliberately not refreshed:
        the window runs from when the challenge was solved, so a caller that
        keeps sending cannot hold a proof open indefinitely.
        """
        key = _flow_sends_key(token)
        count = _as_int(await self._client.incr(key))
        ttl = _as_int(await self._client.ttl(key))
        if ttl < 0:
            await self._client.expire(key, settings.SIGNUP_FLOW_TTL_SECONDS)
        return count

    async def set_verification_token(self, token: str, email: str, password_hash: str) -> str:
        await self._client.set(
            _vt_key(token),
            json.dumps({"email": email, "password_hash": password_hash}),
            ex=settings.VERIFICATION_TOKEN_TTL_SECONDS,
        )
        return token

    async def get_verification_token(self, token: str) -> dict[str, str] | None:
        raw = _as_str(await self._client.get(_vt_key(token)))
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("email"), str):
            return None
        return {
            "email": payload["email"],
            "password_hash": payload.get("password_hash", "") or "",
        }

    async def update_verification_token_password(self, token: str, password_hash: str) -> None:
        payload = await self.get_verification_token(token)
        if payload is not None:
            await self.set_verification_token(token, payload["email"], password_hash)

    async def delete_verification_token(self, token: str) -> None:
        await self._client.delete(_vt_key(token))
