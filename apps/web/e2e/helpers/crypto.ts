import { createHmac, randomBytes } from "node:crypto";

const B32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function bytesToBase32(bytes: Uint8Array): string {
  let bits = 0;
  let value = 0;
  let output = "";
  for (const byte of bytes) {
    value = (value << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      output += B32_ALPHABET[(value >>> (bits - 5)) & 0x1f];
      bits -= 5;
    }
  }
  if (bits > 0) {
    output += B32_ALPHABET[(value << (5 - bits)) & 0x1f];
  }
  return output;
}

function base32ToBytes(value: string): Uint8Array {
  const clean = value
    .toUpperCase()
    .replace(/[^A-Z2-7]/g, "")
    .replace(/=+$/, "");
  let bits = 0;
  let valueAcc = 0;
  const bytes: number[] = [];
  for (const char of clean) {
    const index = B32_ALPHABET.indexOf(char);
    if (index === -1) continue;
    valueAcc = (valueAcc << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bytes.push((valueAcc >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Uint8Array.from(bytes);
}

/** RFC 4226 HOTP — dynamic truncation of the HMAC-SHA1 counter block. */
function hotp(secret: string, counter: number, digits = 6): string {
  const key = base32ToBytes(secret);
  const counterBytes = Buffer.alloc(8);
  counterBytes.writeUInt32BE(Math.floor(counter / 2 ** 32), 0);
  counterBytes.writeUInt32BE(counter % 2 ** 32, 4);

  const hmac = createHmac("sha1", key).update(counterBytes).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const binary =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff);
  return (binary % 10 ** digits).toString().padStart(digits, "0");
}

/** RFC 6238 TOTP for the current 30-second step. */
export function totp(
  secret: string,
  atMs: number = Date.now(),
  stepSeconds = 30,
): string {
  const counter = Math.floor(atMs / 1000 / stepSeconds);
  return hotp(secret, counter);
}

/** A pyotp-compatible random base32 secret (20 bytes → 32 chars). */
export function randomBase32Secret(): string {
  return bytesToBase32(randomBytes(20));
}

/** 16 lowercase hex chars, matching the backend `secrets.token_hex(8)` format. */
export function backupCode(): string {
  return randomBytes(8).toString("hex");
}

export function normalizeSecret(displayed: string): string {
  return displayed
    .toUpperCase()
    .replace(/[^A-Z2-7]/g, "")
    .replace(/=+$/, "");
}
