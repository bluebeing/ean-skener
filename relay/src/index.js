// Relay pro EAN Skener: přeposílá zašifrované zprávy mezi telefonem a PC.
// Server nezná klíč, vidí jen ID místnosti, přítomnost a zašifrovaná data.
import { DurableObject } from 'cloudflare:workers';

const ROOM_RE = /^[A-Za-z0-9_-]{22,64}$/;
const ROLES = ['pc', 'phone'];
const MAX_MESSAGE = 4096;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const m = url.pathname.match(/^\/ws\/([^/]+)$/);
    if (!m) return env.ASSETS.fetch(request);

    const room = m[1];
    const role = url.searchParams.get('role');
    if (!ROOM_RE.test(room) || !ROLES.includes(role)) {
      return new Response('Neplatná místnost nebo role', { status: 400 });
    }
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Očekáván WebSocket', { status: 426 });
    }
    return env.ROOMS.get(env.ROOMS.idFromName(room)).fetch(request);
  },
};

export class Room extends DurableObject {
  async fetch(request) {
    const role = new URL(request.url).searchParams.get('role');
    if (role === 'pc') {
      // v místnosti je vždy jen jedno PC, nové nahradí staré
      for (const old of this.ctx.getWebSockets('pc')) old.close(4000, 'replaced');
    }
    const { 0: client, 1: server } = new WebSocketPair();
    this.ctx.acceptWebSocket(server, [role]);
    this.broadcastPresence();
    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws, message) {
    if (typeof message !== 'string' || message.length > MAX_MESSAGE) return;
    const role = this.ctx.getTags(ws)[0];
    const target = role === 'pc' ? 'phone' : 'pc';
    for (const peer of this.ctx.getWebSockets(target)) {
      try { peer.send(message); } catch (e) { /* spojení se právě zavírá */ }
    }
  }

  webSocketClose(ws) {
    try { ws.close(); } catch (e) { /* už zavřeno */ }
    this.broadcastPresence(ws);
  }

  webSocketError(ws) {
    this.broadcastPresence(ws);
  }

  broadcastPresence(closing) {
    const open = (tag) => this.ctx.getWebSockets(tag).filter((s) => s !== closing && s.readyState === 1);
    const msg = JSON.stringify({ t: 'peer', pc: open('pc').length > 0, phones: open('phone').length });
    for (const s of this.ctx.getWebSockets()) {
      if (s === closing) continue;
      try { s.send(msg); } catch (e) { /* ignorovat */ }
    }
  }
}
