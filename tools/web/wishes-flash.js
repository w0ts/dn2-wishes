/* SPDX-License-Identifier: AGPL-3.0-or-later
 * The builder's "Flash from this page" step: the Digitone II's own USB OS update, sent the way Elektron
 * Transfer sends it. Everything here is the protocol and its checks; the page (builder.html) only wires a
 * Web MIDI port to it. Shared by builder.html and the tests (node: scripts/web_flash_check.mjs).
 *
 * What it copies, from one recording of Transfer updating a DN2 (2026-11-21, a read-only MIDI capture decoded
 * by scripts/usb_flash_decode.py of branch claude/flash-capture; replayed by scripts/web_flash_check.mjs):
 *   - framing: F0 00 20 3C 10 00 <8-in-7 of body> F7; body = seq:u16 BE, 00 00, opcode, payload.
 *     A reply's body = its own seq:u16, the request's seq:u16, opcode|0x80, payload.
 *   - 0x50 OsUpgradeStart: file size u32 BE, "sysex\0", 0x01 (the DN2 asks UPGRADE OS NOW? itself).
 *     Reply 0xD0: status u8 (0 ok), message string.
 *   - 0x51 OsUpgradeWrite: crc u32 BE, length u32 BE, offset u32 BE, data; 2,048 bytes a chunk, the last
 *     one shorter. The payload is the .syx file's bytes, unchanged.
 *     crc = CRC-32 (reflected, poly 0xEDB88320) with register init 0 and final xor 0xFFFFFFFF, i.e.
 *     zlib.crc32(data, 0xFFFFFFFF), elektroid's crc32(0xffffffff, ...). It is NOT zlib.crc32(data): the
 *     two differ by a constant XOR per length. Check value of "123456789": 0xD202D277.
 *   - Reply 0xD1 after EVERY chunk: next offset u32 BE, status u8 (0 ok, 1 last chunk, 2 bad CRC,
 *     3 error), message string. Transfer never has two writes outstanding; it sends the next one about
 *     5 ms after the reply (recorded: min 0.1, mean 5.1, max 13.2 ms). The last chunk's reply took 1.1 s.
 *   - Transfer sent NO 0x52 OsUpgradeEnd: after status 1 the DN2 asks UPGRADE OS NOW? on its own screen
 *     and the User's YES there is the commit. This code never sends a commit. Its Abort sends
 *     0x52 with one byte 0x00 (cancel, as elkflash documents it); that message is NOT in the recording.
 */
"use strict";
(function (root) {
  const HEADER = [0xF0, 0x00, 0x20, 0x3C, 0x10, 0x00];
  const OP = { PING: 0x01, VERSION: 0x02, START: 0x50, WRITE: 0x51, END: 0x52 };
  const ST = { OK: 0, LAST: 1, BAD_CRC: 2, ERROR: 3 };
  const C = {
    CHUNK: 2048,               // Transfer's and elektroid's chunk
    PACE_MS: 5,                // reply -> next write, Transfer's mean
    PROBE_TIMEOUT_MS: 2000,    // Ping/Version answer in ~1 ms
    START_TIMEOUT_MS: 5000,    // 0xD0 came after 92 ms
    WRITE_TIMEOUT_MS: 3000,    // 0xD1 came after 3.5..5 ms
    LAST_TIMEOUT_MS: 15000,    // the last 0xD1 came after 1,135 ms (the DN2 checks the whole image)
    CANCEL_WAIT_MS: 1000,
    MAX_CRC_RESENDS: 3,        // per chunk
    USB_BUFFER: 0x200000,      // the DN2's receive buffer (docs/usb-upgrade-limit.md)
    USB_PACKET_BYTES: 101,     // decoded bytes per 0x7E data packet
    DEVICE_ID: 0x2B,           // the file-API product id of the Digitone II (docs/midi-rpc.md)
    TRANSPORT_ID: 0x15,        // .syx byte 4 for the Digitone II
    STREAM_ID: 0x10,           // .syx header byte 8 for the Digitone II ("Incompatible OS" otherwise)
    OS_VERSION: "1.12",
  };

  // -- bytes --
  function encode87(src) {
    const out = [];
    for (let j = 0; j < src.length; j += 7) {
      let acc = 0;
      const n = Math.min(7, src.length - j);
      for (let k = 0; k < 7; k++) { acc <<= 1; if (k < n && (src[j + k] & 0x80)) acc |= 1; }
      out.push(acc);
      for (let k = 0; k < n; k++) out.push(src[j + k] & 0x7F);
    }
    return out;
  }
  function decode87(src) {
    const out = [];
    for (let i = 0; i < src.length; i += 8) {
      const acc = src[i];
      for (let k = 0; k < 7 && i + 1 + k < src.length; k++) out.push(src[i + 1 + k] | ((acc & (1 << (6 - k))) ? 0x80 : 0));
    }
    return Uint8Array.from(out);
  }
  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();
  /** Transfer's chunk CRC: register init 0, final xor 0xFFFFFFFF (zlib.crc32(data, 0xFFFFFFFF)). */
  function crc32(data, start = 0, end = data.length) {
    let c = 0;
    for (let i = start; i < end; i++) c = CRC_TABLE[(c ^ data[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function be32(n) { return [(n >>> 24) & 0xFF, (n >>> 16) & 0xFF, (n >>> 8) & 0xFF, n & 0xFF]; }
  function rd32(b, o) { return ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0; }
  function cstr(b, o) { let s = ""; for (let i = o; i < b.length && b[i]; i++) s += String.fromCharCode(b[i]); return s; }

  /** One RPC request: F0 00 20 3C 10 00 <encode87(seq, 00 00, op, payload)> F7. */
  function rpc(seq, op, payload = []) {
    const body = [(seq >> 8) & 0xFF, seq & 0xFF, 0, 0, op];
    for (let i = 0; i < payload.length; i++) body.push(payload[i]);
    return Uint8Array.from([...HEADER, ...encode87(body), 0xF7]);
  }
  /** -> {seq, ref, op, payload} for an Elektron RPC message, else null. ref: the request's seq in a reply. */
  function parse(raw) {
    if (!raw || raw.length < HEADER.length + 2 || raw[raw.length - 1] !== 0xF7) return null;
    for (let i = 0; i < HEADER.length; i++) if (raw[i] !== HEADER[i]) return null;
    const body = decode87(raw.subarray(HEADER.length, raw.length - 1));
    if (body.length < 5) return null;
    return { seq: (body[0] << 8) | body[1], ref: (body[2] << 8) | body[3], op: body[4], payload: body.subarray(5) };
  }
  function startPayload(size) { return [...be32(size), 0x73, 0x79, 0x73, 0x65, 0x78, 0x00, 0x01]; }   // "sysex\0", ask on the DN2
  function chunkLength(size, off) { return Math.min(C.CHUNK, size - off); }
  /** The 0x51 message for the chunk at OFF of SYX. */
  function writeMessage(seq, syx, off) {
    const len = chunkLength(syx.length, off);
    const head = [...be32(crc32(syx, off, off + len)), ...be32(len), ...be32(off)];
    const payload = new Uint8Array(12 + len);
    payload.set(head, 0);
    payload.set(syx.subarray(off, off + len), 12);
    return rpc(seq, OP.WRITE, payload);
  }
  function cancelMessage(seq) { return rpc(seq, OP.END, [0x00]); }
  function parseStatus(p) { return { status: p.length ? p[0] : -1, text: cstr(p, 1) }; }
  function parseWriteReply(p) {
    if (p.length < 5) return null;
    return { next: rd32(p, 0), status: p[4], text: cstr(p, 5) };
  }
  function parsePing(p) {
    if (p.length < 2) return null;
    const n = p[1], ops = Array.from(p.subarray(2, 2 + n));
    return { id: p[0], ops, name: cstr(p, 2 + n) };
  }
  function parseVersion(p) {
    const build = cstr(p, 0);
    return { build, version: cstr(p, build.length + 1) };
  }

  // -- the checks --
  /** The Digitone II OS file, packet by packet: header, data packets in order with good checksums, trailer,
   *  and the 2 MiB receive limit. -> {ok, errors, packets, usbBytes, size} */
  function checkImage(syx) {
    const errors = [];
    const res = { ok: false, errors, packets: 0, usbBytes: 0, size: syx ? syx.length : 0 };
    if (!syx || !syx.length) { errors.push("no file"); return res; }
    const msgs = [];
    for (let i = 0; i < syx.length;) {
      if (syx[i] !== 0xF0) { errors.push(`byte ${i} is not the start of a SysEx message`); return res; }
      let j = i + 1;
      while (j < syx.length && syx[j] !== 0xF7) { if (syx[j] & 0x80) break; j++; }
      if (j >= syx.length || syx[j] !== 0xF7) { errors.push(`the message at byte ${i} has no end`); return res; }
      msgs.push([i, j + 1]);
      i = j + 1;
    }
    const m = (k) => syx.subarray(msgs[k][0], msgs[k][1]);
    const ctl = (b, kind) => b.length === 16 && b[1] === 0x00 && b[2] === 0x20 && b[3] === 0x3C && b[5] === 0x00 && b[6] === 0x7F && b[7] === kind;
    if (msgs.length < 3) { errors.push("too few messages for an OS file"); return res; }
    const head = m(0), tail = m(msgs.length - 1);
    if (!ctl(head, 1)) { errors.push("the first message is not an OS-file header"); return res; }
    if (!ctl(tail, 2)) errors.push("the last message is not an OS-file trailer");
    if (head[4] !== C.TRANSPORT_ID || head[8] !== C.STREAM_ID) errors.push("not a Digitone II OS file (another product's)");
    const three = (b, o) => (b[o] << 14) | (b[o + 1] << 7) | b[o + 2];
    const base = head[8], seq0 = three(head, 9), count = three(head, 12);
    const n = msgs.length - 2;
    if (count !== n) errors.push(`the header announces ${count} data packets, the file has ${n}`);
    if (!errors.length && (three(tail, 9) !== seq0 || three(tail, 12) !== count)) errors.push("header and trailer disagree");
    for (let k = 1; k <= n && errors.length < 5; k++) {
      const b = m(k);
      if (b.length !== 128 || b[4] !== head[4] || b[6] !== 0x7E) { errors.push(`packet ${k} is not a data packet`); continue; }
      if (three(b, 7) !== ((seq0 + k - 1) & 0x1FFFFF)) errors.push(`packet ${k} is out of order`);
      let acc = 0;
      for (let i = 0; i < 119; i++) acc += b[7 + i] ^ ((base + i) & 0xFF);
      if (((base + acc) & 0x7F) !== b[126]) errors.push(`packet ${k} has a bad checksum`);
    }
    res.packets = n;
    res.usbBytes = n * C.USB_PACKET_BYTES;
    if (res.usbBytes > C.USB_BUFFER) errors.push(`the image decodes to ${res.usbBytes} bytes, over the DN2's 2 MiB receive buffer (${C.USB_BUFFER})`);
    res.ok = !errors.length;
    return res;
  }
  /** The instrument on the port: a Digitone II on OS 1.12 that takes the OS update opcodes. */
  function checkDevice(ping, ver) {
    const errors = [];
    if (!ping) errors.push("no Ping answer");
    else {
      if (ping.id !== C.DEVICE_ID || !/^Digitone II\b/.test(ping.name)) errors.push(`not a Digitone II (id 0x${ping.id.toString(16)}, "${ping.name}")`);
      for (const op of [OP.START, OP.WRITE, OP.END]) if (!ping.ops.includes(op)) errors.push(`the device does not list opcode 0x${op.toString(16)}`);
    }
    if (!ver) errors.push("no SoftwareVersion answer");
    else if (ver.version !== C.OS_VERSION) errors.push(`the DN2 runs OS ${ver.version || "?"}; this page flashes only from OS ${C.OS_VERSION}`);
    return { ok: !errors.length, errors };
  }

  /** Reassembles SysEx messages from MIDI bytes (Chrome delivers whole messages; this also takes pieces). */
  function assembler() {
    let buf = null;
    return (bytes) => {
      const out = [];
      for (const b of bytes) {
        if (b >= 0xF8) continue;
        if (b === 0xF0) buf = [b];
        else if (buf) { buf.push(b); if (b === 0xF7) { if (buf.length > 2) out.push(Uint8Array.from(buf)); buf = null; } }
      }
      return out;
    };
  }

  class FlashError extends Error {
    constructor(code, message, info = {}) { super(message); this.code = code; Object.assign(this, info); }
  }

  /** The session. opts: send(bytes) (one SysEx message), log(text), progress(done, total),
   *  seq(op) -> u16 (default: a counter), paceMs and the *_TIMEOUT_MS of C, setTimeout/clearTimeout.
   *  Feed every incoming MIDI message to receive(). */
  function createFlasher(opts) {
    const o = Object.assign({}, C, opts);
    const setT = o.setTimeout || ((f, ms) => setTimeout(f, ms));
    const clearT = o.clearTimeout || ((t) => clearTimeout(t));
    const log = o.log || (() => {});
    const progress = o.progress || (() => {});
    let counter = 0;
    const nextSeq = o.seq || (() => { counter = (counter + 1) & 0xFFFF; return counter; });
    const feed = assembler();
    let pending = null;        // {seq, op, resolve, reject, timer}
    let state = "idle";        // idle, probing, ready, starting, writing, confirm, cancelled, failed, lost
    let abortWanted = false;

    function sleep(ms) { return ms > 0 ? new Promise(r => setT(r, ms)) : Promise.resolve(); }
    function settle(fn, v) {
      const p = pending; if (!p) return;
      pending = null; clearT(p.timer); fn === "ok" ? p.resolve(v) : p.reject(v);
    }
    function request(op, payload, timeoutMs, raw) {
      if (pending) return Promise.reject(new FlashError("busy", "a request is already waiting"));
      const seq = nextSeq(op);
      const msg = raw ? raw(seq) : rpc(seq, op, payload);
      return new Promise((resolve, reject) => {
        pending = { seq, op, resolve, reject,
          timer: setT(() => settle("no", new FlashError("timeout", `no answer to 0x${op.toString(16)} in ${timeoutMs} ms`)), timeoutMs) };
        try { o.send(msg); } catch (e) { settle("no", new FlashError("send", "the MIDI port refused the message: " + (e && e.message || e))); }
      });
    }
    function receive(bytes) {
      for (const raw of feed(bytes)) {
        const r = parse(raw);
        if (!r) { log(`ignored a message that is not an Elektron RPC (${raw.length} B)`); continue; }
        if (raw.length === 885) log("a reply of exactly 885 bytes: another application may hold the port (docs/midi-rpc.md)");
        if (pending && r.op === (pending.op | 0x80) && r.ref === pending.seq) settle("ok", r);
        else if (r.op & 0x80) log(`ignored a reply 0x${r.op.toString(16)} to request ${r.ref} (not this page's)`);
      }
    }
    async function probe() {
      state = "probing";
      try {
        const p = parsePing((await request(OP.PING, [], o.PROBE_TIMEOUT_MS)).payload);
        const v = parseVersion((await request(OP.VERSION, [], o.PROBE_TIMEOUT_MS)).payload);
        const chk = checkDevice(p, v);
        state = chk.ok ? "ready" : "idle";
        return { ping: p, version: v, ...chk };
      } catch (e) { state = "idle"; throw e; }
    }
    async function cancel(why) {
      log(`cancelling: 0x52 00 (${why})`);
      try {
        const r = await request(OP.END, null, o.CANCEL_WAIT_MS, cancelMessage);
        log(`cancel answered: ${Array.from(r.payload).map(b => b.toString(16).padStart(2, "0")).join(" ")}`);
      } catch (e) { log(`cancel: ${e.message}`); }
    }
    function stopIfAborted() { if (abortWanted) throw new FlashError("aborted", "stopped by the Abort button"); }

    /** Sends SYX. Resolves {state: "confirm"} once the DN2 took the last chunk (it then asks UPGRADE OS NOW?).
     *  Rejects with a FlashError; before that point every failure after the start sends the cancel. */
    async function flash(syx) {
      if (!(syx instanceof Uint8Array)) throw new FlashError("input", "no image");
      if (!["idle", "ready"].includes(state)) throw new FlashError("state", `cannot start while ${state}`);
      abortWanted = false;
      const img = checkImage(syx);
      if (!img.ok) throw new FlashError("image", "the file failed its checks: " + img.errors.join("; "));
      const dev = await probe();            // Ping and SoftwareVersion must answer, right before the start
      if (!dev.ok) throw new FlashError("device", dev.errors.join("; "));
      stopIfAborted();
      const size = syx.length;
      state = "starting";
      let started = false;
      try {
        const s = parseStatus((await request(OP.START, startPayload(size), o.START_TIMEOUT_MS)).payload);
        started = true;
        if (s.status !== 0) throw new FlashError("start", `the DN2 refused the update (status ${s.status}${s.text ? ": " + s.text : ""})`);
        state = "writing";
        log(`OsUpgradeStart accepted; ${Math.ceil(size / o.CHUNK)} chunks of ${o.CHUNK} B`);
        let off = 0, resends = 0;
        for (;;) {
          stopIfAborted();
          const len = chunkLength(size, off), last = off + len === size;
          const r = await request(OP.WRITE, null, last ? o.LAST_TIMEOUT_MS : o.WRITE_TIMEOUT_MS, (seq) => writeMessage(seq, syx, off));
          const w = parseWriteReply(r.payload);
          if (!w) throw new FlashError("reply", "a 0xD1 reply too short to read");
          if (w.status === ST.LAST) {
            if (!last || w.next !== size) throw new FlashError("reply", `the DN2 said "last chunk" at offset ${w.next} of ${size}`);
            progress(size, size);
            state = "confirm";
            log("the DN2 took the whole file; it now asks UPGRADE OS NOW? on its own screen");
            return { state };
          }
          if (w.status === ST.BAD_CRC) {
            if (++resends > o.MAX_CRC_RESENDS) throw new FlashError("crc", `bad CRC at offset ${off} more than ${o.MAX_CRC_RESENDS} times`);
            if (w.next > off) throw new FlashError("reply", `bad CRC but the DN2 asks for offset ${w.next}, past ${off}`);
            log(`bad CRC at offset ${off}: resending from ${w.next} (${resends}/${o.MAX_CRC_RESENDS})`);
            off = w.next;
          } else if (w.status === ST.OK) {
            if (w.next !== off + len || last) throw new FlashError("reply", `the DN2 asks for offset ${w.next} after the chunk at ${off} (+${len})${last ? ", after the last chunk" : ""}`);
            off = w.next; resends = 0;
          } else {
            throw new FlashError("device", `the DN2 stopped the update (status ${w.status}${w.text ? ": " + w.text : ""})`);
          }
          progress(off, size);
          await sleep(o.paceMs !== undefined ? o.paceMs : o.PACE_MS);
        }
      } catch (e) {
        const err = e instanceof FlashError ? e : new FlashError("internal", String(e && e.message || e));
        if (state !== "lost") {
          if (started || state === "starting") await cancel(err.message);
          state = err.code === "aborted" ? "cancelled" : "failed";
        }
        throw err;
      }
    }
    /** The Abort button: before the last chunk is taken, stops and sends the cancel. After it, no message:
     *  the User answers NO on the DN2. -> true when the cancel will be sent. */
    function abort() {
      if (!["probing", "starting", "writing"].includes(state)) return false;
      abortWanted = true;
      settle("no", new FlashError("aborted", "stopped by the Abort button"));
      return true;
    }
    /** The port went away: nothing more can be sent. */
    function portLost() {
      const was = state;
      if (["probing", "starting", "writing"].includes(state)) state = "lost";
      settle("no", new FlashError("lost", "the MIDI port disconnected"));
      return was;
    }
    return { probe, flash, abort, portLost, receive, get state() { return state; } };
  }

  const api = { C, OP, ST, encode87, decode87, crc32, rpc, parse, startPayload, chunkLength, writeMessage, cancelMessage,
    parseStatus, parseWriteReply, parsePing, parseVersion, checkImage, checkDevice, assembler, createFlasher, FlashError };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WishesFlash = api;
})(typeof self !== "undefined" ? self : this);
