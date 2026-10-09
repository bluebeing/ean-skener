"""EAN agent: přijímá kódy z telefonu (přes šifrovaný relay) a vepisuje je do aktivního okna."""
import ctypes
import queue
import socket
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlparse

import pystray
import qrcode
from PIL import Image, ImageTk

from config import Config, resource_dir
from relay_client import RelayClient

BG, FG, MUTED, ACCENT, WARN = "#0f1115", "#e8eaed", "#9aa0a6", "#3ddc84", "#fbbc04"


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

        self.root = tk.Tk()
        self.root.withdraw()
        self.client = RelayClient(self.cfg, lambda ev, data: self.events.put((ev, data)))
        self._build_window()
        self._build_tray()
        if self.cfg["relay_url"]:
            self.client.start()
        self.root.after(150, self._poll_events)

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

        self.last_lbl = tk.Label(r, text="Zatím nic nenaskenováno", font=("Segoe UI", 11),
                                 bg=BG, fg=MUTED, wraplength=440)
        self.last_lbl.pack(pady=(10, 4))
        tk.Label(r, text=f"PC: {socket.gethostname()} · spojení je šifrované end-to-end",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack()
        tk.Label(r, text="Zavřením okna agent běží dál v oznamovací oblasti (u hodin).",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(pady=(0, 14))
        self._update_status()
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
            pystray.MenuItem("Zrušit spárování všech telefonů", ui(self.reset_pairing)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Ukončit", ui(self.quit)),
        )
        image = Image.open(self.res / "pwa" / "icons" / "icon-192.png")
        self.icon = pystray.Icon("EanAgent", image, "EAN agent", menu)
        self.icon.run_detached()
        self._update_status()

    def _set(self, key, value):
        self.cfg.set(key, value)
        self.icon.update_menu()

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
                elif ev == "scan":
                    where = f" → {data['target']}" if data["target"] else ""
                    self.last_lbl.configure(text=f"Poslední kód: {data['code']}{where}", fg=FG)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:  # ostré QR kódy na monitorech s větším měřítkem
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    App().run()
