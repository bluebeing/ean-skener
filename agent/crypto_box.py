"""End-to-end šifrování zpráv mezi telefonem a PC (AES-256-GCM).

Klíč zná jen PC a telefon (z párovacího QR kódu), relay server vidí jen šifrovaný text.
Formát zprávy: base64url(IV 12 B || šifrovaný text || tag 16 B).
AAD = room + směr ("p2c" telefon→PC, "c2p" PC→telefon), takže zprávu nejde poslat zpátky odesílateli.
"""
import base64
import json
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CODE_RE = re.compile(r"^(\d{8}|\d{12}|\d{13})$")


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_room() -> str:
    return b64e(os.urandom(16))


def new_key() -> str:
    return b64e(AESGCM.generate_key(bit_length=256))


class Box:
    def __init__(self, room: str, key: str):
        self.room = room
        self.aes = AESGCM(b64d(key))

    def seal(self, obj, direction: str) -> str:
        iv = os.urandom(12)
        data = json.dumps(obj, separators=(",", ":")).encode()
        return b64e(iv + self.aes.encrypt(iv, data, (self.room + direction).encode()))

    def open(self, text: str, direction: str):
        """Vrátí dešifrovaný objekt, nebo None, když zpráva není od spárovaného zařízení."""
        try:
            raw = b64d(text)
            plain = self.aes.decrypt(raw[:12], raw[12:], (self.room + direction).encode())
            return json.loads(plain)
        except (InvalidTag, ValueError, TypeError):
            return None


def ean_checksum_ok(code: str) -> bool:
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    # váhy 3,1,3,1… počítané zprava od číslice před kontrolní
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def valid_code(code: str) -> bool:
    return bool(CODE_RE.match(code)) and ean_checksum_ok(code)
