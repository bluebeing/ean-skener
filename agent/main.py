"""EAN agent: přijímá kódy z telefonu (přes šifrovaný relay) a vepisuje je do aktivního okna."""
import ctypes
import logging
import queue
import socket
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.parse import urlparse

import pystray
import qrcode
from PIL import Image, ImageTk

import updater
from config import DATA_DIR, Config, resource_dir
from products import ProductTable
from relay_client import RelayClient
from version import __version__

log = logging.getLogger("ean")

BG, FG, MUTED, ACCENT, WARN, PANEL = "#0f1115", "#e8eaed", "#9aa0a6", "#3ddc84", "#fbbc04", "#181b21"
PRODUCTS_CHECK_MS = 5000
FIRST_UPDATE_CHECK_MS = 30_000
UPDATE_CHECK_MS = 6 * 3600_000
ERROR_ALREADY_EXISTS = 183


def qr_image(text, size=260):
    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(text)
    return qr.make_image(fill_color="black", back_color="white").get_image().resize(
        (size, size), Image.NEAREST)


class App:
    def __init__(self):
        self.cfg = Config()
        self.res = resource_dir()
        self.events = queue.Queue()
        self.connected = False
        self.clients = 0
        self.stopped = False
        self.update_status = ""  # text pro tray menu
        self.updating = False

        self.products = ProductTable()
        self.root = tk.Tk()
        self.root.withdraw()
        # bez konzole by se chyby v Tk callbackách ztratily (stderr neexistuje)
        self.root.report_callback_exception = lambda *exc: log.error("Chyba v okně", exc_info=exc)
        self.client = RelayClient(self.cfg, lambda ev, data: self.events.put((ev, data)), self.products)
        self._build_window()
        self._build_tray()
        if self.cfg["relay_url"]:
            self.client.start()
        self._load_products(self.cfg["products_file"])
        self.root.after(150, self._poll_events)
        self.root.after(PRODUCTS_CHECK_MS, self._check_products)
        if updater.can_update():
            self.root.after(FIRST_UPDATE_CHECK_MS, self._scheduled_update_check)

    # ---------- okno ----------
    def _build_window(self):
        r = self.root
        r.title("EAN agent")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self.hide_window)
        try:
            r.iconbitmap(str(self.res / "agent" / "app.ico"))
        except tk.TclError:
            pass

        tk.Label(r, text="EAN agent", font=("Segoe UI Semibold", 18), bg=BG, fg=FG).pack(pady=(16, 0))
        self.status_lbl = tk.Label(r, font=("Segoe UI", 11), bg=BG)
        self.status_lbl.pack()

        tk.Label(r, text="Spárovat telefon", font=("Segoe UI Semibold", 11), bg=BG, fg=FG).pack(pady=(14, 0))
        tk.Label(r, text="Naskenuj fotoaparátem telefonu, nebo v aplikaci tlačítkem „Naskenovat párovací QR“",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED, wraplength=420).pack()
        self.qr_lbl = tk.Label(r, bg=BG)
        self.qr_lbl.pack(padx=24, pady=8)
        self.url_lbl = tk.Label(r, font=("Consolas", 9), bg=BG, fg=MUTED)
        self.url_lbl.pack()
        self._refresh_qr()

        prod = tk.Frame(r, bg=PANEL, padx=12, pady=8)
        prod.pack(fill="x", padx=20, pady=(12, 0))
        tk.Label(prod, text="Tabulka produktů", font=("Segoe UI Semibold", 10), bg=PANEL, fg=FG).pack(anchor="w")
        self.prod_lbl = tk.Label(prod, font=("Segoe UI", 9), bg=PANEL, fg=MUTED, wraplength=420, justify="left")
        self.prod_lbl.pack(anchor="w")
        buttons = tk.Frame(prod, bg=PANEL)
        buttons.pack(anchor="w", pady=(6, 0))
        button = dict(font=("Segoe UI", 9), bg=BG, fg=FG, activebackground=BG, activeforeground=FG,
                      relief="flat", padx=10, pady=2, cursor="hand2")
        tk.Button(buttons, text="Vybrat tabulku…", command=self.choose_products, **button).pack(side="left")
        self.amb_btn = tk.Button(buttons, text="Sporné EANy", command=self.show_ambiguous, **button)
        self.name_var = tk.BooleanVar(value=self.cfg["write_name"])
        self.name_chk = tk.Checkbutton(buttons, text="Vepisovat název místo EANu", variable=self.name_var,
                                       command=lambda: self._set("write_name", self.name_var.get()),
                                       font=("Segoe UI", 9), bg=PANEL, fg=FG, selectcolor=BG,
                                       activebackground=PANEL, activeforeground=FG)
        self.name_chk.pack(side="left", padx=(10, 0))

        self.last_lbl = tk.Label(r, text="Zatím nic nenaskenováno", font=("Segoe UI", 11),
                                 bg=BG, fg=MUTED, wraplength=440)
        self.last_lbl.pack(pady=(10, 4))
        tk.Label(r, text=f"PC: {socket.gethostname()} · verze {__version__} · spojení je šifrované end-to-end",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack()
        tk.Label(r, text="Zavřením okna agent běží dál v oznamovací oblasti (u hodin).",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(pady=(0, 14))
        self._update_status()
        # Párovací QR (= klíč) ukázat po startu jen dokud se nepřipojil žádný telefon.
        # Jinak by se objevoval při každém přihlášení, třeba i při sdílení obrazovky.
        if not self.cfg["paired"]:
            r.deiconify()

    def _refresh_qr(self):
        if not self.cfg["relay_url"]:
            self.qr_lbl.configure(image="", text="Není nastavená adresa serveru (relay_url v data\\config.json).",
                                  fg=WARN, font=("Segoe UI", 10))
            return
        photo = ImageTk.PhotoImage(qr_image(self.cfg.pairing_url()))
        self.qr_lbl.configure(image=photo)
        self.qr_lbl.image = photo
        self.url_lbl.configure(text=urlparse(self.cfg["relay_url"]).netloc)  # klíč se nezobrazuje

    def _update_status(self):
        if not self.cfg["relay_url"]:
            text, color = "✕ Server není nastavený", WARN
        elif not self.connected:
            text, color = "○ Připojuji k serveru…", WARN
        elif self.client.paused:
            text, color = "⏸ Příjem pozastaven", WARN
        elif self.clients:
            text, color = f"● Připojené telefony: {self.clients}", ACCENT
        else:
            text, color = "○ Připraveno, čekám na telefon", MUTED
        self.status_lbl.configure(text=text, fg=color)
        if hasattr(self, "icon"):
            self.icon.title = f"EAN agent – {text[2:]}"

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_window(self):
        self.root.withdraw()

    # ---------- tray ----------
    def _build_tray(self):
        ui = lambda fn: (lambda icon, item: self.events.put(("ui", fn)))  # noqa: E731

        def radio(key, value, label):
            return pystray.MenuItem(label, ui(lambda: self._set(key, value)),
                                    checked=lambda item: self.cfg[key] == value, radio=True)

        menu = pystray.Menu(
            pystray.MenuItem("Zobrazit párovací QR", ui(self.show_window), default=True),
            pystray.MenuItem("Pozastavit příjem", ui(self.toggle_pause),
                             checked=lambda item: self.client.paused),
            pystray.MenuItem("Po vepsání kódu", pystray.Menu(
                radio("suffix", "none", "Nic nestisknout"),
                radio("suffix", "enter", "Stisknout Enter"),
                radio("suffix", "tab", "Stisknout Tab"),
            )),
            pystray.MenuItem("Způsob psaní", pystray.Menu(
                radio("typing_mode", "unicode", "Znaky (výchozí)"),
                radio("typing_mode", "numpad", "Numerická klávesnice (vzdálená plocha)"),
                radio("typing_mode", "off", "Nepsat, jen zkopírovat do schránky"),
            )),
            pystray.MenuItem("Kopírovat kód do schránky (Ctrl+V)",
                             ui(lambda: self._set("clipboard", not self.cfg["clipboard"])),
                             checked=lambda item: self.cfg["clipboard"]),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Vepisovat název produktu místo EANu",
                             ui(lambda: self._set("write_name", not self.cfg["write_name"])),
                             checked=lambda item: self.cfg["write_name"],
                             enabled=lambda item: bool(self.cfg["products_file"])),
            pystray.MenuItem("Vybrat tabulku produktů…", ui(self.choose_products)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Zrušit spárování všech telefonů", ui(self.reset_pairing)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Verze {__version__}" + (f" – {self.update_status}"
                                                                     if self.update_status else ""),
                             None, enabled=False),
            pystray.MenuItem("Zkontrolovat aktualizace", ui(lambda: self.check_updates(manual=True)),
                             visible=updater.can_update()),
            pystray.MenuItem("Ukončit", ui(self.quit)),
        )
        image = Image.open(self.res / "pwa" / "icons" / "icon-192.png")
        self.icon = pystray.Icon("EanAgent", image, "EAN agent", menu)
        self.icon.run_detached()
        self._update_status()

    def _set(self, key, value):
        self.cfg.set(key, value)
        self.icon.update_menu()
        if key == "write_name":
            self.name_var.set(value)

    # ---------- tabulka produktů ----------
    def choose_products(self):
        self.show_window()
        current = self.cfg["products_file"]
        path = filedialog.askopenfilename(
            parent=self.root, title="Tabulka produktů (EAN a název)",
            initialdir=str(Path(current).parent) if current else str(Path.home() / "Downloads"),
            filetypes=[("Tabulky", "*.xlsx *.xlsm *.csv"), ("Všechny soubory", "*.*")])
        if not path:
            return
        self.cfg.set("products_file", str(Path(path)))
        self._load_products(self.cfg["products_file"])
        self.icon.update_menu()

    def _load_products(self, path):
        """Načtení (u velkého Excelu i pár sekund) běží mimo UI vlákno."""
        self.prod_lbl.configure(text="Načítám tabulku…" if path else "", fg=MUTED)

        def work():
            self.products.set_path(path)
            self.events.put(("ui", self._refresh_products_ui))
        threading.Thread(target=work, daemon=True).start()

    def _check_products(self):
        """Hlídá změny souboru s tabulkou, aby se po uložení v Excelu hned použila nová data."""
        if self.stopped:
            return
        if self.cfg["products_file"]:
            def work():
                before = (self.products.count(), self.products.error)
                self.products.reload_if_changed()
                if (self.products.count(), self.products.error) != before:
                    self.events.put(("ui", self._refresh_products_ui))
            threading.Thread(target=work, daemon=True).start()
        self.root.after(PRODUCTS_CHECK_MS, self._check_products)

    def _refresh_products_ui(self):
        path = self.cfg["products_file"]
        ambiguous = self.products.ambiguous()
        if not path:
            text, color = "Není vybraná. Vepisuje se EAN.", MUTED
        elif self.products.error:
            text, color = f"{Path(path).name}: {self.products.error}. Vepisuje se EAN.", WARN
        else:
            text = f"{Path(path).name} · {self.products.count()} produktů"
            if ambiguous:
                text += f" · {len(ambiguous)} EANů s víc názvy (vepíše se u nich EAN)"
            color = ACCENT if self.cfg["write_name"] else MUTED
        self.prod_lbl.configure(text=text, fg=color)
        if ambiguous and not self.products.error:
            self.amb_btn.pack(side="left", padx=(8, 0), before=self.name_chk)
        else:
            self.amb_btn.pack_forget()
        self.name_chk.configure(state="normal" if path else "disabled")

    def show_ambiguous(self):
        items = self.products.ambiguous()
        win = tk.Toplevel(self.root)
        win.title("EANy s víc názvy")
        win.configure(bg=BG)
        tk.Label(win, text="U těchto EANů se vepíše EAN. Oprav je v tabulce a ulož, agent ji načte sám.",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED, wraplength=520, justify="left").pack(
            anchor="w", padx=12, pady=(10, 4))
        text = tk.Text(win, width=80, height=min(24, 3 * len(items) + 1), font=("Consolas", 9),
                       bg=PANEL, fg=FG, relief="flat", padx=8, pady=6)
        for ean, names in items:
            text.insert("end", ean + "\n" + "".join(f"   {n}\n" for n in names))
        text.configure(state="disabled")
        text.pack(padx=12, pady=(0, 12), fill="both", expand=True)

    def toggle_pause(self):
        self.client.set_paused(not self.client.paused)
        self._update_status()
        self.icon.update_menu()

    def reset_pairing(self):
        if not messagebox.askyesno("EAN agent", "Všechny spárované telefony se odpojí a bude potřeba "
                                                "znovu naskenovat párovací QR kód. Pokračovat?"):
            return
        self.cfg.new_pairing()
        self.client.reconnect()
        self._refresh_qr()
        self.show_window()

    # ---------- aktualizace ----------
    def _scheduled_update_check(self):
        if self.stopped:
            return
        self.check_updates(manual=False)
        self.root.after(UPDATE_CHECK_MS, self._scheduled_update_check)

    def check_updates(self, manual):
        """Kontrola a instalace běží ve vlákně, výsledky jdou do UI přes frontu událostí."""
        if self.updating:
            return
        self.updating = True
        self._set_update_status("kontroluji…")
        threading.Thread(target=self._update_worker, args=(manual,), daemon=True).start()

    def _update_worker(self, manual):
        post = lambda fn: self.events.put(("ui", fn))  # noqa: E731
        try:
            log.info("Kontrola aktualizací (verze %s, %s)", __version__, "ručně" if manual else "automaticky")
            found = updater.check()
            if not found:
                log.info("Aktualizace: žádná novější verze")
                post(lambda: self._update_done("aktuální", "Máte nejnovější verzi." if manual else None))
                return
            version, url, sha = found
            log.info("Aktualizace: nalezena %s, stahuji %s", version, url)
            post(lambda: self._set_update_status(f"stahuji {version}…"))

            def progress(pct):
                if pct % 10 == 0:
                    log.info("Aktualizace: staženo %d %%", pct)
                post(lambda: self._set_update_status(f"stahuji {version}… {pct} %"))
            path = updater.download(url, sha, progress)
            log.info("Aktualizace: staženo a ověřeno %s", path)
            post(lambda: self._install_update(path, version))
        except Exception as e:  # síť, GitHub, kontrolní součet – zkusí se příště
            log.exception("Aktualizace selhala")
            msg = f"Aktualizace se nezdařila: {e}"
            post(lambda: self._update_done("kontrola selhala", msg if manual else None))

    def _update_done(self, status, message):
        self.updating = False
        self._set_update_status(status)
        if message:
            self.icon.notify(message, "EAN agent")

    def _set_update_status(self, text):
        self.update_status = text
        self.icon.update_menu()

    def _install_update(self, path, version):
        self.icon.notify(f"Instaluji verzi {version}, agent se za chvíli sám znovu spustí.", "EAN agent")
        try:
            updater.run_installer(path)
        except OSError:
            log.exception("Instalátor nejde spustit")
            self._update_done("instalace selhala", "Instalátor aktualizace nejde spustit.")
            return
        log.info("Aktualizace: spuštěn instalátor %s, agent se ukončí", version)
        self.root.after(1500, self.quit)  # instalátor potřebuje, aby agent nebyl spuštěný

    def quit(self):
        self.stopped = True
        self.icon.stop()
        self.root.destroy()

    # ---------- události z klienta / tray ----------
    def _poll_events(self):
        try:
            while True:
                ev, data = self.events.get_nowait()
                if ev == "ui":
                    data()
                    if self.stopped:
                        return
                elif ev == "connected":
                    self.connected = data
                    self._update_status()
                elif ev == "clients":
                    self.clients = data
                    self._update_status()
                    if data and not self.cfg["paired"]:
                        self.cfg.set("paired", True)
                elif ev == "scan":
                    where = f" → {data['target']}" if data["target"] else ""
                    what = f"{data['code']} = {data['name']}" if data.get("name") else data["code"]
                    note = f"\n⚠ {data['warn']}" if data.get("warn") else ""
                    if data.get("lot"):
                        note += f"\nŠarže {data['lot']}" + (" je ve schránce (Ctrl+V)" if data.get("lot_copied") else "")
                    self.last_lbl.configure(text=f"Poslední kód: {what}{where}{note}",
                                            fg=WARN if data.get("warn") else FG)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def run(self):
        self.root.mainloop()


def single_instance():
    """Dva agenti by se u relay navzájem odpojovali – druhý se proto neotevře."""
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\EanAgent-single-instance")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("EAN agent", "EAN agent už běží – najdeš ho v oznamovací oblasti u hodin.")
        sys.exit(0)
    return handle


def setup_logging():
    """Log do data\\agent.log (max. ~1 MB) – bez kódů ani názvů produktů, jen provoz a chyby."""
    from logging.handlers import RotatingFileHandler
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(DATA_DIR / "agent.log", maxBytes=512_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    def hook(exc_type, exc, tb):
        log.critical("Neošetřená chyba", exc_info=(exc_type, exc, tb))
    sys.excepthook = hook
    threading.excepthook = lambda args: hook(args.exc_type, args.exc_value, args.exc_traceback)


if __name__ == "__main__":
    try:  # ostré QR kódy na monitorech s větším měřítkem
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    setup_logging()
    _mutex = single_instance()
    log.info("Start agenta %s (%s)", __version__, sys.executable)
    try:
        App().run()
    except Exception:
        log.exception("Agent spadl")
        raise
    log.info("Agent ukončen")
