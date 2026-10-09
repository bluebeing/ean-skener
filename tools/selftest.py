"""Test běžícího agenta přes relay: Python se chová jako telefon.

Spuštění (agent musí běžet a být připojený k relay):
    python tools/selftest.py                # relay z data/config.json
    python tools/selftest.py http://localhost:8787
"""
import asyncio
import json
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import typer  # noqa: E402
from config import Config  # noqa: E402
from crypto_box import Box, new_key  # noqa: E402

cfg = Config()
RELAY = (sys.argv[1] if len(sys.argv) > 1 else cfg["relay_url"]).rstrip("/")
WS = RELAY.replace("https://", "wss://").replace("http://", "ws://")
box = Box(cfg["room"], cfg["key"])
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("OK   " if ok else "FAIL ") + name + (f" – {detail}" if detail else ""))


RUN = new_key()[:8]  # agent si pamatuje ID zpráv, každý běh testu musí mít vlastní


def sealed(obj, b=box, ts=None):
    obj = {**obj, "id": f"{RUN}-{obj['id']}", "ts": ts or int(time.time() * 1000)}
    return json.dumps({"t": "msg", "d": b.seal(obj, "p2c")})


async def next_msg(ws, want="ack", timeout=3.0):
    """Další dešifrovaná zpráva daného typu od PC (ostatní přeskočí); None = nic nepřišlo."""
    deadline = time.monotonic() + timeout
    while (left := deadline - time.monotonic()) > 0:
        try:
            msg = await ws.receive(timeout=left)
        except asyncio.TimeoutError:
            return None
        if msg.type != aiohttp.WSMsgType.TEXT:
            return None
        data = json.loads(msg.data)
        if data.get("t") == "msg":
            inner = box.open(data["d"], "c2p")
            if inner and inner.get("type") == want:
                return inner
    return None


def test_window_focused():
    return typer.foreground_title() == "EAN selftest"


async def run(entry_value, clipboard_value):
    async with aiohttp.ClientSession() as s:
        async with s.get(RELAY + "/") as r:
            check("PWA se načte z relay", r.status == 200 and "EAN Skener" in await r.text(), str(r.status))
        async with s.get(RELAY + "/ws/kratke?role=phone", headers={"Upgrade": "websocket"}) as r:
            check("neplatná místnost odmítnuta", r.status == 400, str(r.status))

        async with s.ws_connect(f"{WS}/ws/{cfg['room']}?role=phone") as ws:
            peer = json.loads((await ws.receive(timeout=5)).data)
            check("relay hlásí připojené PC", peer.get("t") == "peer" and peer.get("pc") is True, json.dumps(peer))

            await ws.send_str(sealed({"type": "hello", "id": "h1"}))
            status = await next_msg(ws, want="status")
            check("zašifrovaný status od PC", bool(status) and status.get("type") == "status", json.dumps(status))

            await ws.send_str(sealed({"type": "scan", "code": "4006381333932", "id": "s1"}))
            ack = await next_msg(ws)
            check("špatná kontrolní číslice odmítnuta", bool(ack) and ack["ok"] is False, (ack or {}).get("error", ""))

            wrong = Box(cfg["room"], new_key())
            await ws.send_str(sealed({"type": "scan", "code": "4006381333931", "id": "s2"}, b=wrong))
            check("zpráva s cizím klíčem ignorována", await next_msg(ws, timeout=2) is None)

            old = int(time.time() * 1000) - 5 * 60 * 1000
            await ws.send_str(sealed({"type": "scan", "code": "4006381333931", "id": "s3"}, ts=old))
            check("stará zpráva (replay) ignorována", await next_msg(ws, timeout=2) is None)
            check("nic se zatím nevepsalo", entry_value() == "", repr(entry_value()))

            # platný kód se opravdu vepíše do okna s fokusem – poslat jen, když je to testovací okno
            if not test_window_focused():
                print(f"SKIP vepsání – fokus má jiné okno ({typer.foreground_title()!r}), kód se neposílá")
                return
            msg = sealed({"type": "scan", "code": "4006381333931", "id": "s4"})
            await ws.send_str(msg)
            ack = await next_msg(ws, timeout=5)
            check("platný kód přijat", bool(ack) and ack["ok"] is True, f"okno: {(ack or {}).get('target')}")
            await asyncio.sleep(0.5)
            check("kód vepsán do testovacího okna", entry_value() == "4006381333931", repr(entry_value()))
            if cfg["clipboard"]:
                check("kód ve schránce", clipboard_value() == "4006381333931", repr(clipboard_value()))

            await ws.send_str(msg)
            check("stejná zpráva podruhé ignorována", await next_msg(ws, timeout=2) is None)
            check("vepsáno jen jednou", entry_value() == "4006381333931", repr(entry_value()))


def main():
    root = tk.Tk()
    root.title("EAN selftest")
    entry = tk.Entry(root, font=("Consolas", 16), width=20)
    entry.pack(padx=20, pady=20)
    root.attributes("-topmost", True)
    root.after(300, lambda: (root.focus_force(), entry.focus_set()))
    values = {"v": "", "clip": ""}

    def poll():
        values["v"] = entry.get()
        try:
            values["clip"] = root.clipboard_get()
        except tk.TclError:
            values["clip"] = ""
        root.after(50, poll)

    def worker():
        time.sleep(1.2)
        try:
            asyncio.run(run(lambda: values["v"], lambda: values["clip"]))
        finally:
            root.after(0, root.destroy)

    poll()
    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()
    print(f"\n{sum(results)}/{len(results)} testů prošlo")
    sys.exit(0 if results and all(results) else 1)


if __name__ == "__main__":
    main()
