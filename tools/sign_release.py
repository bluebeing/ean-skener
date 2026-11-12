"""Podpis instalátoru pro automatické aktualizace (Ed25519).

Soukromý klíč leží MIMO repozitář: %USERPROFILE%\\.ean-skener\\release-ed25519.pem
Agent obsahuje jen veřejný klíč (agent/updater.py) a nainstaluje pouze podepsané vydání,
takže ani převzetí GitHub účtu nestačí k podvržení aktualizace.

    python tools/sign_release.py --generate          # jednou: vytvoří klíč, vypíše veřejný klíč
    python tools/sign_release.py dist/EanAgent-Setup-1.3.0.exe   # vytvoří .sig vedle instalátoru
"""
import base64
import hashlib
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_FILE = Path(os.environ.get("EAN_SIGNING_KEY") or Path.home() / ".ean-skener" / "release-ed25519.pem")


def signed_message(name: str, sha256_hex: str) -> bytes:
    """Co se podepisuje: název instalátoru (obsahuje verzi) a jeho SHA-256."""
    return f"ean-skener-release\n{name}\n{sha256_hex.lower()}\n".encode()


def public_key_b64(key) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def generate():
    if KEY_FILE.exists():
        sys.exit(f"Klíč už existuje: {KEY_FILE}")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    KEY_FILE.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    print(f"Soukromý klíč: {KEY_FILE}  (ZÁLOHUJ, nikam nenahrávej)")
    print(f"Veřejný klíč do agent/updater.py: {public_key_b64(key)}")


def sign(installer: Path):
    key = serialization.load_pem_private_key(KEY_FILE.read_bytes(), None)
    sha = hashlib.sha256(installer.read_bytes()).hexdigest()
    sig = key.sign(signed_message(installer.name, sha))
    out = installer.with_name(installer.name + ".sig")
    out.write_text(base64.b64encode(sig).decode(), encoding="ascii")
    print(f"Podepsáno: {out.name} (veřejný klíč {public_key_b64(key)})")


if __name__ == "__main__":
    if sys.argv[1:] == ["--generate"]:
        generate()
    elif len(sys.argv) == 2:
        sign(Path(sys.argv[1]))
    else:
        sys.exit(__doc__)
