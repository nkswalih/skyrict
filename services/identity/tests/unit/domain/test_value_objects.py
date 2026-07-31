"""Unit tests for domain value objects."""

from __future__ import annotations

import pytest

from identity.domain.value_objects import PasswordPolicy, RiskScore, TokenPair


class TestPasswordPolicy:
    """Test password policy validation."""

    def test_valid_password(self):
        policy = PasswordPolicy()
        errors = policy.validate("StrongP@ss1")
        assert errors == []

    def test_too_short(self):
        policy = PasswordPolicy(min_length=8)
        errors = policy.validate("Short1!")
        assert any("at least 8" in e for e in errors)

    def test_no_uppercase(self):
        policy = PasswordPolicy()
        errors = policy.validate("nouppercase1!")
        assert any("uppercase" in e for e in errors)

    def test_no_lowercase(self):
        policy = PasswordPolicy()
        errors = policy.validate("NOLOWERCASE1!")
        assert any("lowercase" in e for e in errors)

    def test_no_digit(self):
        policy = PasswordPolicy()
        errors = policy.validate("NoDigitHere!")
        assert any("digit" in e for e in errors)

    def test_no_special_char(self):
        policy = PasswordPolicy()
        errors = policy.validate("NoSpecialChar1")
        assert any("special" in e for e in errors)


class TestTokenPair:
    """Test TokenPair value object."""

    def test_authorization_header(self):
        pair = TokenPair(access_token="abc123", refresh_token="xyz789")
        assert pair.authorization_header == "Bearer abc123"

    def test_default_values(self):
        pair = TokenPair(access_token="a", refresh_token="b")
        assert pair.token_type == "Bearer"
        assert pair.expires_in == 1800


class TestRiskScore:
    """Test RiskScore enum."""

    def test_values(self):
        assert RiskScore.LOW.value == "low"
        assert RiskScore.CRITICAL.value == "critical"
