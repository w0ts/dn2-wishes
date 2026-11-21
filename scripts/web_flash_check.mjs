/**
 * The builder's "Flash from this page" protocol (tools/web/wishes-flash.js), checked from the command line.
 * Nothing here opens a MIDI port: every DN2 below is a fake in this process.
 *
 *   node scripts/web_flash_check.mjs synthetic
 *       A fake DN2 that answers the way the recording shows, over small synthetic OS files: a clean run,
 *       bad CRC (resend, then too many), a device error, a timeout, the Abort button before and after the
 *       last chunk, a lost port, the wrong device, the wrong OS, an image over 2 MiB, a broken file.
 *   node scripts/web_flash_check.mjs replay CAPTURE.log FILE.syx
 *       Replays a recording of Elektron Transfer's update (scratch/flash-capture, midi_tap format): the
 *       page's encoder, given the recording's sequence numbers, must send byte for byte the OsUpgradeStart
 *       and every OsUpgradeWrite Transfer sent, and finish on the DN2's recorded replies.
 *
 * Prints one JSON report (never the device's name: it may carry the owner's) and exits 1 if a check fails.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { crc32 as zcrc32 } from "node:zlib";
import { performance } from "node:perf_hooks";

const require = createRequire(import.meta.url);
const F = require("../tools/web/wishes-flash.js");

const checks = [];
function check(name, ok, detail = "") { checks.push({ name, ok: !!ok, detail: String(detail) }); }
const eq = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
const hexs = (b) => Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");

// -- a Digitone II OS file of N data packets (header 7F 01, data 7E, trailer 7F 02), checksums as the DN2 checks them
function makeImage(n, { stream = 0x10, transport = 0x15, seed = 1 } = {}) {
  const seq0 = 242, base = stream;
  const three = (v) => [(v >> 14) & 0x7f, (v >> 7) & 0x7f, v & 0x7f];
  const ctl = (kind) => [0xf0, 0x00, 0x20, 0x3c, transport, 0x00, 0x7f, kind, base, ...three(seq0), ...three(n), 0xf7];
  const out = [...ctl(1)];
  let x = seed;
  for (let k = 0; k < n; k++) {
    const p = [0xf0, 0x00, 0x20, 0x3c, transport, 0x00, 0x7e, ...three(seq0 + k)];
    for (let i = 0; i < 116; i++) { x = (x * 1103515245 + 12345) >>> 0; p.push((x >>> 16) & 0x7f); }
    let acc = 0;
    for (let i = 0; i < 119; i++) acc += p[7 + i] ^ ((base + i) & 0xff);
    p.push((base + acc) & 0x7f, 0xf7);
    out.push(...p);
  }
  out.push(...ctl(2));
  return Uint8Array.from(out);
}

// -- the fake DN2: answers like the recording (0x81, 0x82, 0xD0 "00 00", 0xD1 <next u32> <status> 00) --
const PING_OPS = [0x01, 0x02, 0x03, 0x04, 0x06, 0x07, 0x09, 0x50, 0x52, 0x51, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5a, 0x5b, 0x5c, 0x5d, 0x5e];
function fakeDN2(syx, opt = {}) {
  const tx = [];                 // every message the page sent, parsed
  const got = new Uint8Array(syx.length);
  let devSeq = 0x0750, flasher = null, crcBad = Object.assign({}, opt.badCrc || {}), writes = 0;
  const reply = (req, payload) => {
    const body = [(devSeq >> 8) & 0xff, devSeq & 0xff, (req.seq >> 8) & 0xff, req.seq & 0xff, req.op | 0x80, ...payload];
    devSeq = (devSeq + 1) & 0xffff;
    const raw = Uint8Array.from([0xf0, 0x00, 0x20, 0x3c, 0x10, 0x00, ...F.encode87(body), 0xf7]);
    if (opt.split) setImmediate(() => { flasher.receive(raw.subarray(0, 7)); flasher.receive(raw.subarray(7)); });
    else setImmediate(() => flasher.receive(raw));
  };
  const name = [...Buffer.from(opt.name || "Digitone II"), 0];
  function send(raw) {
    const m = F.parse(raw);
    tx.push({ raw: Uint8Array.from(raw), ...m });
    if (opt.lostAtWrite !== undefined && m.op === 0x51 && writes === opt.lostAtWrite) { setImmediate(() => flasher.portLost()); return; }
    if (m.op === 0x01) return reply(m, [opt.pingId ?? 0x2b, PING_OPS.length, ...PING_OPS, ...name]);
    if (m.op === 0x02) return reply(m, [...Buffer.from("0062\0" + (opt.version || "1.12") + "\0")]);
    if (m.op === 0x50) return reply(m, [opt.startStatus ?? 0, 0]);
    if (m.op === 0x52) return reply(m, [0, 0]);
    if (m.op === 0x51) {
      const p = m.payload, rd = (o) => ((p[o] << 24) | (p[o + 1] << 16) | (p[o + 2] << 8) | p[o + 3]) >>> 0;
      const crc = rd(0), len = rd(4), off = rd(8), data = p.subarray(12);
      const k = writes++;
      if (opt.silentAtWrite === k) return;                                           // never answers
      if (opt.abortAtWrite === k) setImmediate(() => flasher.abort());
      if (opt.errorAtWrite === k) return reply(m, [...be(off), 3, 0]);
      const crcOk = zcrc32(data, 0xffffffff) === crc && len === data.length;        // node's zlib, not the page's table
      if (!crcOk || (crcBad[off] > 0 && crcBad[off]--)) return reply(m, [...be(off), 2, 0]);
      got.set(data, off);
      const next = off + len;
      return reply(m, [...be(next), next === syx.length ? 1 : 0, 0]);
    }
  }
  return { send, tx, got, attach(f) { flasher = f; } };
}
const be = (n) => [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff];

async function run(syx, opt = {}, fopt = {}) {
  const dev = fakeDN2(syx, opt);
  const logs = [];
  const f = F.createFlasher({ send: dev.send, log: (t) => logs.push(t), paceMs: 0, WRITE_TIMEOUT_MS: 200, LAST_TIMEOUT_MS: 400,
    START_TIMEOUT_MS: 200, PROBE_TIMEOUT_MS: 200, CANCEL_WAIT_MS: 200, ...fopt });
  dev.attach(f);
  let res = null, err = null;
  try { res = await f.flash(syx); } catch (e) { err = e; }
  const ops = dev.tx.map((m) => m.op);
  return { res, err, dev, f, logs, ops, commits: dev.tx.filter((m) => m.op === 0x52 && m.payload[0] !== 0).length,
    cancels: dev.tx.filter((m) => m.op === 0x52 && m.payload.length === 1 && m.payload[0] === 0).length };
}

async function synthetic() {
  // the CRC variant, on its standard check string and on the recording's rule
  const nine = Uint8Array.from(Buffer.from("123456789"));
  check("crc: check value of 123456789 is 0xD202D277", F.crc32(nine) === 0xd202d277, F.crc32(nine).toString(16));
  const rnd = makeImage(3);
  check("crc: equals zlib.crc32(data, 0xFFFFFFFF)", F.crc32(rnd) === zcrc32(rnd, 0xffffffff));
  check("crc: differs from plain zlib.crc32", F.crc32(rnd) !== zcrc32(rnd));
  const any = Uint8Array.from({ length: 999 }, (_, i) => (i * 37 + (i >> 3)) & 0xff);
  check("8-in-7 round trip", eq(F.decode87(F.encode87(any)), any));
  check("framing: a Ping is the recording's bytes", hexs(F.rpc(0x0181, 0x01)) === "f000203c1000200101000001f7");
  check("framing: OsUpgradeStart is the recording's bytes",
    hexs(F.rpc(0x019d, 0x50, F.startPayload(2549152))) === "f000203c100020011d00005000266065207379736578000001f7");
  const d0 = F.parse(Uint8Array.from(Buffer.from("f000203c10000c076c011d500000f7", "hex")));
  check("framing: the recorded 0xD0 reply reads as ref 0x019d, status 0", d0 && d0.op === 0xd0 && d0.ref === 0x019d && F.parseStatus(d0.payload).status === 0);
  const d1 = F.parse(Uint8Array.from(Buffer.from("f000203c10000c0c6b061c5100266065200100f7", "hex")));
  const w1 = d1 && F.parseWriteReply(d1.payload);
  check("framing: the recorded last 0xD1 reads as next 2549152, status 1", w1 && w1.next === 2549152 && w1.status === 1 && d1.ref === 0x069c);

  const img = makeImage(70);                                    // 8,992 B: 5 chunks, the last 800 B
  const chk = F.checkImage(img);
  check("image check passes a well-formed DN2 file", chk.ok && chk.packets === 70 && chk.usbBytes === 7070, chk.errors.join("; "));
  const broken = Uint8Array.from(img); broken[16 + 128 * 5 + 50] ^= 1;
  check("image check refuses a bad packet checksum", !F.checkImage(broken).ok, F.checkImage(broken).errors[0]);
  const dropped = Uint8Array.from([...img.subarray(0, 16 + 128 * 3), ...img.subarray(16 + 128 * 4)]);
  check("image check refuses a missing packet", !F.checkImage(dropped).ok, F.checkImage(dropped).errors[0]);
  check("image check refuses another product's file", !F.checkImage(makeImage(5, { stream: 0x0f, transport: 0x14 })).ok);
  const big = makeImage(Math.floor(0x200000 / 101) + 1);
  const bc = F.checkImage(big);
  check("image check refuses an image over the 2 MiB receive buffer", !bc.ok && bc.errors.some((e) => /2 MiB/.test(e)), bc.usbBytes);
  check("image check takes an image just at the buffer", F.checkImage(makeImage(Math.floor(0x200000 / 101))).ok);

  // a clean run
  let r = await run(img);
  const writes = r.dev.tx.filter((m) => m.op === 0x51);
  check("clean: ends waiting for the DN2's own UPGRADE OS NOW?", r.res && r.res.state === "confirm" && r.f.state === "confirm", r.err && r.err.message);
  check("clean: Ping and SoftwareVersion before the start", eq(r.ops.slice(0, 3), [0x01, 0x02, 0x50]), r.ops.slice(0, 3));
  check("clean: the DN2 received exactly the file", eq(r.dev.got, img));
  check("clean: 2,048-byte chunks, the last shorter", writes.length === 5 && writes.slice(0, 4).every((m) => m.payload.length === 12 + 2048) && writes[4].payload.length === 12 + 800);
  check("clean: no 0x52 at all (Transfer sends none)", !r.ops.includes(0x52));
  check("clean: every request has its own sequence number", new Set(r.dev.tx.map((m) => m.seq)).size === r.dev.tx.length);
  r = await run(img, { split: true });
  check("clean: replies split across MIDI events are reassembled", r.res && r.res.state === "confirm");

  // bad CRC: resend the same chunk; more than three times: stop and cancel
  r = await run(img, { badCrc: { 4096: 2 } });
  const at4096 = r.dev.tx.filter((m) => m.op === 0x51 && ((m.payload[8] << 24) | (m.payload[9] << 16) | (m.payload[10] << 8) | m.payload[11]) === 4096);
  check("bad CRC twice: the chunk is resent and the run completes", r.res && r.res.state === "confirm" && at4096.length === 3 && eq(r.dev.got, img), r.err && r.err.message);
  check("bad CRC: the resent chunk is the same bytes but a new sequence number",
    at4096.length === 3 && eq(at4096[0].payload, at4096[2].payload) && at4096[0].seq !== at4096[2].seq);
  r = await run(img, { badCrc: { 2048: 9 } });
  check("bad CRC four times: stops, sends the cancel 0x52 00, never a commit", r.err && r.err.code === "crc" && r.cancels === 1 && r.commits === 0 && r.f.state === "failed", r.err && r.err.message);

  r = await run(img, { errorAtWrite: 2 });
  check("status 3 (error): stops and cancels", r.err && r.err.code === "device" && r.cancels === 1 && r.ops.filter((o) => o === 0x51).length === 3);
  r = await run(img, { silentAtWrite: 1 });
  check("timeout: no 0xD1 in time stops and cancels", r.err && r.err.code === "timeout" && r.cancels === 1 && r.ops.filter((o) => o === 0x51).length === 2, r.err && r.err.message);
  r = await run(img, { startStatus: 1 });
  check("start refused (0xD0 status 1): no write, cancel", r.err && r.err.code === "start" && !r.ops.includes(0x51) && r.cancels === 1);

  r = await run(img, { abortAtWrite: 2 });
  check("Abort mid-transfer: no further write, the cancel 0x52 00 is sent", r.err && r.err.code === "aborted" && r.cancels === 1 && r.commits === 0
    && r.ops.filter((o) => o === 0x51).length === 3 && r.ops[r.ops.length - 1] === 0x52 && r.f.state === "cancelled", r.ops.join(","));
  r = await run(img);
  check("Abort after the last chunk sends nothing (the User answers NO on the DN2)", r.f.abort() === false && !r.ops.includes(0x52));
  r = await run(img, { lostAtWrite: 2 });
  check("port lost before the end: stops, sends nothing more", r.err && r.err.code === "lost" && r.cancels === 0 && r.ops[r.ops.length - 1] === 0x51 && r.f.state === "lost");

  r = await run(img, { pingId: 0x2a, name: "Digitakt II" });
  check("wrong device: refused before OsUpgradeStart", r.err && r.err.code === "device" && !r.ops.includes(0x50));
  r = await run(img, { version: "1.11" });
  check("another OS than 1.12: refused before OsUpgradeStart", r.err && r.err.code === "device" && !r.ops.includes(0x50), r.err && r.err.message);
  r = await run(big);
  check("over 2 MiB: refused before any message", r.err && r.err.code === "image" && r.ops.length === 0);
  r = await run(broken);
  check("bad file: refused before any message", r.err && r.err.code === "image" && r.ops.length === 0);

  // no commit anywhere in the code: the only 0x52 is the cancel
  const src = readFileSync(new URL("../tools/web/wishes-flash.js", import.meta.url), "utf8");
  check("the module builds 0x52 only as the cancel (one byte 0x00)",
    /function cancelMessage\(seq\) \{ return rpc\(seq, OP\.END, \[0x00\]\); \}/.test(src) && (src.match(/OP\.END/g) || []).length === 3);
}

// -- the recording --
function readLog(path) {
  const msgs = [], buf = { TX: null, RX: null }, t0 = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    if (!line || line.startsWith("#")) continue;
    const [ns, d, , hx] = line.split(/\s+/);
    if (!hx) continue;
    for (const b of Buffer.from(hx, "hex")) {
      if (b >= 0xf8) continue;
      if (b === 0xf0) { buf[d] = [b]; t0[d] = Number(ns); }
      else if (buf[d]) { buf[d].push(b); if (b === 0xf7) { if (buf[d].length > 2) msgs.push({ dir: d, t: t0[d], raw: Uint8Array.from(buf[d]) }); buf[d] = null; } }
    }
  }
  return msgs.sort((a, b) => a.t - b.t);
}

async function replay(logPath, syxPath) {
  const syx = new Uint8Array(readFileSync(syxPath));
  const msgs = readLog(logPath).map((m) => ({ ...m, p: F.parse(m.raw) })).filter((m) => m.p);
  const recTx = msgs.filter((m) => m.dir === "TX" && [0x50, 0x51, 0x52].includes(m.p.op));
  const recRx = new Map(msgs.filter((m) => m.dir === "RX" && [0xd0, 0xd1, 0xd2].includes(m.p.op)).map((m) => [m.p.ref, m.raw]));
  const ping = msgs.find((m) => m.dir === "RX" && m.p.op === 0x81), ver = msgs.find((m) => m.dir === "RX" && m.p.op === 0x82);
  check("recording: one OsUpgradeStart, its writes, no OsUpgradeEnd", recTx[0] && recTx[0].p.op === 0x50 && recTx.filter((m) => m.p.op === 0x52).length === 0,
    `${recTx.length} messages`);
  // Transfer's pacing: reply -> next write
  const gaps = [];
  for (let i = 0; i < msgs.length - 1; i++) if (msgs[i].dir === "RX" && msgs[i].p.op === 0xd1) {
    const n = msgs.slice(i + 1).find((m) => m.dir === "TX" && m.p.op === 0x51);
    if (n) gaps.push((n.t - msgs[i].t) / 1e6);
  }
  const queue = recTx.map((m) => m.p.seq);
  let flasher = null, other = 1;
  const sent = [], times = [], replyAt = [];
  const send = (raw) => {
    const m = F.parse(raw);
    sent.push({ raw: Uint8Array.from(raw), op: m.op });
    if (m.op === 0x51) times.push(performance.now());
    const answer = (r) => setImmediate(() => { if (m.op === 0x51) replyAt.push(performance.now()); flasher.receive(r); });
    if (m.op === 0x01 || m.op === 0x02) {
      const rec = m.op === 0x01 ? ping : ver;     // the recorded payload, re-addressed to this request
      const body = [0x07, 0x50, (m.seq >> 8) & 0xff, m.seq & 0xff, m.op | 0x80, ...rec.p.payload];
      return answer(Uint8Array.from([0xf0, 0x00, 0x20, 0x3c, 0x10, 0x00, ...F.encode87(body), 0xf7]));
    }
    const r = recRx.get(m.seq);
    if (r) answer(r);                          // the DN2's own recorded reply bytes
  };
  flasher = F.createFlasher({ send, seq: (op) => (op === 0x50 || op === 0x51 ? queue.shift() : other++) });
  let res = null, err = null;
  const t = performance.now();
  try { res = await flasher.flash(syx); } catch (e) { err = e; }
  const secs = (performance.now() - t) / 1000;
  const ours = sent.filter((m) => [0x50, 0x51, 0x52].includes(m.op));
  let firstDiff = -1;
  for (let i = 0; i < Math.max(ours.length, recTx.length); i++) {
    if (!ours[i] || !recTx[i] || !eq(ours[i].raw, recTx[i].raw)) { firstDiff = i; break; }
  }
  check("replay: the run ends waiting for UPGRADE OS NOW?", res && res.state === "confirm", err && err.message);
  check("replay: every OsUpgradeStart/Write byte for byte Transfer's", firstDiff === -1 && ours.length === recTx.length,
    `${ours.length} sent, ${recTx.length} recorded${firstDiff >= 0 ? ", first difference at message " + firstDiff : ""}`);
  check("replay: the device check passes on the recorded Ping/Version", F.checkDevice(F.parsePing(ping.p.payload), F.parseVersion(ver.p.payload)).ok);
  check("replay: the file passes the image check", F.checkImage(syx).ok, F.checkImage(syx).errors.join("; "));
  const ourGaps = times.slice(1).map((x, i) => x - replyAt[i]);
  const mean = (a) => a.reduce((s, x) => s + x, 0) / (a.length || 1);
  const tMin = Math.min(...gaps), tMax = Math.max(...gaps);
  check("replay: reply -> next write about as Transfer (mean within its recorded min..max + timer slack)",
    mean(ourGaps) >= tMin && mean(ourGaps) <= tMax + 2, `ours mean ${mean(ourGaps).toFixed(1)} ms; Transfer min ${tMin.toFixed(1)} mean ${mean(gaps).toFixed(1)} max ${tMax.toFixed(1)}`);
  check("replay: one write outstanding at a time", replyAt.length >= times.length - 1 && times.slice(1).every((x, i) => x >= replyAt[i]));
  return { writes: ours.length - 1, seconds: secs };
}

const [mode, a, b] = process.argv.slice(2);
let extra = {};
if (mode === "synthetic") await synthetic();
else if (mode === "replay") extra = await replay(a, b);
else { console.error("usage: web_flash_check.mjs synthetic | replay CAPTURE.log FILE.syx"); process.exit(2); }
const failed = checks.filter((c) => !c.ok);
console.log(JSON.stringify({ mode, ok: !failed.length, failed: failed.length, checks, ...extra }, null, 1));
process.exit(failed.length ? 1 : 0);
