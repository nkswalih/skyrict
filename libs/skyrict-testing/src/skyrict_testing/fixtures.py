"""Shared pytest fixtures for Skyrict services.

Usage in service conftest.py:
    from skyrict_testing.fixtures import *
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ---------------------------------------------------------------------------
# RSA key fixtures (for RS256 JWT testing)
#
# Keys are generated fresh in memory for every test session — no key material
# is ever stored in or committed to the repository.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair() -> dict[str, str]:
    """Generate a fresh RSA-2048 key pair in memory for this test session.

    Returns {"private_key": str, "public_key": str} PEM-encoded keys.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {
        "private_key": private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode(),
        "public_key": private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
    }


@pytest.fixture(scope="session")
def rsa_private_key(rsa_keypair: dict[str, str]) -> str:
    """Fresh RSA private key (PEM string) generated for this test session."""
    return rsa_keypair["private_key"]


@pytest.fixture(scope="session")
def rsa_public_key(rsa_keypair: dict[str, str]) -> str:
    """Fresh RSA public key (PEM string) generated for this test session."""
    return rsa_keypair["public_key"]


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for pytest-asyncio."""
    return "asyncio"
