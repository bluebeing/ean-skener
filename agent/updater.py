"""Automatické aktualizace z GitHub Releases.

Agent si jednou za čas zjistí nejnovější vydání, stáhne instalátor, ověří jeho SHA-256
a spustí ho potichu. Instalátor agenta ukončí, přepíše a znovu spustí; data (párování) zůstanou.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from version import __version__

REPO = "bluebeing/ean-skener"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_RE = re.compile(r"^EanAgent-Setup-[\d.]+\.exe$")
HEADERS = {"User-Agent": f"EanAgent/{__version__}", "Accept": "application/vnd.github+json"}


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
    latest = release.get("tag_name", "")
    if _parse(latest) <= _parse(__version__):
        return None
    assets = release.get("assets", [])
    setup = next((a for a in assets if ASSET_RE.match(a.get("name", ""))), None)
    if not setup:
        return None
    digest = (setup.get("digest") or "").removeprefix("sha256:")
    if not digest:  # záloha: kontrolní součet jako samostatný soubor vydání
        sums = next((a for a in assets if a.get("name") == setup["name"] + ".sha256"), None)
        if not sums:
            return None
        digest = _get(sums["browser_download_url"]).decode().split()[0]
    return latest.lstrip("v"), setup["browser_download_url"], digest.lower()


def download(url, sha256) -> str:
    """Stáhne instalátor do dočasné složky a ověří ho. Vrátí cestu k souboru."""
    data = _get(url, timeout=300)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("Stažený instalátor nesouhlasí s kontrolním součtem")
    path = os.path.join(tempfile.gettempdir(), url.rsplit("/", 1)[-1])
    with open(path, "wb") as f:
        f.write(data)
    return path


def run_installer(path):
    """Spustí instalátor potichu, odpojený od agenta (agent se pak sám ukončí)."""
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     creationflags=flags, close_fds=True)
