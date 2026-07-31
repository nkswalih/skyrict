"""Unit tests for security utilities — JWT (RS256) and password hashing (Argon2id)."""

from __future__ import annotations

import pytest

from identity.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_jwt,
    verify_password,
)
from skyrict_common.exceptions import TokenExpiredError, TokenInvalidError


class TestPasswordHashing:
    """Test Argon2id password hashing."""

    def test_hash_password_returns_hash(self):
        hashed = hash_password("TestPassword123!")
        assert hashed != "TestPassword123!"
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        password = "MySecurePassword!1"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("CorrectPassword!1")
        assert verify_password("WrongPassword!1", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("SamePassword!1")
        h2 = hash_password("SamePassword!1")
        assert h1 != h2  # Argon2id uses random salt

    def test_verify_password_empty_string(self):
        hashed = hash_password("Password123!")
        assert verify_password("", hashed) is False


class TestJWT:
    """Test JWT token creation and verification (RS256)."""

    def test_create_and_verify_access_token(self):
        token = create_access_token("user-123", tenant_id="tenant-456")
        payload = verify_jwt(token)
        assert payload["sub"] == "user-123"
        assert payload["tenant_id"] == "tenant-456"
        assert payload["type"] == "access"
        assert payload["iss"] == "https://auth.test.skyrict.io"
        assert payload["aud"] == "api.test.skyrict.io"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_and_verify_refresh_token(self):
        token = create_refresh_token("user-123", tenant_id="tenant-456")
        payload = verify_jwt(token)
        assert payload["sub"] == "user-123"
        assert payload["tenant_id"] == "tenant-456"
        assert payload["type"] == "refresh"

    def test_verify_invalid_token(self):
        with pytest.raises(TokenInvalidError):
            verify_jwt("not.a.valid.token")

    def test_verify_tampered_token(self):
        token = create_access_token("user-123", tenant_id="tenant-456")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(TokenInvalidError):
            verify_jwt(tampered)

    def test_verify_rejects_non_rs256_header(self):
        """Ensure tokens with alg:none or HS256 header are rejected."""
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload_part = base64.urlsafe_b64encode(
            json.dumps({"sub": "user-123", "exp": 9999999999}).encode()
        ).rstrip(b"=").decode()
        fake_token = f"{header}.{payload_part}.fake-sig"

        with pytest.raises(TokenInvalidError):
            verify_jwt(fake_token)
