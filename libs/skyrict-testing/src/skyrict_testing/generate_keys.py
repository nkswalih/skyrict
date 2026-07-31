"""CLI to generate RSA key pairs for RS256 JWT development.

Usage:
    python -m skyrict_testing.generate_keys

Output (relative to CWD):
    .dev/keys/private.pem
    .dev/keys/public.pem

Keys are written to the gitignored .dev/ directory for local development only.
Tests generate ephemeral keys automatically and never commit key material.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_keypair(
    *, key_size: int = 2048, output_dir: Path | None = None
) -> tuple[Path, Path]:
    """Generate an RSA key pair and write to disk.

    Returns (private_key_path, public_key_path).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)

    out = output_dir or Path(".dev/keys")
    out.mkdir(parents=True, exist_ok=True)

    private_path = out / "private.pem"
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    public_path = out / "public.pem"
    public_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    return private_path, public_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate RSA key pair for RS256 JWT testing")
    parser.add_argument("--key-size", type=int, default=2048, help="RSA key size (default: 2048)")
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Output directory (default: .dev/keys)"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    private_path, public_path = generate_rsa_keypair(key_size=args.key_size, output_dir=output_dir)
    print(f"Private key: {private_path}")
    print(f"Public key:  {public_path}")
