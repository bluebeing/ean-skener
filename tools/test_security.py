"""Bezpečnostní testy (nic nevepisuje ani neinstaluje).

    python tools/test_security.py [http://127.0.0.1:8787]   # s adresou otestuje i limity relay
"""
import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from products import _clean_name  # noqa: E402
from relay_client import RelayClient  # noqa: E402
from sign_release import signed_message  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("OK   " if ok else "FAIL ") + name + (f" – {detail}" if detail else ""))


def rejected(fn):
    try:
        fn()
        return False
    except updater.UpdateRejected:
        return True


# ---------- podpis aktualizací ----------
key = Ed25519PrivateKey.generate()
pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                     serialization.PublicFormat.Raw)).decode()
name, sha = "EanAgent-Setup-9.9.9.exe", hashlib.sha256(b"instalator").hexdigest()
good = base64.b64encode(key.sign(signed_message(name, sha))).decode()
check("platný podpis projde", not rejected(lambda: updater.verify_signature(name, sha, good, pub)))
check("podpis jiného souboru neprojde", rejected(lambda: updater.verify_signature(name, "0" * 64, good, pub)))
check("podpis jiné verze neprojde",
      rejected(lambda: updater.verify_signature("EanAgent-Setup-9.9.8.exe", sha, good, pub)))
other = base64.b64encode(Ed25519PrivateKey.generate().sign(signed_message(name, sha))).decode()
check("podpis cizím klíčem neprojde", rejected(lambda: updater.verify_signature(name, sha, other, pub)))
check("rozbitý podpis neprojde", rejected(lambda: updater.verify_signature(name, sha, "!!!", pub)))
check("podpis sign_release.py = ověření v agentovi", signed_message(name, sha) == updater.signed_message(name, sha))

# ---------- podvržené vydání (simulace odpovědi GitHub API) ----------
TAG = "v9.9.9"
BASE = f"https://github.com/bluebeing/ean-skener/releases/download/{TAG}/"


def release(assets):
    return json.dumps({"tag_name": TAG, "assets": assets}).encode()


def asset(n, url=None, digest=None):
    a = {"name": n, "browser_download_url": url or BASE + n}
    if digest:
        a["digest"] = "sha256:" + digest
    return a


def run_check(api_body, files=None):
    files = files or {}
    real_get = updater._get
    updater._get = lambda url, timeout=20: api_body if url == updater.API_LATEST else files[url]
    try:
        return updater.check()
    finally:
        updater._get = real_get


sig = base64.b64encode(key.sign(signed_message(name, sha))).decode().encode()
updater_key = updater.RELEASE_PUBLIC_KEY
updater.RELEASE_PUBLIC_KEY = pub
verify = updater.verify_signature
updater.verify_signature = lambda n, s, g, p=None: verify(n, s, g, pub)
try:
    ok = run_check(release([asset(name, digest=sha), asset(name + ".sig")]), {BASE + name + ".sig": sig})
    check("podepsané vydání projde kontrolou", ok == ("9.9.9", BASE + name, sha), str(ok))
    check("vydání bez podpisu se odmítne",
          rejected(lambda: run_check(release([asset(name, digest=sha)]))))
    check("cizí adresa instalátoru se odmítne", rejected(lambda: run_check(release(
        [asset(name, url="https://evil.example/" + name, digest=sha), asset(name + ".sig")]),
        {BASE + name + ".sig": sig})))
    check("instalátor jiné verze než tag se odmítne", rejected(lambda: run_check(release(
        [asset("EanAgent-Setup-9.9.8.exe", digest=sha), asset("EanAgent-Setup-9.9.8.exe.sig")]))))
finally:
    updater.RELEASE_PUBLIC_KEY = updater_key
    updater.verify_signature = verify
check("stažení s ..\\ v adrese se odmítne", rejected(lambda: updater.download(
    BASE + "..\\..\\Startup\\EanAgent-Setup-9.9.9.exe", sha)))
check("v agentovi je zabudovaný veřejný klíč", len(base64.b64decode(updater.RELEASE_PUBLIC_KEY)) == 32)

# ---------- názvy z tabulky ----------
check("řídicí znaky z názvu pryč", _clean_name("Čaj\tzelený\r\n‮abc") == "Čaj zelený abc",
      repr(_clean_name("Čaj\tzelený\r\n‮abc")))
check("dlouhý název zkrácen", len(_clean_name("x" * 10_000)) == 200)

# ---------- odolnost agenta vůči vadným zprávám ----------
client = RelayClient({"room": "A" * 22, "key": base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")},
                     lambda *a: None)
from crypto_box import Box  # noqa: E402

client.box = Box("A" * 22, base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="))
sent = []


async def fake_send(obj):
    sent.append(obj)
client._send = fake_send
client._send_status = lambda: fake_send({"type": "status"})


async def feed():
    bad = [[], "x", {"t": "peer", "phones": "hodně"}, {"t": "peer", "phones": 10 ** 9}, {"t": "msg", "d": 5},
           {"t": "msg", "d": client.box.seal({"type": "scan", "code": ["8594001234561"], "id": "1",
                                              "ts": __import__("time").time() * 1000}, "p2c")},
           {"t": "msg", "d": client.box.seal({"type": "scan", "code": "8594001234561", "id": {"x": 1},
                                              "ts": 1}, "p2c")}]
    errors = 0
    for m in bad:
        try:
            await client._handle_message(m)
        except Exception:
            errors += 1
    return errors

check("vadné zprávy nevyhodí výjimku", asyncio.run(feed()) == 0)
check("nesmyslný počet telefonů ignorován", client.phones == 0, str(client.phones))
check("sken s polem místo kódu odmítnut", any(s.get("ok") is False for s in sent), json.dumps(sent))

# ---------- limity relay (volitelně proti běžícímu wrangler dev) ----------
if len(sys.argv) > 1:
    import aiohttp

    async def relay_limits(base):
        ws_base = base.replace("http", "ws")
        room = "L" * 22
        async with aiohttp.ClientSession() as s:
            sockets = []
            for _ in range(10):
                sockets.append(await s.ws_connect(f"{ws_base}/ws/{room}?role=phone"))
            try:
                await s.ws_connect(f"{ws_base}/ws/{room}?role=phone")
                over = None
            except aiohttp.WSServerHandshakeError as e:
                over = e.status
            for w in sockets:
                await w.close()
            async with s.get(f"{base}/ws/{room}?role=admin", headers={"Upgrade": "websocket"}) as r:
                bad_role = r.status
            return over, bad_role

    over, bad_role = asyncio.run(relay_limits(sys.argv[1].rstrip("/")))
    check("relay: 11. telefon v místnosti odmítnut", over == 429, str(over))
    check("relay: neplatná role odmítnuta", bad_role == 400, str(bad_role))

print(f"\n{sum(results)}/{len(results)} testů prošlo")
sys.exit(0 if all(results) else 1)
