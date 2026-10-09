'use strict';

const EAN_FORMATS = ['ean_13', 'ean_8', 'upc_a'];
const SAME_CODE_COOLDOWN_MS = 2000;
const SCAN_INTERVAL_MS = 120;
const HISTORY_SIZE = 5;
const $ = (id) => document.getElementById(id);

const state = {
  pair: null, // { room, key } z párovacího QR kódu
  cryptoKey: null,
  ws: null,
  pcOnline: false, // PC je připojené k serveru
  connected: false, // PC potvrdilo spojení zašifrovaným statusem
  paused: false,
  helloTimer: null,
  retryMs: 1000,
  stream: null,
  detector: null,
  detectorMode: null, // 'ean' | 'pair'
  mode: 'ean',
  loopTimer: null,
  lastCode: null,
  lastCodeAt: 0,
  pending: new Map(), // id -> záznam historie
  history: [],
  audio: null,
  wakeLock: null,
  torch: false,
};

// ---------- úložiště ----------
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* soukromý režim */ } },
};

// ---------- EAN ----------
function eanValid(code) {
  if (!/^(\d{8}|\d{12}|\d{13})$/.test(code)) return false;
  const d = code.split('').map(Number);
  const check = d.pop();
  let sum = 0;
  d.reverse().forEach((n, i) => { sum += n * (i % 2 === 0 ? 3 : 1); });
  return (10 - (sum % 10)) % 10 === check;
}

// ---------- zvuk / vibrace ----------
function beep(ok) {
  try {
    if (!state.audio) return;
    const ctx = state.audio, osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.frequency.value = ok ? 1800 : 320;
    osc.type = ok ? 'sine' : 'square';
    gain.gain.value = 0.15;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + (ok ? 0.08 : 0.25));
  } catch (e) { /* bez zvuku */ }
  if (navigator.vibrate) navigator.vibrate(ok ? 60 : [80, 60, 80]);
}

function flash(ok) {
  const f = $('flash');
  f.className = 'flash ' + (ok ? 'ok' : 'err');
  requestAnimationFrame(() => requestAnimationFrame(() => { f.className = 'flash'; }));
}

// ---------- spojení s PC ----------
function setConn(cls, text) {
  $('conn').className = 'conn ' + cls;
  $('connText').textContent = text;
}

// ---------- šifrování (AES-256-GCM, klíč zná jen telefon a PC) ----------
const enc = new TextEncoder();
const dec = new TextDecoder();

function b64d(s) {
  s = s.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

function b64e(bytes) {
  let s = '';
  bytes.forEach((b) => { s += String.fromCharCode(b); });
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function seal(obj) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: enc.encode(state.pair.room + 'p2c') },
    state.cryptoKey, enc.encode(JSON.stringify({ ...obj, ts: Date.now() }))));
  const out = new Uint8Array(12 + ct.length);
  out.set(iv);
  out.set(ct, 12);
  return b64e(out);
}

async function unseal(text) {
  try {
    const raw = b64d(text);
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: raw.slice(0, 12), additionalData: enc.encode(state.pair.room + 'c2p') },
      state.cryptoKey, raw.slice(12));
    return JSON.parse(dec.decode(plain));
  } catch (e) {
    return null; // zpráva není od našeho PC
  }
}

// ---------- párování ----------
function parsePairing(hash) {
  const r = hash.match(/[#&]r=([A-Za-z0-9_-]{22,64})/);
  const k = hash.match(/[#&]k=([A-Za-z0-9_-]{43})/);
  return r && k ? { room: r[1], key: k[1] } : null;
}

async function setPairing(pair) {
  state.pair = pair;
  state.cryptoKey = pair
    ? await crypto.subtle.importKey('raw', b64d(pair.key), 'AES-GCM', false, ['encrypt', 'decrypt'])
    : null;
}

function readPairing() {
  const fromUrl = parsePairing(location.hash);
  if (fromUrl) {
    store.set('ean.pair', JSON.stringify(fromUrl));
    history.replaceState(null, '', location.pathname); // klíč nenechávat v adrese
    return fromUrl;
  }
  try { return JSON.parse(store.get('ean.pair')); } catch (e) { return null; }
}

// ---------- spojení přes relay server ----------
function connect() {
  if (!state.pair) {
    setConn('err', 'Nespárováno');
    showPairing(true);
    return;
  }
  if (state.ws && state.ws.readyState <= 1) return;
  setConn('warn', 'Připojuji k serveru…');
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/${state.pair.room}?role=phone`);
  state.ws = ws;
  ws.onopen = () => { state.retryMs = 1000; };
  ws.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.t === 'peer') {
      onPeer(msg.pc);
    } else if (msg.t === 'msg') {
      const inner = await unseal(String(msg.d || ''));
      if (!inner) return;
      if (inner.type === 'status') onStatus(inner);
      else if (inner.type === 'ack') onAck(inner);
    }
  };
  ws.onclose = () => {
    if (state.ws !== ws) return; // nahrazeno novým spojením
    state.ws = null;
    state.pcOnline = false;
    state.connected = false;
    clearTimeout(state.helloTimer);
    failPending('Spojení přerušeno');
    setConn('err', 'Bez spojení se serverem – zkouším znovu…');
    setTimeout(connect, state.retryMs);
    state.retryMs = Math.min(state.retryMs * 2, 10000);
  };
}

function reconnect() {
  const old = state.ws;
  state.ws = null;
  state.pcOnline = false;
  state.connected = false;
  if (old) old.close();
  connect();
}

function onPeer(pcOnline) {
  const wasOnline = state.pcOnline;
  state.pcOnline = pcOnline;
  if (!pcOnline) {
    state.connected = false;
    clearTimeout(state.helloTimer);
    setConn('err', 'PC je offline – spusťte na PC EAN agenta');
    return;
  }
  if (!wasOnline || !state.connected) sendHello();
}

// Požádá PC o status. Když nepřijde odpověď, kterou jde dešifrovat, PC má jiný klíč.
async function sendHello() {
  if (!state.ws || state.ws.readyState !== 1) return;
  setConn('warn', 'Ověřuji spojení s PC…');
  state.ws.send(JSON.stringify({ t: 'msg', d: await seal({ type: 'hello', id: randomId() }) }));
  clearTimeout(state.helloTimer);
  state.helloTimer = setTimeout(() => {
    if (state.pcOnline && !state.connected) {
      setConn('err', 'Neplatné spárování – naskenujte nový QR kód z PC');
      showPairing(true);
    }
  }, 5000);
}

function onStatus(msg) {
  clearTimeout(state.helloTimer);
  state.connected = true;
  state.paused = msg.paused;
  showPairing(false);
  setConn(msg.paused ? 'warn' : 'ok', msg.paused ? `${msg.pc}: příjem pozastaven` : `Připojeno k ${msg.pc}`);
}

function randomId() {
  return b64e(crypto.getRandomValues(new Uint8Array(9)));
}

async function sendCode(code) {
  const entry = { code, id: randomId(), status: 'pending', at: Date.now() };
  addHistory(entry);
  showLast(code, 'Odesílám…', '');
  if (!state.ws || state.ws.readyState !== 1 || !state.connected) {
    entry.status = 'err';
    entry.info = state.pcOnline ? 'Neodesláno – PC ještě neověřeno' : 'Neodesláno – PC je offline';
    renderHistory();
    showLast(code, entry.info, 'err');
    beep(false); flash(false);
    return;
  }
  state.pending.set(entry.id, entry);
  state.ws.send(JSON.stringify({ t: 'msg', d: await seal({ type: 'scan', code, id: entry.id }) }));
  entry.timer = setTimeout(() => {
    if (state.pending.delete(entry.id)) {
      entry.status = 'err'; entry.info = 'PC neodpovědělo';
      renderHistory(); showLast(code, entry.info, 'err'); beep(false);
    }
  }, 5000);
}

function onAck(msg) {
  const entry = state.pending.get(msg.id);
  if (!entry) return;
  state.pending.delete(msg.id);
  clearTimeout(entry.timer);
  entry.status = msg.ok ? 'ok' : 'err';
  entry.info = msg.ok ? (msg.target ? `Vepsáno → ${msg.target}` : 'Vepsáno') : msg.error;
  renderHistory();
  showLast(entry.code, entry.info, entry.status);
  beep(msg.ok); flash(msg.ok);
}

function failPending(reason) {
  state.pending.forEach((entry) => {
    clearTimeout(entry.timer);
    entry.status = 'err'; entry.info = reason;
  });
  if (state.pending.size) renderHistory();
  state.pending.clear();
}

// ---------- UI ----------
function showLast(code, info, cls) {
  $('last').className = 'last ' + (cls || '');
  $('lastCode').textContent = code;
  $('lastInfo').textContent = info;
}

function addHistory(entry) {
  state.history.unshift(entry);
  state.history = state.history.slice(0, HISTORY_SIZE);
  renderHistory();
}

function renderHistory() {
  const ul = $('history');
  ul.textContent = '';
  state.history.forEach((e) => {
    const li = document.createElement('li');
    li.className = e.status;
    const time = new Date(e.at).toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const code = document.createElement('span');
    code.className = 'code'; code.textContent = e.code;
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = (e.status === 'pending' ? '…' : e.status === 'ok' ? '✓ ' : '✗ ') + time;
    li.append(code, meta);
    li.onclick = () => { unlockAudio(); sendCode(e.code); };
    ul.appendChild(li);
  });
  store.set('ean.history', JSON.stringify(state.history.map(({ code, status, at, info }) =>
    ({ code, status: status === 'pending' ? 'err' : status, at, info }))));
}

function showPairing(needed) {
  $('pairBtn').hidden = !needed;
  if (needed && !state.stream) {
    $('placeholderText').textContent = 'Telefon není spárovaný s PC. Klepněte na „Naskenovat párovací QR“ a namiřte na QR kód v okně EAN agenta na PC.';
  }
}

// ---------- kamera a detekce ----------
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error('Nelze načíst ' + src));
    document.head.appendChild(s);
  });
}

async function createDetector(formats) {
  if ('BarcodeDetector' in window) {
    try {
      const supported = await window.BarcodeDetector.getSupportedFormats();
      if (formats.every((f) => supported.includes(f))) return new window.BarcodeDetector({ formats });
    } catch (e) { /* použije se ZXing */ }
  }
  if (!window.BarcodeDetectionAPI) {
    await loadScript('vendor/barcode-detector.js');
    const wasmUrl = new URL('vendor/zxing_reader.wasm', location.href).href;
    window.BarcodeDetectionAPI.setZXingModuleOverrides({
      locateFile: (path, prefix) => (path.endsWith('.wasm') ? wasmUrl : prefix + path),
    });
  }
  return new window.BarcodeDetectionAPI.BarcodeDetector({ formats });
}

async function startCamera() {
  unlockAudio();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $('placeholderText').textContent = 'Kamera není v tomto prohlížeči dostupná.';
    return;
  }
  try {
    $('placeholderText').textContent = 'Spouštím kameru…';
    state.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
    });
  } catch (e) {
    $('placeholderText').textContent = 'Kameru se nepodařilo spustit: ' + (e.name === 'NotAllowedError'
      ? 'přístup ke kameře byl odepřen. Povolte ho v nastavení prohlížeče.' : e.message);
    return;
  }
  const video = $('video');
  video.srcObject = state.stream;
  try { await video.play(); } catch (e) { /* autoplay je muted */ }

  const track = state.stream.getVideoTracks()[0];
  const caps = track.getCapabilities ? track.getCapabilities() : {};
  if (caps.focusMode && caps.focusMode.includes('continuous')) {
    track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(() => {});
  }
  $('torchBtn').hidden = !caps.torch;
  state.torch = false;
  $('torchBtn').classList.remove('on');

  $('placeholder').hidden = true;
  $('guide').hidden = false;
  $('stopBtn').hidden = false;
  requestWakeLock();
  scheduleScan(0);
}

function stopCamera() {
  clearTimeout(state.loopTimer);
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
  state.stream = null;
  $('video').srcObject = null;
  $('placeholder').hidden = false;
  $('placeholderText').textContent = 'Kamera je vypnutá';
  $('guide').hidden = true;
  $('stopBtn').hidden = true;
  $('torchBtn').hidden = true;
  if (state.wakeLock) { state.wakeLock.release().catch(() => {}); state.wakeLock = null; }
  showPairing(!state.pair || state.mode === 'pair');
}

function scheduleScan(delay) {
  clearTimeout(state.loopTimer);
  state.loopTimer = setTimeout(scanFrame, delay);
}

async function scanFrame() {
  const video = $('video');
  if (!state.stream) return;
  try {
    if (state.detectorMode !== state.mode) {
      state.detector = await createDetector(state.mode === 'pair' ? ['qr_code'] : EAN_FORMATS);
      state.detectorMode = state.mode;
    }
    if (video.readyState >= 2) {
      const codes = await state.detector.detect(video);
      for (const c of codes) {
        if (handleDetected(c.rawValue)) break;
      }
    }
  } catch (e) {
    console.error(e);
    $('lastInfo').textContent = 'Chyba čtečky: ' + e.message;
    return scheduleScan(1000);
  }
  scheduleScan(SCAN_INTERVAL_MS);
}

function handleDetected(raw) {
  if (state.mode === 'pair') return handlePairQr(raw);
  const code = String(raw || '').trim();
  if (!eanValid(code)) return false;
  const now = Date.now();
  if (code === state.lastCode && now - state.lastCodeAt < SAME_CODE_COOLDOWN_MS) {
    state.lastCodeAt = now; // dokud kód drží v záběru, znovu se neodešle
    return true;
  }
  state.lastCode = code;
  state.lastCodeAt = now;
  sendCode(code);
  return true;
}

function handlePairQr(raw) {
  let url;
  try { url = new URL(raw); } catch (e) { return false; }
  const pair = parsePairing(url.hash);
  if (!pair) return false;
  if (url.host !== location.host) {
    location.href = url.href; // QR patří k jinému serveru
    return true;
  }
  store.set('ean.pair', JSON.stringify(pair));
  state.mode = 'ean';
  $('camera').classList.remove('pairing');
  beep(true); flash(true);
  showLast('Spárováno', 'Telefon je spárovaný s PC', 'ok');
  setPairing(pair).then(reconnect);
  return true;
}

async function toggleTorch() {
  if (!state.stream) return;
  state.torch = !state.torch;
  try {
    await state.stream.getVideoTracks()[0].applyConstraints({ advanced: [{ torch: state.torch }] });
    $('torchBtn').classList.toggle('on', state.torch);
  } catch (e) { state.torch = false; }
}

async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) state.wakeLock = await navigator.wakeLock.request('screen');
  } catch (e) { /* nepodporováno */ }
}

function unlockAudio() {
  if (state.audio) { if (state.audio.state === 'suspended') state.audio.resume(); return; }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (Ctx) state.audio = new Ctx();
}

// ---------- start ----------
async function init() {
  try {
    await setPairing(readPairing());
  } catch (e) {
    await setPairing(null);
  }
  try { state.history = JSON.parse(store.get('ean.history') || '[]').slice(0, HISTORY_SIZE); } catch (e) { state.history = []; }
  renderHistory();

  $('startBtn').onclick = startCamera;
  $('stopBtn').onclick = stopCamera;
  $('torchBtn').onclick = toggleTorch;
  $('pairBtn').onclick = () => {
    state.mode = 'pair';
    $('camera').classList.add('pairing');
    showLast('Párování', 'Namiřte kameru na QR kód v okně EAN agenta na PC', '');
    if (!state.stream) startCamera();
  };

  let wasScanning = false;
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      wasScanning = !!state.stream;
      if (wasScanning) stopCamera();
    } else {
      connect();
      if (wasScanning) startCamera();
    }
  });

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch((e) => console.warn('SW:', e));
  }
  connect();
}

init();
