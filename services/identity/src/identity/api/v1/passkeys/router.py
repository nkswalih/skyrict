"""Passkey (WebAuthn) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from identity.api.deps import get_current_user, get_passkey_service
from identity.application.passkey.service.passkey import PasskeyService
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/passkeys", tags=["passkeys"])


@router.post("/register/start")
async def start_passkey_registration(
    current_user: dict = Depends(get_current_user),
    passkey_svc: PasskeyService = Depends(get_passkey_service),
) -> ResponseEnvelope[dict]:
    """Start passkey registration — returns WebAuthn creation options."""
    import uuid

    options = await passkey_svc.start_registration(uuid.UUID(current_user["user_id"]))
    return ResponseEnvelope(data=options)


@router.post("/register/complete")
async def complete_passkey_registration(
    credential: dict,
    current_user: dict = Depends(get_current_user),
    passkey_svc: PasskeyService = Depends(get_passkey_service),
) -> ResponseEnvelope[dict]:
    """Complete passkey registration after browser ceremony."""
    import uuid

    result = await passkey_svc.complete_registration(uuid.UUID(current_user["user_id"]), credential)
    return ResponseEnvelope(data=result, message="Passkey registered")


@router.post("/authenticate/start")
async def start_passkey_authentication(
    email: str,
    passkey_svc: PasskeyService = Depends(get_passkey_service),
) -> ResponseEnvelope[dict]:
    """Start passkey authentication — returns WebAuthn request options."""
    options = await passkey_svc.start_authentication(email)
    return ResponseEnvelope(data=options)


@router.post("/authenticate/complete")
async def complete_passkey_authentication(
    credential: dict,
    passkey_svc: PasskeyService = Depends(get_passkey_service),
) -> ResponseEnvelope[dict]:
    """Complete passkey authentication after browser ceremony."""
    result = await passkey_svc.complete_authentication(credential)
    return ResponseEnvelope(data=result, message="Passkey authentication successful")
