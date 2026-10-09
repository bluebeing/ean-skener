"""Spojení agenta s relay serverem: přijímá šifrované kódy z telefonu a vepisuje je."""
import asyncio
import json
import socket
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import aiohttp

import typer
from crypto_box import Box, valid_code

MAX_AGE_S = 60  # starší zprávy se zahodí (ochrana proti přehrání)


class RelayClient:
    def __init__(self, cfg, on_event):
        self.cfg = cfg
        self.on_event = on_event  # callback(event:str, data) – volá se z vlákna klienta
        self.paused = False
        self.connected = False
        self.phones = 0
        self.ws = None
        self.loop = asyncio.new_event_loop()
        # jediné vlákno => kódy z více telefonů se nikdy nepromíchají
        self.typing = ThreadPoolExecutor(max_workers=1)
        self.seen = OrderedDict()  # id zpráv pro odmítnutí duplicit
        self._reconnect = None

    # ---------- spuštění ----------
    def start(self):
        threading.Thread(target=self._run, daemon=True, name="relay-client").start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self._reconnect = asyncio.Event()
        self.loop.run_until_complete(self._main())

    def url(self):
        base = self.cfg["relay_url"].rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        return f"{base}/ws/{self.cfg['room']}?role=pc"

    async def _main(self):
        delay = 1
        async with aiohttp.ClientSession() as session:
            while True:
                self._reconnect.clear()
                self.box = Box(self.cfg["room"], self.cfg["key"])
                try:
                    async with session.ws_connect(self.url(), heartbeat=25) as ws:
                        self.ws = ws
                        self._set_connected(True)
                        delay = 1
                        await self._receive(ws)
                except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as e:
                    self.on_event("error", str(e))
                finally:
                    self.ws = None
                    self._set_connected(False)
                try:  # čekat na další pokus, nebo na okamžité přepojení (nové spárování)
                    await asyncio.wait_for(self._reconnect.wait(), delay)
                    delay = 1
                except asyncio.TimeoutError:
                    delay = min(delay * 2, 30)

    async def _receive(self, ws):
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except ValueError:
                continue
            if data.get("t") == "peer":
                phones = int(data.get("phones", 0))
                if phones > self.phones:
                    await self._send_status()
                self.phones = phones
                self.on_event("clients", phones)
            elif data.get("t") == "msg":
                inner = self.box.open(str(data.get("d", "")), "p2c")
                if inner is None or not self._fresh(inner):
                    continue  # cizí, poškozená nebo přehraná zpráva
                if inner.get("type") == "scan":
                    await self._send(await self._handle_scan(inner))
                elif inner.get("type") == "hello":
                    await self._send_status()

    def _fresh(self, inner) -> bool:
        msg_id = str(inner.get("id", ""))
        ts = inner.get("ts")
        if not msg_id or not isinstance(ts, (int, float)) or abs(time.time() * 1000 - ts) > MAX_AGE_S * 1000:
            return False
        if msg_id in self.seen:
            return False
        self.seen[msg_id] = True
        while len(self.seen) > 500:
            self.seen.popitem(last=False)
        return True

    async def _handle_scan(self, inner):
        code = str(inner.get("code", "")).strip()
        ack = {"type": "ack", "id": inner.get("id"), "code": code}
        if not valid_code(code):
            return {**ack, "ok": False, "error": "Neplatný EAN kód"}
        if self.paused:
            return {**ack, "ok": False, "error": "Příjem na PC je pozastaven"}
        try:
            target = await self.loop.run_in_executor(
                self.typing, typer.type_code, code,
                self.cfg["typing_mode"], self.cfg["suffix"], self.cfg["key_delay_ms"],
                self.cfg["clipboard"])
        except OSError as e:
            return {**ack, "ok": False, "error": str(e)}
        self.on_event("scan", {"code": code, "target": target})
        return {**ack, "ok": True, "target": target}

    async def _send(self, obj):
        if self.ws is None or self.ws.closed:
            return
        obj = {**obj, "ts": int(time.time() * 1000)}
        try:
            await self.ws.send_str(json.dumps({"t": "msg", "d": self.box.seal(obj, "c2p")}))
        except (ConnectionError, RuntimeError):
            pass

    async def _send_status(self):
        await self._send({"type": "status", "paused": self.paused, "pc": socket.gethostname()})

    def _set_connected(self, value):
        if self.connected != value:
            self.connected = value
            if not value:
                self.phones = 0
                self.on_event("clients", 0)
            self.on_event("connected", value)

    # ---------- ovládání z UI vlákna ----------
    def set_paused(self, paused: bool):
        self.paused = paused
        asyncio.run_coroutine_threadsafe(self._send_status(), self.loop)

    def reconnect(self):
        """Přepojení s novým room/klíčem (po zrušení spárování) nebo jinou adresou relay."""
        async def go():
            if self.ws is not None:
                await self.ws.close()
            self._reconnect.set()
        asyncio.run_coroutine_threadsafe(go(), self.loop)
