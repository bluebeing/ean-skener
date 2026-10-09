"""Nastavení agenta a cesty k datům / přibaleným souborům."""
import json
import sys
import threading
from pathlib import Path

from crypto_box import new_key, new_room

APP_NAME = "EanAgent"
# adresa nasazeného Cloudflare relay (viz relay/)
DEFAULT_RELAY_URL = "https://ean-skener.blue-kolman.workers.dev"
OBSOLETE_KEYS = ("https_port", "http_port", "network", "token")


def _data_dir() -> Path:
    # Data (párovací klíč) leží vedle EanAgent.exe, ne v %APPDATA%: zabalené aplikace
    # (MSIX) si AppData virtualizují, takže agent spuštěný z nich by viděl jiný klíč
    # než agent spuštěný dvojklikem, a telefon by se přestal připojovat.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent / "dist" / "data"


DATA_DIR = _data_dir()
CONFIG_FILE = DATA_DIR / "config.json"

DEFAULTS = {
    "relay_url": DEFAULT_RELAY_URL,
    # "unicode" = znaky přes KEYEVENTF_UNICODE (nezávislé na rozložení klávesnice)
    # "numpad"  = klávesy numerické klávesnice (záloha např. pro vzdálenou plochu)
    # "off"     = nepsat, jen zkopírovat do schránky
    "typing_mode": "unicode",
    # co stisknout po vepsání kódu: "none" | "enter" | "tab"
    "suffix": "none",
    "key_delay_ms": 8,
    # kód se zároveň vloží do schránky (Ctrl+V)
    "clipboard": True,
}


def resource_dir() -> Path:
    """Kořen projektu – při běhu z PyInstaller .exe rozbalená složka."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent.parent


class Config:
    def __init__(self):
        self._lock = threading.Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        for key in OBSOLETE_KEYS:
            data.pop(key, None)
        if not data.get("relay_url"):
            data.pop("relay_url", None)  # převezme výchozí adresu z nové verze
        self._data = {**DEFAULTS, **data}
        if not self._data.get("room") or not self._data.get("key"):
            self.new_pairing(save=False)
        self.save()

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
        self.save()

    def new_pairing(self, save=True):
        """Nová místnost a klíč – dosud spárované telefony se už nepřipojí."""
        with self._lock:
            self._data["room"] = new_room()
            self._data["key"] = new_key()
        if save:
            self.save()

    def pairing_url(self) -> str:
        return f"{self['relay_url'].rstrip('/')}/#r={self['room']}&k={self['key']}"

    def save(self):
        with self._lock:
            CONFIG_FILE.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
