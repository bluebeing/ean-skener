"""Offline test načítání tabulky produktů (nic nevepisuje).

Spuštění: python tools/test_products.py [cesta k tabulce .xlsx]
Bez cesty otestuje jen vygenerované CSV soubory.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from products import ProductTable  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("OK   " if ok else "FAIL ") + name + (f" – {detail}" if detail else ""))


def write(tmp, name, text, encoding="utf-8"):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(text)
    return path


with tempfile.TemporaryDirectory() as tmp:
    t = ProductTable()
    t.set_path(write(tmp, "a.csv", "Název;EAN\nČokoláda hořká;8594001234561\nDvakrát;4006381333931\n"
                                   "Jinak;4006381333931\nUPC výrobek;036000291452\n", "cp1250"))
    check("CSV cp1250 se středníky", t.count() == 3, t.error)
    check("nalezený název s diakritikou", t.lookup("8594001234561").name == "Čokoláda hořká")
    check("víc názvů = ambiguous", t.lookup("4006381333931").status == "ambiguous")
    check("UPC-A (12) najde i EAN-13 s nulou", t.lookup("0036000291452").name == "UPC výrobek")
    check("chybějící EAN", t.lookup("5901234123457").status == "missing")

    p = write(tmp, "b.csv", "8594001234561,Bez záhlaví\n")
    t.set_path(p)
    check("CSV bez záhlaví", t.lookup("8594001234561").name == "Bez záhlaví", t.error)
    write(tmp, "b.csv", "8594001234561,Změněný název\n")
    os.utime(p, (2_000_000_000, 2_000_000_000))  # jiný čas úpravy i při velmi rychlém přepsání
    check("po uložení se tabulka načte znovu", t.lookup("8594001234561").name == "Změněný název")

    t.set_path(os.path.join(tmp, "neexistuje.xlsx"))
    check("chybějící soubor hlásí chybu", t.lookup("8594001234561").status == "missing" and bool(t.error), t.error)

if len(sys.argv) > 1:
    t = ProductTable()
    t.set_path(sys.argv[1])
    check("skutečná tabulka se načte", t.loaded, f"{t.count()} EANů {t.error}")
    check("první produkt", t.lookup("4004060420675").name == "Čajové filtry (Finum) - balení 100 ks filtrů",
          t.lookup("4004060420675").name)
    amb = t.ambiguous()
    check("sporné EANy", len(amb) == 11, f"{len(amb)}")
    check("8594172183316 je sporný", t.lookup("8594172183316").status == "ambiguous")

print(f"\n{sum(results)}/{len(results)} testů prošlo")
sys.exit(0 if all(results) else 1)
