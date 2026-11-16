/* Sample Transfer: the sample-link protocol core (the pool image, SysEx framing,
 * the +Drive library commands, WAV/AIFF reading and slicing).
 *
 * Copied unchanged from De-Pattern/dn2mk2-firmware, tools/web/index.html
 * (its <script id="core"> block), commit 5b26e21d0f5d5aeb67fde8374739c553967f6495
 * (2026-11-12; the same file is served by De-Pattern/dn2mk2 as its index.html).
 * AGPL-3.0-or-later, as the rest of that repository. Do not edit here: change it
 * upstream and copy it again, so it stays byte for byte the code
 * test/test_web_tool.py checks against tools/dn2samples.py.
 *
 * A classic script, not an ES module: samples-page.js reads the DN2 global it
 * declares, exactly as the two inline scripts of the upstream page do.
 */
/* The pool image, as tools/dn2samples.py and dnfw.sampler.live.pool_bytes build it.
 * Kept free of the page so a test can run it under node (test/test_web_tool.py). */
const DN2 = (() => {
  const C = {
    POOL_MAGIC: 0x31504D53, POOL_SLOTS: 128, USER_SLOTS: 122, ENTRY_WORDS: 4,
    NAMES_OFFSET: 8 + 128 * 16, NAME_BYTES: 8, DATA_OFFSET: 0x1000, FMT_I16: 1,
    MAX_SLICES: 64, REC_OFFSET: 96 << 20, REC_END: 128 << 20, POOL_BYTES: 400 << 20,
    DSP_RATE: 48000, POOL_DDR: 0x84000000,
    HEADER: [0xF0, 0x00, 0x20, 0x3C, 0x7D, 0x01],
    CMD: { HELLO: 1, WRITE: 2, STATUS: 3, BEGIN: 8, END: 9, DIR: 10, DIAG: 24, SCAN: 25, ENTRY: 27 },
    /* v0.31 (sample link 5): the +Drive's library, little-endian (csrc/sampler/lib.c) */
    LIB: { INFO: 16, FOLDER: 17, BEGIN: 18, WRITE: 19, END: 20, LIST: 21, DELETE: 22, FOLDERS: 23, DROP: 26,
           FOLDER_IN: 30, TREE: 31 }, LIB_CAP: 2048,
    /* v0.40 (sample link 7): folders inside folders, six levels at most (lib.c LIB_DEPTH,
     * dnfw.sampler.libtree); a dropped folder's path kept whole until it is sent */
    LIB_DEPTH: 6, PATH_MAX: 200,
    /* v0.25: long names and folders (dnfw.sampler.machines META_*) */
    META_PTR: 0xC08, META_PTR_MAGIC: 0x52544D53, META_MAGIC: 0x54454D53, META_FOLDERS: 64,
    META_FOLDER_BYTES: 32, META_SLOT_BYTES: 40, META_NAME_BYTES: 36, LONG_MAX: 35, FOLDER_MAX: 31,
  };
  C.META_BYTES = 12 + C.META_FOLDERS * C.META_FOLDER_BYTES + C.POOL_SLOTS * C.META_SLOT_BYTES;
  C.HOLE_BYTES = C.REC_END - C.REC_OFFSET;           /* what a send skips */
  C.SLICE_AREA = C.REC_END - (128 << 10);           /* v0.23: slices made on the instrument */
  C.TABLE_AREA = C.SLICE_AREA - (512 << 10);         /* v0.26: the machines' tables, before the slices */
  C.REC_BYTES = C.TABLE_AREA - C.REC_OFFSET;

  function pack7(data) {
    const out = [];
    for (let i = 0; i < data.length; i += 7) {
      const g = data.slice(i, i + 7);
      let h = 0;
      g.forEach((b, k) => { if (b & 0x80) h |= 1 << (6 - k); });
      out.push(h, ...Array.from(g, b => b & 0x7F));
    }
    return out;
  }
  function unpack7(data) {
    const out = [];
    let i = 0;
    while (i < data.length) {
      const h = data[i++];
      for (let k = 1; k < 8 && i < data.length; k++) out.push(data[i++] | ((h << k) & 0x80));
    }
    return out;
  }
  function request(seq, cmd, payload = []) {
    const body = [(seq >> 8) & 0xFF, seq & 0xFF, cmd, ...payload];
    return Uint8Array.from([...C.HEADER, ...pack7(body), 0xF7]);
  }
  function parse(sx) {
    sx = Array.from(sx);
    if (sx.length < 8 || C.HEADER.some((b, k) => sx[k] !== b) || sx[sx.length - 1] !== 0xF7) return null;
    const m = unpack7(sx.slice(C.HEADER.length, -1));
    if (m.length < 4) return null;
    return { seq: (m[0] << 8) | m[1], cmd: m[2], status: m[3], payload: Uint8Array.from(m.slice(4)) };
  }
  const be32 = v => [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255];
  const rd32 = (p, o) => ((p[o] << 24) | (p[o + 1] << 16) | (p[o + 2] << 8) | p[o + 3]) >>> 0;

  /* a WAV -> {frames: Float32Array mono, rate, cues: [frame offsets]} (PCM 8/16/24/32, float 32/64) */
  function readWav(buf) {
    const d = new DataView(buf);
    const tag = (o) => String.fromCharCode(d.getUint8(o), d.getUint8(o + 1), d.getUint8(o + 2), d.getUint8(o + 3));
    if (buf.byteLength < 12 || tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a WAV file");
    let at = 12, fmt = null, data = null; const cues = [];
    while (at + 8 <= buf.byteLength) {
      const id = tag(at), size = d.getUint32(at + 4, true), body = at + 8;
      if (id === "fmt ") fmt = { tag: d.getUint16(body, true), ch: d.getUint16(body + 2, true),
        rate: d.getUint32(body + 4, true), bits: d.getUint16(body + 14, true),
        ext: size >= 26 ? d.getUint16(body + 24, true) : 0 };
      else if (id === "data") data = { at: body, size: Math.min(size, buf.byteLength - body) };
      else if (id === "cue ") { const n = d.getUint32(body, true); for (let k = 0; k < n; k++) cues.push(d.getUint32(body + 4 + 24 * k + 20, true)); }
      at = body + size + (size & 1);
    }
    if (!fmt || !data) throw new Error("no fmt or data chunk");
    const tagv = fmt.tag === 0xFFFE ? fmt.ext : fmt.tag, bps = fmt.bits / 8, ch = fmt.ch;
    const n = Math.floor(data.size / (bps * ch)), out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let c = 0; c < ch; c++) {
        const o = data.at + (i * ch + c) * bps; let x;
        if (tagv === 3) x = bps === 8 ? d.getFloat64(o, true) : d.getFloat32(o, true);
        else if (bps === 1) x = (d.getUint8(o) - 128) / 128;
        else if (bps === 2) x = d.getInt16(o, true) / 32768;
        else if (bps === 3) { let v = d.getUint8(o) | (d.getUint8(o + 1) << 8) | (d.getUint8(o + 2) << 16); if (v & 0x800000) v -= 0x1000000; x = v / 8388608; }
        else if (bps === 4) x = d.getInt32(o, true) / 2147483648;
        else throw new Error(`${fmt.bits}-bit samples are not read here`);
        s += x;
      }
      out[i] = s / ch;
    }
    return { frames: out, rate: fmt.rate, cues: [...new Set(cues)].sort((a, b) => a - b) };
  }
  /* an AIFF or AIFF-C (NONE, sowt, fl32, fl64) -> as readWav; its markers are the cues */
  function readAiff(buf) {
    const d = new DataView(buf);
    const tag = (o) => String.fromCharCode(d.getUint8(o), d.getUint8(o + 1), d.getUint8(o + 2), d.getUint8(o + 3));
    if (buf.byteLength < 12 || tag(0) !== "FORM" || (tag(8) !== "AIFF" && tag(8) !== "AIFC")) throw new Error("not an AIFF file");
    let at = 12, comm = null, ssnd = null; const cues = [];
    const ext80 = o => {                       /* the 80-bit extended sample rate */
      const e = d.getUint16(o) & 0x7FFF, hi = d.getUint32(o + 2), lo = d.getUint32(o + 6);
      return e === 0 && hi === 0 && lo === 0 ? 0 : (hi * 2 ** 32 + lo) * 2 ** (e - 16383 - 63);
    };
    while (at + 8 <= buf.byteLength) {
      const id = tag(at), size = d.getUint32(at + 4), body = at + 8;
      if (id === "COMM") comm = { ch: d.getInt16(body), frames: d.getUint32(body + 2), bits: d.getInt16(body + 6), rate: ext80(body + 8),
                                  comp: tag(8) === "AIFC" && size >= 22 ? tag(body + 18).toLowerCase() : "none" };
      else if (id === "SSND") ssnd = { at: body + 8 + d.getUint32(body), size: Math.min(size - 8, buf.byteLength - body - 8) };
      else if (id === "MARK") { const n = d.getUint16(body); let m = body + 2; for (let k = 0; k < n; k++) { cues.push(d.getUint32(m + 2)); m += 6; const l = d.getUint8(m); m += 1 + l + ((l + 1) & 1); } }
      at = body + size + (size & 1);
    }
    if (!comm || !ssnd) throw new Error("no COMM or SSND chunk");
    const fl = comm.comp === "fl32" || comm.comp === "fl64", little = comm.comp === "sowt";
    if (!fl && !little && comm.comp !== "none") throw new Error(`compressed AIFF-C (${comm.comp}) is not read here`);
    const bps = fl ? (comm.comp === "fl64" ? 8 : 4) : Math.ceil(comm.bits / 8), ch = comm.ch;
    const n = Math.min(comm.frames, Math.floor(ssnd.size / (bps * ch))), out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let c = 0; c < ch; c++) {
        const o = ssnd.at + (i * ch + c) * bps; let x;
        if (fl) x = bps === 8 ? d.getFloat64(o) : d.getFloat32(o);
        else if (bps === 1) x = d.getInt8(o) / 128;
        else if (bps === 2) x = d.getInt16(o, little) / 32768;
        else if (bps === 3) { let v = little ? d.getUint8(o) | d.getUint8(o + 1) << 8 | d.getUint8(o + 2) << 16 : d.getUint8(o) << 16 | d.getUint8(o + 1) << 8 | d.getUint8(o + 2); if (v & 0x800000) v -= 0x1000000; x = v / 8388608; }
        else if (bps === 4) x = d.getInt32(o, little) / 2147483648;
        else throw new Error(`${comm.bits}-bit samples are not read here`);
        s += x;
      }
      out[i] = s / ch;
    }
    return { frames: out, rate: Math.round(comm.rate), cues: [...new Set(cues)].filter(c => c < n).sort((a, b) => a - b) };
  }

  function onsets(s, rate, most = 64) {
    const hop = Math.max(64, Math.floor(rate * 0.005)), env = [];
    for (let i = 0; i < s.length; i += hop) { let e = 0; const m = Math.min(s.length, i + hop); for (let j = i; j < m; j++) e += s[j] * s[j]; env.push(e / hop); }
    const gap = Math.max(1, Math.floor(0.05 * rate / hop)), floor = env.length ? Math.max(...env) * 1e-4 : 0;
    const out = [0]; let last = -gap;
    for (let k = 1; k < env.length; k++) {
      const lo = Math.max(0, k - 4); let p = 0; for (let j = lo; j < k; j++) p += env[j]; p /= Math.min(4, k);
      if (env[k] > floor && env[k] > 4 * (p + 1e-12) && k - last >= gap && k * hop - out[out.length - 1] >= 0.05 * rate) { out.push(k * hop); last = k; }
    }
    return out.slice(0, most);
  }
  function slicesFrom(starts, frames) {
    const s = [...new Set(starts.filter(x => x >= 0 && x < frames))].sort((a, b) => a - b).slice(0, C.MAX_SLICES);
    return s.map((a, k) => [a, k + 1 < s.length ? s[k + 1] : frames, a]);
  }
  function slicing(mode, w) {
    const n = w.frames.length;
    if (mode === "none") return [];
    if (mode.startsWith("grid:")) { const g = Math.max(1, Math.min(64, parseInt(mode.slice(5), 10))); return slicesFrom(Array.from({ length: g }, (_, k) => Math.floor(n * k / g)), n); }
    if (mode === "onsets") return slicesFrom(onsets(w.frames, w.rate), n);
    return w.cues.length ? slicesFrom(w.cues, n) : [];
  }
  function itemBytes(frames, nslices) {               /* a sample's frames and slice table, padded */
    let b = frames * 2;
    if (nslices) b += (4 - b % 4) % 4 + 12 * nslices;
    return b + (0x40 - b % 0x40) % 0x40;
  }

  /* items: [{frames: Float32Array, rate, name, slices: [[a,b,loop]]}] in slot order;
   * hole (bytes into the pool) skipped as dn2samples.py does -> Uint8Array */
  /* one sample's bytes as the pool holds them: int16 frames (normalised if over 1), then
   * its slice table on a word, padded to 0x40 */
  function itemData(it) {
    const f = it.frames, out = new Uint8Array(itemBytes(f.length, it.slices.length)), dv = new DataView(out.buffer);
    let peak = 0; for (let i = 0; i < f.length; i++) peak = Math.max(peak, Math.abs(f[i]));
    const g = peak > 1 ? 1 / peak : 1;
    for (let i = 0; i < f.length; i++) dv.setInt16(2 * i, Math.max(-32768, Math.min(32767, Math.round(f[i] * g * 32768))), true);
    if (it.slices.length) {
      let t = 2 * f.length; t += (4 - t % 4) % 4;
      it.slices.forEach(([a, b, lp], j) => { dv.setUint32(t + 12 * j, a, true); dv.setUint32(t + 12 * j + 4, b, true); dv.setUint32(t + 12 * j + 8, lp, true); });
    }
    return out;
  }
  function putEntry(dir, k, addr, it) {
    const dv = new DataView(dir.buffer, dir.byteOffset), e = 8 + 16 * k;
    dv.setUint32(e, addr, true); dv.setUint32(e + 4, it.frames.length, true);
    dv.setFloat32(e + 8, it.rate / C.DSP_RATE, true); dv.setUint32(e + 12, C.FMT_I16 | (it.slices.length << 8), true);
    const nm = (it.name || "").toUpperCase().slice(0, C.NAME_BYTES - 1);
    for (let j = 0; j < C.NAME_BYTES; j++) { const c = j < nm.length ? nm.charCodeAt(j) : 0; dir[C.NAMES_OFFSET + C.NAME_BYTES * k + j] = c < 128 ? c : 63; }
  }

  /* items: [{frames: Float32Array, rate, name, slices: [[a,b,loop]]} or null (an empty
   * slot)], slot 0 first; hole (bytes into the pool) skipped as dn2samples.py does -> Uint8Array */
  function poolBytes(items, hole = [C.REC_OFFSET, C.REC_END], base = C.POOL_DDR) {
    const place = []; let len = 0;
    for (const it of items) {
      if (!it) { place.push(0); continue; }
      const sz = itemBytes(it.frames.length, it.slices.length);
      if (hole && C.DATA_OFFSET + len < hole[1] && C.DATA_OFFSET + len + sz > hole[0]) len = hole[1] - C.DATA_OFFSET;
      place.push(C.DATA_OFFSET + len); len += sz;
    }
    const out = new Uint8Array(C.DATA_OFFSET + len), dv = new DataView(out.buffer);
    dv.setUint32(0, C.POOL_MAGIC, true); dv.setUint32(4, items.length, true);
    items.forEach((it, k) => {
      if (!it) return;
      putEntry(out, k, base + place[k], it);
      out.set(itemData(it), place[k]);
    });
    return out;
  }

  /* v0.24 tool, ADD: new samples into chosen slots, the instrument's others kept where they
   * are. The link writes the +Drive's image in 64 KB blocks, each from its start, and only
   * the blocks a send touches (link.c: up_flush): so the directory page alone (block 0,
   * DATA_OFFSET bytes), then the new samples from the first whole block after the kept
   * ones' data. kept: [{k, entry: 16 bytes, name}] (as this tool last sent them, checked
   * against the instrument), keptEnd: the end of their data; adds: [{k, frames, rate, name,
   * slices}] -> {dir: the directory page, at: where the new data goes, data, end: the image} */
  const BLOCK = 0x10000;
  function addPlan(kept, keptEnd, adds, hole = [C.REC_OFFSET, C.REC_END], base = C.POOL_DDR, meta = null) {
    const dir = new Uint8Array(C.DATA_OFFSET), dv = new DataView(dir.buffer);
    const taken = new Set(adds.map(a => a.k));
    let count = 0;
    for (const s of kept) {
      if (taken.has(s.k)) continue;                 /* an add in its slot replaces it */
      dir.set(s.entry, 8 + 16 * s.k);
      const nm = (s.name || "").slice(0, C.NAME_BYTES - 1);
      for (let j = 0; j < nm.length; j++) dir[C.NAMES_OFFSET + C.NAME_BYTES * s.k + j] = nm.charCodeAt(j) & 0x7F;
      count = Math.max(count, s.k + 1);
    }
    let at = Math.ceil(Math.max(keptEnd, C.DATA_OFFSET) / BLOCK) * BLOCK;
    if (hole && at >= hole[0] && at < hole[1]) at = hole[1];
    const start = at, parts = [];
    for (const a of [...adds].sort((x, y) => x.k - y.k)) {
      const d = itemData(a);
      if (hole && at < hole[1] && at + d.length > hole[0]) {      /* across the recordings: past them */
        parts.push(new Uint8Array(hole[1] - at)); at = hole[1];      /* (the send skips the hole) */
      }
      putEntry(dir, a.k, base + at, a);
      parts.push(d); at += d.length;
      count = Math.max(count, a.k + 1);
    }
    dv.setUint32(0, C.POOL_MAGIC, true); dv.setUint32(4, count, true);
    if (meta) {                                       /* v0.25: the names and folders after them */
      const m = metaAt(at, meta.length, hole);
      if (m > at) parts.push(new Uint8Array(m - at));
      parts.push(meta); putMetaPtr(dir, m, meta.length); at = m + meta.length;
    }
    const data = new Uint8Array(at - start); let o = 0;
    for (const p of parts) { data.set(p, o); o += p.length; }
    return { dir, at: start, data, end: at };
  }
  function payloadBytes(len) {                      /* what a send moves: all but the hole */
    return len > C.REC_END ? len - C.HOLE_BYTES : Math.min(len, C.REC_OFFSET);
  }
  function short(long) {                         /* v0.25: the instrument's seven letters of a long name */
    return long.toUpperCase().replace(/[^A-Z0-9 _#-]/g, "").slice(0, 7) || "SAMPLE";
  }
  function stem(name) {
    return name.replace(/\.[^.]*$/, "").toUpperCase().replace(/[^A-Z0-9 _#-]/g, "").slice(0, 7) || "SAMPLE";
  }
  /* v0.25: the meta block for SLOTS ([{long, folder}] or null, slot 0 first) -> bytes,
   * 512-padded; folders in order of first use, at most META_FOLDERS (the rest: none) */
  function metaBytes(slots) {
    const out = new Uint8Array(Math.ceil(C.META_BYTES / 512) * 512), dv = new DataView(out.buffer);
    const folders = [];
    const ascii = (str, max) => Array.from(str.slice(0, max), ch => { const c = ch.charCodeAt(0); return c >= 32 && c < 127 ? c : 63; });
    slots.forEach((m, k) => {
      const rec = 12 + C.META_FOLDERS * C.META_FOLDER_BYTES + C.META_SLOT_BYTES * k;
      out[rec] = 0xFF;
      if (!m) return;
      const f = (m.folder || "").trim().slice(0, C.FOLDER_MAX);
      if (f) {
        let i = folders.indexOf(f);
        if (i < 0 && folders.length < C.META_FOLDERS) { folders.push(f); i = folders.length - 1; }
        if (i >= 0) out[rec] = i;
      }
      out.set(ascii(m.long || "", C.LONG_MAX), rec + 4);
    });
    for (let k = slots.length; k < C.POOL_SLOTS; k++) out[12 + C.META_FOLDERS * C.META_FOLDER_BYTES + C.META_SLOT_BYTES * k] = 0xFF;
    dv.setUint32(0, C.META_MAGIC, true); dv.setUint32(4, 1, true); dv.setUint32(8, folders.length, true);
    folders.forEach((f, i) => out.set(ascii(f, C.META_FOLDER_BYTES - 1), 12 + C.META_FOLDER_BYTES * i));
    return out;
  }
  /* where a block of BYTES goes after an image of LEN: the next 512, past the recordings */
  function metaAt(len, bytes, hole = [C.REC_OFFSET, C.REC_END]) {
    let at = Math.ceil(len / 512) * 512;
    if (hole && at < hole[1] && at + bytes > hole[0]) at = hole[1];
    return at;
  }
  function putMetaPtr(dir, at, bytes) {
    const dv = new DataView(dir.buffer, dir.byteOffset);
    dv.setUint32(C.META_PTR, C.META_PTR_MAGIC, true); dv.setUint32(C.META_PTR + 4, at, true); dv.setUint32(C.META_PTR + 8, bytes, true);
  }
  /* POOL (poolBytes') with META after it, the directory pointing at it -> a new image */
  function attachMeta(pool, meta, hole = [C.REC_OFFSET, C.REC_END]) {
    const at = metaAt(pool.length, meta.length, hole), out = new Uint8Array(at + meta.length);
    out.set(pool); out.set(meta, at); putMetaPtr(out, at, meta.length);
    return out;
  }
  /* v0.31: one sample for the +Drive's library: int16 mono, as the pool holds it, no slices */
  function libSample(it) { return itemData({ frames: it.frames, slices: [] }).slice(0, 2 * it.frames.length); }
  function le32(v) { return [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255]; }
  function libBegin(frames, folder, rate, name) {
    const r = new DataView(new ArrayBuffer(4)); r.setFloat32(0, rate / C.DSP_RATE, true);
    const nm = [...String(name).toUpperCase().slice(0, C.LONG_MAX)].map(ch => { const c = ch.charCodeAt(0); return c >= 32 && c < 127 ? c : 63; });
    return [...le32(frames), C.FMT_I16, folder, ...new Uint8Array(r.buffer), ...nm];
  }
  function adler(b, s = 1) {
    let a = s & 0xFFFF, h = s >>> 16;
    for (let i = 0; i < b.length; i++) { a = (a + b[i]) % 65521; h = (h + a) % 65521; }
    return ((h << 16) | a) >>> 0;
  }
  function libList(p) {                          /* a LIST reply -> {count, rows: [{k, frames, folder, name}]} */
    const dv = new DataView(p.buffer, p.byteOffset, p.length), rows = [];
    for (let j = 0; j < 4; j++) {
      const o = 4 + 31 * j; let name = "";
      for (let c = 0; c < 24; c++) { const b = p[o + 7 + c]; if (!b) break; name += String.fromCharCode(b); }
      rows.push({ k: dv.getUint16(o, true), frames: dv.getUint32(o + 2, true), folder: p[o + 6], name });
    }
    return { count: dv.getUint32(0, true), rows };
  }
  /* v0.40: a dropped folder's path as the instrument's folders (dnfw.sampler.libtree.levels,
   * upper-cased as every name sent): '/' between levels, the spaces next to a '/' and empty
   * levels dropped, each cut to its record (31 at the top, 30 inside), LIMIT levels at most */
  function folderLevels(path, limit = C.LIB_DEPTH) {
    const parts = String(path).toUpperCase().replace(/[^ -~]/g, "").split("/"), out = [];
    parts.forEach((x, i) => {
      if (i > 0) x = x.replace(/^ +/, "");
      x = x.slice(0, C.FOLDER_MAX);
      if (i < parts.length - 1) x = x.replace(/ +$/, "");
      if (x) out.push(out.length ? x.slice(0, C.FOLDER_MAX - 1) : x);
    });
    return out.slice(0, limit);
  }
  /* v0.40: a TREE reply (31) -> {depth, parents: each folder's parent, -1 the top} */
  function libTree(p) { return { depth: p[0], parents: [...p.subarray(1, 65)].map(b => b === 0xFF ? -1 : b) }; }
  return { C, BLOCK, readAiff, libSample, le32, libBegin, adler, libList, folderLevels, libTree, metaBytes, metaAt, putMetaPtr, attachMeta, short, pack7, unpack7, request, parse, be32, rd32, readWav, onsets, slicesFrom, slicing, itemBytes, itemData, putEntry, poolBytes, addPlan, payloadBytes, stem };
})();
if (typeof module !== "undefined") module.exports = DN2;
