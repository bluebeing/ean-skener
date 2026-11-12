"""Automatické aktualizace z GitHub Releases.

Agent si jednou za čas zjistí nejnovější vydání, ověří podpis Ed25519 (soukromý klíč má jen
autor, viz tools/sign_release.py), stáhne instalátor, ověří jeho SHA-256 a spustí ho potichu.
Instalátor agenta ukončí, přepíše a znovu spustí; data (párování) zůstanou.
Nepodepsané nebo jinak podezřelé vydání se nenainstaluje.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from version import __version__

REPO = "bluebeing/ean-skener"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
ASSET_RE = re.compile(r"^EanAgent-Setup-(\d+\.\d+\.\d+)\.exe$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
HEADERS = {"User-Agent": f"EanAgent/{__version__}", "Accept": "application/vnd.github+json"}
# veřejná část podpisového klíče vydání (soukromá je jen u autora mimo repozitář)
RELEASE_PUBLIC_KEY = "LeQPL8hpLGoJKzA8RY/Wp9NHhGBRdKyK5RejELkxBiI="


class UpdateRejected(Exception):
    """Vydání nesplňuje bezpečnostní kontroly – neinstaluje se."""


def signed_message(name: str, sha256_hex: str) -> bytes:
    # musí odpovídat tools/sign_release.py
    return f"ean-skener-release\n{name}\n{sha256_hex.lower()}\n".encode()


def verify_signature(name: str, sha256_hex: str, signature_b64: str, public_key_b64=RELEASE_PUBLIC_KEY):
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64.strip(), validate=True), signed_message(name, sha256_hex))
    except (InvalidSignature, ValueError) as e:
        raise UpdateRejected(f"Neplatný podpis vydání {name}") from e


def _parse(version: str):
    return tuple(int(p) for p in re.findall(r"\d+", version)[:3])


def can_update() -> bool:
    """Aktualizovat jde jen nainstalovaná aplikace (ne vývojové spuštění z Pythonu)."""
    return bool(getattr(sys, "frozen", False))


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check():
    """Vrátí (verze, url instalátoru, sha256) novější verze, nebo None."""
    try:
        release = json.loads(_get(API_LATEST))
    except urllib.error.HTTPError as e:
        if e.code == 404:  # zatím žádné vydání
            return None
        raise
    latest = str(release.get("tag_name", ""))
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", latest) or _parse(latest) <= _parse(__version__):
        return None
    version = latest.lstrip("v")
    assets = release.get("assets", [])
    setup = next((a for a in assets if ASSET_RE.match(str(a.get("name", "")))), None)
    if not setup:
        return None
    name = setup["name"]
    url = str(setup.get("browser_download_url", ""))
    if ASSET_RE.match(name).group(1) != version:
        raise UpdateRejected(f"Instalátor {name} nepatří k vydání {latest}")
    if url != f"{DOWNLOAD_PREFIX}{latest}/{name}":
        raise UpdateRejected(f"Neočekávaná adresa instalátoru: {url}")

    digest = str(setup.get("digest") or "").removeprefix("sha256:").lower()
    if not digest:  # záloha: kontrolní součet jako samostatný soubor vydání
        sums = _asset(assets, latest, name + ".sha256")
        digest = _get(sums).decode().split()[0].lower()
    if not SHA_RE.match(digest):
        raise UpdateRejected("Neplatný kontrolní součet vydání")
    signature = _get(_asset(assets, latest, name + ".sig")).decode("ascii")
    verify_signature(name, digest, signature)  # bez platného podpisu se nic nestáhne
    return version, url, digest


def _asset(assets, tag, name):
    asset = next((a for a in assets if a.get("name") == name), None)
    if not asset:
        raise UpdateRejected(f"Vydání {tag} nemá soubor {name}")
    url = str(asset.get("browser_download_url", ""))
    if url != f"{DOWNLOAD_PREFIX}{tag}/{name}":
        raise UpdateRejected(f"Neočekávaná adresa souboru: {url}")
    return url


def download(url, sha256, progress=None) -> str:
    """Stáhne instalátor po částech do dočasné složky a ověří ho. Vrátí cestu k souboru.

    progress(procenta) se volá průběžně; na pomalé síti může stahování trvat i minuty.
    """
    name = url.rsplit("/", 1)[-1]
    if not url.startswith(DOWNLOAD_PREFIX) or not ASSET_RE.match(name):
        raise UpdateRejected(f"Neočekávaná adresa instalátoru: {url}")  # žádné ..\ v cestě
    path = os.path.join(tempfile.gettempdir(), name)
    part = path + ".part"
    digest = hashlib.sha256()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last_pct = 0, -1
        while chunk := resp.read(256 * 1024):
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            pct = done * 100 // total if total else 0
            if progress and pct != last_pct:
                progress(pct)
                last_pct = pct
    if digest.hexdigest() != sha256:
        os.remove(part)
        raise ValueError("Stažený instalátor nesouhlasí s kontrolním součtem")
    os.replace(part, path)
    return path


def run_installer(path):
    """Spustí instalátor potichu, odpojený od agenta (agent se pak sám ukončí)."""
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     creationflags=flags, close_fds=True)
