"""Tabulka produktů (EAN → název) z Excelu nebo CSV.

Tabulka zůstává jen na PC. Načte se znovu sama, kdykoli se soubor změní,
takže stačí tabulku upravit a uložit.
"""
import csv
import os
import re
import threading
from dataclasses import dataclass, field

EAN_HEADERS = ("ean", "čárový kód", "carovy kod", "barcode", "gtin")
NAME_HEADERS = ("název", "nazev", "name", "produkt", "product", "zboží", "zbozi")
DIGITS_RE = re.compile(r"^\d{8,14}$")
# řídicí znaky (Tab, Enter…) a neviditelné obousměrné značky se nesmí dostat do vepisovaného textu
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]+")
MAX_NAME = 200  # delší buňka je skoro jistě chyba v tabulce – nevepisovat ji celé minuty


def normalize(code: str) -> str:
    """Klíč pro hledání: UPC-A (12 číslic) a EAN-13 s úvodní nulou se shodují."""
    return code.zfill(13) if len(code) <= 13 else code


def _cell_to_code(value):
    if value is None:
        return None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    text = re.sub(r"\s", "", str(value))
    return text if DIGITS_RE.match(text) else None


def _clean_name(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", CONTROL_RE.sub(" ", str(value))).strip()[:MAX_NAME].rstrip()


@dataclass
class Lookup:
    status: str  # "ok" | "missing" | "ambiguous"
    name: str = ""
    names: list = field(default_factory=list)


class ProductTable:
    def __init__(self):
        self.path = ""
        self.error = ""
        self._lock = threading.Lock()
        self._mtime = None
        self._names = {}  # klíč EAN -> [názvy v pořadí tabulky]

    # ---------- načtení ----------
    def set_path(self, path: str):
        with self._lock:
            self.path = path or ""
            self._mtime = None
            self._names = {}
            self.error = ""
        self.reload_if_changed()

    def reload_if_changed(self):
        """Znovu načte tabulku, pokud se soubor od posledního načtení změnil."""
        with self._lock:
            if not self.path:
                return
            try:
                st = os.stat(self.path)
                mtime = (st.st_mtime_ns, st.st_size)  # i velikost – dvě uložení během jednoho „tiku“ hodin
            except OSError:
                self.error = "Soubor s tabulkou nebyl nalezen"
                self._names = {}
                self._mtime = None
                return
            if mtime == self._mtime:
                return
            try:
                rows = _read_rows(self.path)
                self._names = _build_index(rows)
                self.error = ""
            except Exception as e:  # rozbitý / otevřený soubor – zkusí se při dalším skenu
                self.error = f"Tabulku nelze načíst: {e}"
                self._names = {}
                return
            self._mtime = mtime

    # ---------- dotazy ----------
    def lookup(self, code: str) -> Lookup:
        self.reload_if_changed()
        with self._lock:
            names = self._names.get(normalize(code), [])
        if not names:
            return Lookup("missing")
        unique = list(dict.fromkeys(names))
        if len(unique) > 1:
            return Lookup("ambiguous", names=unique)
        return Lookup("ok", name=unique[0])

    @property
    def loaded(self) -> bool:
        with self._lock:
            return bool(self._names)

    def count(self) -> int:
        with self._lock:
            return len(self._names)

    def ambiguous(self):
        """[(EAN, [názvy])] pro EANy, které mají v tabulce víc různých názvů."""
        with self._lock:
            items = list(self._names.items())
        result = []
        for key, names in items:
            unique = list(dict.fromkeys(names))
            if len(unique) > 1:
                result.append((key, unique))
        return result


def _read_rows(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl  # jen když je potřeba
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            wb.close()
    if ext in (".csv", ".txt"):
        raw = open(path, "rb").read()
        for encoding in ("utf-8-sig", "cp1250"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        return [row for row in csv.reader(text.splitlines(), dialect)]
    raise ValueError("podporované jsou soubory .xlsx a .csv")


def _find_columns(rows):
    """Vrátí (index řádku záhlaví nebo -1, sloupec EAN, sloupec názvu)."""
    if rows:
        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
        ean_col = next((i for i, h in enumerate(header) if any(k in h for k in EAN_HEADERS)), None)
        name_col = next((i for i, h in enumerate(header) if any(k in h for k in NAME_HEADERS)), None)
        if ean_col is not None and name_col is not None and ean_col != name_col:
            return 0, ean_col, name_col
    # bez záhlaví: EAN je sloupec s nejvíc číselnými kódy, název první textový sloupec
    sample = rows[:200]
    width = max((len(r) for r in sample), default=0)
    scores = [sum(1 for r in sample if i < len(r) and _cell_to_code(r[i])) for i in range(width)]
    if not scores or max(scores) == 0:
        raise ValueError("v tabulce není sloupec s EAN kódy")
    ean_col = scores.index(max(scores))
    name_col = next((i for i in range(width) if i != ean_col and any(
        i < len(r) and isinstance(r[i], str) and r[i].strip() and not _cell_to_code(r[i]) for r in sample)), None)
    if name_col is None:
        raise ValueError("v tabulce není sloupec s názvy")
    return -1, ean_col, name_col


def _build_index(rows):
    header_row, ean_col, name_col = _find_columns(rows)
    index = {}
    for r in rows[header_row + 1:]:
        if len(r) <= max(ean_col, name_col):
            continue
        code = _cell_to_code(r[ean_col])
        name = _clean_name(r[name_col])
        if code and name:
            index.setdefault(normalize(code), []).append(name)
    if not index:
        raise ValueError("tabulka neobsahuje žádné řádky s EAN a názvem")
    return index
