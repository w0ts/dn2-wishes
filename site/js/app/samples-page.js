/* Sample Transfer: the page (Web MIDI ports, the two panes, memory, the
 * transfer queue, diagnostics, erase). Restyled by samples.html only; the
 * element ids and class names it sets are upstream's.
 *
 * Copied unchanged from De-Pattern/dn2mk2-firmware, tools/web/index.html
 * (its second inline <script>), commit 5b26e21d0f5d5aeb67fde8374739c553967f6495
 * (2026-11-12). AGPL-3.0-or-later, as the rest of that repository.
 *
 * A classic script loaded after js/samples-core.js, whose DN2 global it uses.
 */
(() => {
  const $ = id => document.getElementById(id);
  const C = DN2.C;
  const MB = 1 << 20;
  const fmtMB = b => (b / MB).toFixed(b < 10 * MB ? 2 : 1) + " MB";
  const fmtSize = b => b >= 1024 * MB ? (b / (1024 * MB)).toFixed(2) + " GB" : fmtMB(b);
  const fmtS = f => (f / C.DSP_RATE).toFixed(2) + " s";
  const log = t => { const l = $("log"); l.textContent += t + "\n"; l.scrollTop = l.scrollHeight; };

  let midi = null, out = null, inp = null, seq = 0x300, waiting = null;
  let dev = null;           /* {proto, room, ram, slots: [{k, off, frames, name}], lib: {rows, folders} | null} */
  let items = [];           /* [{file, name, w, slices, slot}] (slot: 0-based, for pick and add) */
  let mode = "lib";         /* lib (the +Drive library) | fill | pick | add (the project's slots) */
  let libAt = null;         /* the +Drive folder open on the right (its index), null: the folders */
  const libSel = new Set(); /* ticked on the right: entry numbers, and "f<N>" for whole folders */
  let queue = [];           /* the last send: [{name, into, bytes, st, cls}] */
  const esc = v => String(v).replace(/[<&>"]/g, ch => ({ "<": "&lt;", "&": "&amp;", ">": "&gt;", '"': "&quot;" })[ch]);
  /* into the library: the ticked samples, or all of them when none is ticked */
  const toSend = () => mode !== "lib" ? items : (items.some(it => it.sel) ? items.filter(it => it.sel) : items);
  const libFolder = f => (dev && dev.lib && dev.lib.folders[f]) || `FOLDER ${f + 1}`;
  /* v0.40: folders inside folders: F's parent (-1 the top), its path, whether G is F or inside it */
  const libParent = f => (dev && dev.lib && dev.lib.parents && dev.lib.parents[f] != null ? dev.lib.parents[f] : -1);
  const libChain = f => { const c = []; for (let g = f, n = 0; g >= 0 && n < 8; g = libParent(g), n++) c.unshift(g); return c; };
  const libPath = f => libChain(f).map(libFolder).join("/");
  const libUnder = (g, f) => libChain(g).includes(f);
  let keep = null;          /* add: {kept: [{k, entry, name}], end} once checked, else {why} */
  const MEM_KEY = "dn2.sent.v1";      /* what this browser last sent (the directory, for Add) */
  function memRead() { try { return JSON.parse(localStorage.getItem(MEM_KEY) || "null"); } catch (e) { return null; } }
  function memWrite(m) { try { localStorage.setItem(MEM_KEY, JSON.stringify(m)); } catch (e) { /* no storage: Add stays off */ } }
  function memFromDir(dir, end, metas = []) {      /* the directory page we sent -> what to remember */
    const dv = new DataView(dir.buffer, dir.byteOffset), entries = [];
    for (let k = 0; k < C.POOL_SLOTS; k++) {
      const addr = dv.getUint32(8 + 16 * k, true), fr = dv.getUint32(12 + 16 * k, true);
      if (!fr || addr < C.POOL_DDR + C.DATA_OFFSET) continue;
      let name = ""; for (let c = 0; c < C.NAME_BYTES; c++) { const b = dir[C.NAMES_OFFSET + C.NAME_BYTES * k + c]; if (!b) break; name += String.fromCharCode(b); }
      const m = metas[k] || {};
      entries.push({ k, e: Array.from(dir.subarray(8 + 16 * k, 24 + 16 * k)), name, off: addr - C.POOL_DDR, frames: fr,
                     long: m.long || "", folder: m.folder || "" });
    }
    return { entries, end, date: new Date().toISOString() };
  }
  /* Add is safe only if the instrument holds exactly what this browser last sent (its
   * recordings aside): every slot's place, length and name */
  function checkKeep() {
    if (!dev) return { why: "Connect first." };
    const m = memRead();
    if (!m || !Array.isArray(m.entries)) return { why: "This browser has not sent samples to this instrument yet: use Replace all once, then Add works from here." };
    const mine = dev.slots.filter(s => !s.rec), byK = new Map(m.entries.map(e => [e.k, e]));
    const same = mine.length === m.entries.length && mine.every(s => { const e = byK.get(s.k); return e && e.off === s.off && e.frames === s.frames && e.name === s.name; });
    if (!same) return { why: "The instrument's samples are not what this browser last sent (trimmed, renamed or recorded over there, or sent from elsewhere). Use Replace all once; Add works from then on." };
    return { kept: m.entries.map(e => ({ k: e.k, entry: Uint8Array.from(e.e), name: e.name, long: e.long || "", folder: e.folder || "" })), end: m.end };
  }
  function usedSlots() {               /* slots the list must not take by default */
    const u = new Set();
    if (dev) dev.slots.forEach(s => { if (s.rec || mode === "add") u.add(s.k); });
    return u;
  }
  function assignSlots() {
    if (mode === "lib") { items.forEach(it => { it.slot = null; }); return; }
    if (mode === "fill") { items.forEach((it, k) => { it.slot = k; }); return; }
    const used = usedSlots(), taken = new Set(items.filter(it => it.slot != null).map(it => it.slot));
    let next = 0;
    for (const it of items) {
      if (it.slot != null) continue;
      while (next < C.USER_SLOTS && (used.has(next) || taken.has(next))) next++;
      it.slot = next < C.USER_SLOTS ? next : null; taken.add(it.slot); next++;
    }
  }
  function slotProblems() {
    if (mode === "lib") return dev && dev.lib && toSend().length + dev.lib.rows.length > dev.lib.cap ? `The library holds ${dev.lib.cap.toLocaleString()} samples.` : "";
    if (mode === "fill") return items.length > C.USER_SLOTS ? `Only ${C.USER_SLOTS} slots.` : "";
    const seen = new Map();
    for (const it of items) {
      if (it.slot == null || it.slot < 0 || it.slot >= C.USER_SLOTS) return `Every sample needs a slot from 1 to ${C.USER_SLOTS}.`;
      if (seen.has(it.slot)) return `Two samples are on SAMP ${it.slot + 1}.`;
      seen.set(it.slot, it);
    }
    return "";
  }
  let rate = 40000;         /* bytes a second, measured as we go */

  /* -- MIDI -- */
  function fillPorts() {
    const os = $("outSel"), is = $("inSel");
    const pick = (sel, ports) => {
      const prev = sel.value; sel.innerHTML = "";
      for (const p of ports.values()) { const o = document.createElement("option"); o.value = p.id; o.textContent = p.name; sel.append(o); }
      const want = [...sel.options].find(o => o.value === prev) || [...sel.options].find(o => /digitone/i.test(o.textContent));
      if (want) sel.value = want.value;
    };
    pick(os, midi.outputs); pick(is, midi.inputs);
  }
  async function connect() {
    try {
      if (!navigator.requestMIDIAccess) throw new Error("this browser has no Web MIDI: use Chrome or Edge");
      if (!midi) { midi = await navigator.requestMIDIAccess({ sysex: true }); midi.onstatechange = fillPorts; fillPorts(); }
      out = midi.outputs.get($("outSel").value); inp = midi.inputs.get($("inSel").value);
      if (!out || !inp) throw new Error("pick the Digitone II's ports");
      inp.onmidimessage = e => {
        const r = DN2.parse(e.data);
        if (r && waiting && r.seq === waiting.seq && r.cmd === (waiting.cmd | 0x80)) { const w = waiting; waiting = null; clearTimeout(w.timer); w.resolve(r); }
      };
      const p = (await call(C.CMD.HELLO)).payload;
      const proto = (p[0] << 8) | p[1];
      dev = { proto, room: DN2.rd32(p, 2), ram: p.length >= 22 ? DN2.rd32(p, 18) : null, slots: [] };
      if (proto < 4) throw new Error(`sample link ${proto}: flash v0.22 or later for this tool (or use dn2samples.py)`);
      $("connState").textContent = "connected"; $("connState").className = "pill ok";
      const ram = { 0: ["RAM check not run yet", "warn"], 1: ["RAM check passed: all 400 MB load", "ok"], 2: ["RAM check FAILED: only the first 128 MB load", "bad"] }[dev.ram] || ["", ""];
      $("devInfo").textContent = `Sample link ${proto}. ${ram[0]}.`;
      $("devInfo").className = "note " + (ram[1] === "bad" ? "bad" : ram[1] === "warn" ? "warn" : "");
      await readDir();
      await readLib();
    } catch (e) {
      $("connState").textContent = "not connected"; $("connState").className = "pill bad";
      $("devInfo").textContent = String(e.message || e); $("devInfo").className = "note bad";
    }
    refresh();
  }
  function call(cmd, payload = [], timeout = 3000, tries = 3) {
    return new Promise((resolve, reject) => {
      const go = (left) => {
        seq = ((seq + 1) & 0xFFFF) || 1;
        const s = seq;
        const timer = setTimeout(() => { waiting = null; left > 1 ? go(left - 1) : reject(new Error("no answer from the instrument (USB CONFIG: USB MIDI or Overbridge?)")); }, timeout);
        waiting = { seq: s, cmd, timer, resolve: r => r.status ? reject(new Error(`command ${cmd}: ${["ok", "refused", "unknown command", "the +Drive refused the write"][r.status] || r.status}`)) : resolve(r) };
        out.send(DN2.request(s, cmd, payload));
      };
      go(tries);
    });
  }
  async function readDir() {
    const slots = [];
    for (let k0 = 0; k0 < C.POOL_SLOTS; k0 += 5) {
      const p = (await call(C.CMD.DIR, [k0])).payload;
      for (let j = 0; j < 5 && k0 + j < C.POOL_SLOTS; j++) {
        const off = DN2.rd32(p, 4 + 16 * j), fr = DN2.rd32(p, 8 + 16 * j);
        if (!fr) continue;
        let name = ""; for (let c = 0; c < 8; c++) { const b = p[12 + 16 * j + c]; if (!b) break; name += String.fromCharCode(b); }
        slots.push({ k: k0 + j, off, frames: fr, name, rec: off >= C.REC_OFFSET && off < C.REC_END });
      }
    }
    dev.slots = slots;
  }
  /* v0.31: the +Drive library's folders and entries (link 5 and later) */
  async function readLib() {
    dev.lib = null;
    if (dev.proto < 5) return;
    const folders = [];
    /* INFO first: v0.43's sixth word is how many folders the library holds (128; 64 before) */
    const ip = (await call(C.LIB.INFO, [])).payload, iw = o => ip[o] | ip[o + 1] << 8 | ip[o + 2] << 16 | (ip[o + 3] << 24 >>> 0);
    const nf = ip.length >= 24 && iw(20) > 64 && iw(20) <= 255 ? iw(20) : 64;
    /* v0.45: the second word is how many samples it holds (16,384; 2,048 before) */
    const cap = ip.length >= 8 && iw(4) >= 2048 && iw(4) <= 65536 ? iw(4) : 2048;
    for (let f0 = 0; f0 < nf; f0 += 4) {
      const p = (await call(C.LIB.FOLDERS, [f0])).payload;
      for (let j = 0; j < 4; j++) { let s = ""; for (let c = 0; c < 24; c++) { const b = p[24 * j + c]; if (!b) break; s += String.fromCharCode(b); } folders.push(s); }
    }
    const rows = [];
    let count = Infinity;
    for (let k0 = 0; k0 < cap && rows.length < count; k0 += 4) {
      const r = DN2.libList((await call(C.LIB.LIST, [k0 & 255, k0 >> 8])).payload);
      count = r.count;
      r.rows.forEach(e => { if (e.frames) rows.push(e); });
    }
    /* INFO: state, capacity, count, the +Drive's sectors, the library's first data sector: its room */
    const sectors = iw(12) >>> 0, first = iw(16) >>> 0;
    const room = sectors > first ? (sectors - first) * 512 : null;
    const used = rows.reduce((a, e) => a + Math.ceil(2 * e.frames / 512) * 512, 0);   /* whole sectors each */
    /* v0.40 (link 7): each folder's parent; before, every folder is at the top */
    let parents = folders.map(() => -1);
    if (dev.proto >= 7)                          /* v0.43: 64 a reply, from the folder asked for */
      for (let f0 = 0, all = []; f0 < nf; f0 += 64) {
        all.push(...DN2.libTree((await call(C.LIB.TREE, f0 ? [f0] : [])).payload).parents);
        parents = all.slice(0, nf);
      }
    dev.lib = { rows, folders, room, used, parents, nf, cap };
  }

  /* -- files -- */
  /* v0.25: a dropped folder: its WAVs, each with the folder's path (below the drop) */
  async function entriesOf(entry, path, out) {
    if (entry.isFile) {
      const f = await new Promise((res, rej) => entry.file(res, rej));
      f.folder = path; out.push(f);
    } else if (entry.isDirectory) {
      const rd = entry.createReader(), sub = path ? path + "/" + entry.name : entry.name;
      for (;;) {
        const batch = await new Promise((res, rej) => rd.readEntries(res, rej));
        if (!batch.length) break;
        for (const e of batch) await entriesOf(e, sub, out);
      }
    }
  }
  async function dropped(dt) {
    const out = [], plain = [];
    const ents = [...dt.items || []].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
    if (!ents.length) return addFiles([...dt.files]);
    for (const e of ents) { if (e.isDirectory) await entriesOf(e, "", out); else plain.push(e); }
    for (const e of plain) await entriesOf(e, "", out);
    out.sort((a, b) => (a.folder + "/" + a.name).localeCompare(b.folder + "/" + b.name, undefined, { numeric: true }));
    return addFiles(out);
  }
  let loading = null;             /* {done, total, skipped} while a batch of files is read */
  async function addFiles(files) {
    files = [...files];
    const audio = files.filter(f => AUDIO.test(f.name));
    const other = files.filter(f => !AUDIO.test(f.name) && !/^\./.test(f.name));
    other.forEach(f => log(`${f.name}: not an audio file, skipped`));
    loading = { done: 0, total: audio.length, skipped: other.length, bad: 0 };
    refresh();
    for (const f of audio) {
      if (mode !== "lib" && items.length >= C.USER_SLOTS) { log(`${f.name}: all ${C.USER_SLOTS} slots are taken`); break; }
      try {
        const w = await readAudio(await f.arrayBuffer());
        if (!w.frames.length) throw new Error("no frames");
        const long = f.name.replace(/\.[^.]*$/, "").slice(0, C.LONG_MAX);
        items.push({ file: f.name, long, name: DN2.short(long), folder: (f.folder || "").slice(0, C.PATH_MAX), w,
                     slices: DN2.slicing($("sliceSel").value, w), slot: null, sel: false });
      } catch (e) { loading.bad++; log(`${f.name}: ${e.message || e}`); }
      loading.done++;
      if (loading.done % 8 === 0) refresh();   /* a big folder shows up as it loads, not at the end */
    }
    const l = loading; loading = null;
    log(`${l.total} audio file(s) read${l.bad ? `, ${l.bad} could not be` : ""}${l.skipped ? `, ${l.skipped} other file(s) skipped` : ""}`);
    refresh();
  }
  /* WAV and AIFF read here (their own rate, cue points kept); FLAC, MP3, OGG, M4A and the
   * rest through the browser's decoder, at the DSP's 48 kHz */
  const AUDIO = /\.(wav|wave|aif|aiff|aifc|flac|mp3|ogg|oga|opus|m4a|aac|caf)$/i;
  async function readAudio(buf) {
    const m = String.fromCharCode(...new Uint8Array(buf, 0, Math.min(12, buf.byteLength)));
    if (m.startsWith("RIFF") && m.slice(8) === "WAVE") return DN2.readWav(buf);
    if (m.startsWith("FORM") && /AIF[FC]/.test(m.slice(8))) return DN2.readAiff(buf);
    const ctx = new OfflineAudioContext(1, 1, C.DSP_RATE);
    let ab;
    try { ab = await ctx.decodeAudioData(buf); } catch (e) { throw new Error("this browser cannot decode it"); }
    const n = ab.length, out = new Float32Array(n);
    for (let c = 0; c < ab.numberOfChannels; c++) { const x = ab.getChannelData(c); for (let i = 0; i < n; i++) out[i] += x[i] / ab.numberOfChannels; }
    return { frames: out, rate: ab.sampleRate, cues: [] };
  }
  function reslice() { items.forEach(it => { it.slices = DN2.slicing($("sliceSel").value, it.w); }); refresh(); }

  /* -- the page -- */
  function plan() {             /* -> {len: the image's end, send: bytes sent} without the audio */
    if (!items.length) return { len: 0, send: 0 };
    if (mode === "lib") { const b = toSend().reduce((a, it) => a + 2 * it.w.frames.length, 0); return { len: 0, send: b }; }
    if (mode === "add" && keep && keep.kept) {
      let at = Math.ceil(Math.max(keep.end, C.DATA_OFFSET) / DN2.BLOCK) * DN2.BLOCK, sent = 0;
      if (at >= C.REC_OFFSET && at < C.REC_END) at = C.REC_END;
      for (const it of [...items].sort((a, b) => a.slot - b.slot)) {
        const sz = DN2.itemBytes(it.w.frames.length, it.slices.length);
        if (at < C.REC_END && at + sz > C.REC_OFFSET) { sent += Math.max(0, C.REC_OFFSET - at); at = C.REC_END; }
        at += sz; sent += sz;
      }
      return { len: at, send: sent + C.DATA_OFFSET };
    }
    let len = 0;
    const order = mode === "pick" ? [...items].sort((a, b) => a.slot - b.slot) : items;
    for (const it of order) {
      const sz = DN2.itemBytes(it.w.frames.length, it.slices.length);
      if (C.DATA_OFFSET + len < C.REC_END && C.DATA_OFFSET + len + sz > C.REC_OFFSET) len = C.REC_END - C.DATA_OFFSET;
      len += sz;
    }
    return { len: C.DATA_OFFSET + len, send: DN2.payloadBytes(C.DATA_OFFSET + len) };
  }
  function refresh() {
    if (mode === "add") keep = checkKeep();
    assignSlots();
    const lib = mode === "lib";
    $("xfer").className = lib ? "lib-mode" : "proj-mode";
    $("tabLib").setAttribute("aria-selected", lib); $("tabProj").setAttribute("aria-selected", !lib);
    const tb = $("list").tBodies[0]; tb.innerHTML = "";
    const devAt = new Map(dev ? dev.slots.map(s => [s.k, s]) : []);
    items.forEach((it, k) => {
      const tr = document.createElement("tr"); tr.draggable = mode === "fill" || lib; tr.dataset.k = k;
      if (it.sel) tr.className = "sel";
      const sz = DN2.itemBytes(it.w.frames.length, it.slices.length);
      const slotCell = lib ? `<td class="slot proj-only"></td>` : mode === "fill" ? `<td class="slot">SAMP ${k + 1}</td>`
        : `<td class="slot">SAMP <input type="number" class="slotIn" min="1" max="${C.USER_SLOTS}" value="${it.slot == null ? "" : it.slot + 1}" style="width:4.5em"></td>`;
      const over = mode !== "fill" && !lib && it.slot != null && devAt.get(it.slot);
      tr.innerHTML = `<td class="ck"><input type="checkbox" class="selIn" ${it.sel ? "checked" : ""} aria-label="Select"></td>${slotCell}<td title="${esc(it.file)}"><input type="text" class="longIn" maxlength="${C.LONG_MAX}" value="${esc(it.long)}" style="text-transform:none"><div class="note slot" style="margin:2px 0 0">${esc(it.name)}${over ? ` <span class="pill warn">${over.rec ? "recording moves" : "replaces " + esc(over.name)}</span>` : ""}</div></td>
        <td><input type="text" class="folderIn" list="folderList" maxlength="${C.PATH_MAX}" value="${esc(it.folder)}" placeholder="${lib ? "INCOMING" : "–"}" style="text-transform:none"></td>
        <td class="num hide-sm">${(it.w.frames.length / it.w.rate).toFixed(2)} s</td>
        <td class="num proj-only hide-sm">${it.slices.length || "–"}</td><td class="num">${fmtMB(lib ? 2 * it.w.frames.length : sz)}</td><td><button class="x" title="Remove from the list">✕</button></td>`;
      tr.querySelector(".selIn").onchange = e => { it.sel = e.target.checked; refresh(); };
      tr.querySelector(".longIn").oninput = e => { it.long = e.target.value.replace(/[^ -~]/g, "").slice(0, C.LONG_MAX); it.name = DN2.short(it.long); tr.querySelector(".note").textContent = it.name; };
      tr.querySelector(".longIn").onchange = refresh;
      tr.querySelector(".folderIn").onchange = e => { it.folder = e.target.value.replace(/[^ -~]/g, "").trim().slice(0, C.PATH_MAX); refresh(); };
      const si = tr.querySelector(".slotIn");
      if (si) si.onchange = e => { const v = parseInt(e.target.value, 10); it.slot = Number.isFinite(v) ? v - 1 : null; refresh(); };
      tr.querySelector(".x").onclick = () => { items.splice(k, 1); refresh(); };
      if (lib) {                     /* drag onto the instrument: this row, or the ticked ones with it */
        tr.ondragstart = e => {
          if (!it.sel) { items.forEach(x => { x.sel = false; }); it.sel = true; }
          e.dataTransfer.setData("application/x-dn2-items", "1"); e.dataTransfer.effectAllowed = "copy";
          tr.classList.add("dragging");
        };
        tr.ondragend = () => { tr.classList.remove("dragging"); refresh(); };
      } else if (mode === "fill") {
        tr.ondragstart = e => { tr.classList.add("dragging"); e.dataTransfer.setData("text/plain", String(k)); };
        tr.ondragend = () => tr.classList.remove("dragging");
        tr.ondragover = e => e.preventDefault();
        tr.ondrop = e => { e.preventDefault(); e.stopPropagation(); const from = +e.dataTransfer.getData("text/plain"); if (Number.isFinite(from) && from !== k) { const [m] = items.splice(from, 1); items.splice(k, 0, m); refresh(); } };
      }
      tb.append(tr);
    });
    $("dropHint").style.display = items.length ? "none" : "";
    const nSel = items.filter(it => it.sel).length;
    $("listAll").checked = !!items.length && nSel === items.length;
    $("listAll").indeterminate = nSel > 0 && nSel < items.length;
    $("removeSelBtn").disabled = !nSel || busy;
    $("clearBtn").disabled = !items.length || busy;
    const fl = $("folderList"); fl.innerHTML = "";
    [...new Set([...items.map(it => it.folder), ...(memRead()?.entries || []).map(e => e.folder || "")].filter(Boolean))].forEach(f => { const o = document.createElement("option"); o.value = f; fl.append(o); });
    const prob = slotProblems();
    $("listNote").textContent = loading ? `Reading ${loading.done} of ${loading.total} audio file(s)…`
      : prob || (!items.length ? (lib ? "No samples yet." : `No samples yet. Slots 1–${C.USER_SLOTS} are yours.`)
      : lib ? `${items.length} sample(s)` + (nSel ? `, ${nSel} ticked` : "")
      : mode === "fill" ? `${items.length} sample(s) go to SAMP 1–${items.length}, in this order. Drag rows to change their slots.`
      : `${items.length} sample(s), each to the slot beside it.`);
    $("listNote").className = "note " + (prob ? "bad" : "");
    $("modeNote").textContent = {
      fill: "Everything of yours on the instrument is replaced by this list. Recordings stay.",
      pick: "Everything of yours on the instrument is replaced by this list, each sample in the slot you give it; the other slots are left empty. Recordings stay.",
      lib: dev && dev.proto < 5 ? "The library needs v0.31 or later on the instrument."
        : "The +Drive library is shared by every project; the project's slots do not change. On the instrument: FUNC + YES in the sample list, +DRIVE, the sample, RIGHT, LOAD TO PROJ. Slices are not kept in the library.",
      add: keep && keep.kept ? "Your samples on the instrument stay where they are; these go into the slots you give them (a slot that holds one of yours is replaced). Only the new samples are sent."
        : (keep ? keep.why : ""),
    }[mode];
    $("modeNote").className = "note " + ((mode === "add" && keep && !keep.kept) || (mode === "lib" && dev && dev.proto < 5) ? "warn" : "");
    $("sendNote").textContent = mode === "lib"
      ? "Each sample goes into the +Drive library one at a time, each checked as it lands. The project's samples and their slots stay as they are."
      : mode === "add"
      ? "Sends the new samples and the slot list only. They go to the +Drive first, then everything loads into the DSP again; they load at every power-on. If a send is cut off, send again with Replace all."
      : "Sending replaces your samples on the instrument with this list; recordings stay. The samples go to the +Drive first, then into the DSP; they load at every power-on.";

    /* memory */
    const ramOk = dev ? dev.ram === 1 : true;
    const top = ramOk ? C.POOL_BYTES : C.REC_OFFSET;
    const cap = (ramOk ? C.POOL_BYTES - C.HOLE_BYTES : C.REC_OFFSET) - C.DATA_OFFSET;
    const pl = plan(), send = Math.max(0, pl.send - (mode === "add" ? 0 : C.DATA_OFFSET));
    const now = dev ? dev.slots.filter(s => !s.rec).reduce((a, s) => a + s.frames * 2, 0) : null;
    const recs = dev ? dev.slots.filter(s => s.rec).reduce((a, s) => a + s.frames * 2, 0) : null;
    const kept = mode === "add" && keep && keep.kept ? Math.max(0, Math.min(keep.end, C.REC_OFFSET) - C.DATA_OFFSET) + Math.max(0, keep.end - C.REC_END) : 0;
    const used = mode === "add" ? (pl.len ? Math.max(0, Math.min(pl.len, C.REC_OFFSET) - C.DATA_OFFSET) + Math.max(0, pl.len - C.REC_END) : kept) : send;
    /* v0.31: into the +Drive library its room is the +Drive's, not the project pool's */
    const lr = dev && dev.lib ? dev.lib : null;
    const libSend = lib ? toSend().reduce((a, it) => a + Math.ceil(2 * it.w.frames.length / 512) * 512, 0) : 0;
    const libFree = lr && lr.room != null ? Math.max(0, lr.room - lr.used) : null;
    $("lCap").textContent = lib ? "room in the +Drive library" : "room for yours";
    $("lNow").textContent = lib ? "in the library now" : "yours on it now";
    $("sCap").textContent = lib ? (lr && lr.room != null ? fmtSize(lr.room) : "–") : fmtMB(cap);
    $("sNow").textContent = lib ? (lr ? fmtSize(lr.used) : "–") : now == null ? "–" : fmtMB(now);
    $("sSend").textContent = fmtSize(lib ? libSend : send);
    $("sLeft").textContent = lib ? (libFree == null ? "–" : fmtSize(Math.max(0, libFree - libSend))) : fmtMB(Math.max(0, cap - used));
    $("sRec").textContent = recs == null ? "–" : `${fmtMB(recs)} of ${fmtMB(C.REC_BYTES)}`;
    const secs = pl.send ? (pl.send / rate) : 0;
    $("sTime").textContent = pl.send ? (secs < 90 ? `${Math.ceil(secs)} s` : `${Math.round(secs / 60)} min`) : "–";
    const bar = $("bar"); bar.innerHTML = "";
    if (lib) {                                  /* the library's bar: what is in it, what you send */
      const whole = lr && lr.room ? lr.room : 1;
      const seg = (bytes, color, title) => { const d = document.createElement("div"); d.style.width = (100 * Math.min(bytes, whole) / whole) + "%"; d.style.background = color; d.title = title; bar.append(d); };
      if (lr && lr.room) { seg(lr.used, "var(--yours)", "in the library: " + fmtSize(lr.used)); seg(libSend, "var(--new)", "what you send: " + fmtSize(libSend)); }
    } else {
    const seg = (bytes, color, title) => { const d = document.createElement("div"); d.style.width = (100 * bytes / (cap + C.HOLE_BYTES)) + "%"; d.style.background = color; d.title = title; bar.append(d); };
    if (kept) seg(kept, "var(--yours)", "yours, kept: " + fmtMB(kept));
    seg(Math.min(mode === "add" ? Math.max(0, used - kept) : send, cap), "var(--new)", "what you send: " + fmtMB(send));
    if (recs) seg(recs, "var(--rec)", "recordings: " + fmtMB(recs));
    }
    const over = lib ? libFree != null && libSend > libFree : used > cap || pl.len > (ramOk ? C.POOL_BYTES : C.REC_OFFSET) || (!ramOk && pl.len > top);
    $("memNote").textContent = over && lib ? `Too much: the library has ${fmtSize(libFree)} free. Remove some samples, or delete some from the library (on the right).`
      : lib ? (lr && lr.room != null ? "The +Drive library, shared by every project. The project's own 400 MB (its slots) fills only when you load samples on the instrument." : "")
      : over ? `Too much: there is room for ${fmtMB(cap)}. Remove some samples.`
      : (!ramOk && dev ? "The instrument's RAM check did not pass this power-on, so only the first 128 MB load: room for 96 MB of yours." : "");
    $("memNote").className = "note " + (over ? "bad" : (!ramOk && dev ? "warn" : ""));
    document.querySelector(".legend").innerHTML = lib ? '<span><i style="background:var(--yours)"></i>in the library</span><span><i style="background:var(--new)"></i>what you send</span>' : (kept ? '<span><i style="background:var(--yours)"></i>yours, kept</span>' : "")
      + '<span><i style="background:var(--rec)"></i>recordings (kept)</span><span><i style="background:var(--new)"></i>what you send</span>';

    /* the right pane: the instrument's slots, or its +Drive library */
    const db = $("dev").tBodies[0]; db.innerHTML = "";
    if (dev) {
      const mine = new Set(mode !== "fill" ? items.map(it => it.slot) : []);
      dev.slots.forEach(s => {
        const tr = document.createElement("tr");
        const kind = s.rec ? "recording · kept" : mode === "add" ? (mine.has(s.k) ? "yours · replaced" : "yours · kept") : "yours · replaced by a send";
        tr.innerHTML = `<td class="slot">SAMP ${s.k + 1}</td><td class="slot">${esc(s.name) || "–"}</td><td class="num">${fmtS(s.frames)}</td><td>${kind}</td>`;
        db.append(tr);
      });
      $("devNote").textContent = dev.slots.length ? "Recordings stay where they are; a recording whose slot your list takes moves to the first empty slot." : "Nothing in the project's slots yet.";
    } else $("devNote").textContent = "";
    renderLib();
    if (!lib) $("crumb").textContent = dev ? "PROJECT SLOTS" : "";
    const ready = !!dev && !busy;
    $("reloadBtn").disabled = !ready;
    $("newFolderBtn").disabled = !ready || !lr;
    $("delSelBtn").disabled = !ready || !lr || !libSel.size;
    $("diagBtn").disabled = busy || !dev; $("eraseBtn").disabled = busy || !dev; $("diagCopy").disabled = !$("diagOut").textContent;
    $("rightEmpty").style.display = !dev ? "" : lib && !lr ? "" : "none";
    $("rightEmpty").textContent = !dev ? "Connect to see the instrument." : "The +Drive library needs v0.31 or later on the instrument.";
    const n = toSend().length;
    $("sendBtn").textContent = lib ? (n ? `Send ${n} →` : "Send →") : "Send →";
    $("intoNote").textContent = !items.length ? "" : !lib ? (mode === "fill" ? (items.length > 1 ? `to SAMP 1–${items.length}` : "to SAMP 1") : "to the slots given")
      : libAt != null ? `into ${libFolder(libAt)}` : "each into its folder";
    $("sendBtn").disabled = !dev || !n || over || busy || !!prob || (mode === "add" && !(keep && keep.kept))
      || (lib && (dev.proto < 5 || !lr));
    renderQueue();
  }

  /* the +Drive library on the right: its folders, or one folder's samples */
  function renderLib() {
    const lt = $("libT").tBodies[0]; lt.innerHTML = "";
    const lr = dev && dev.lib;
    $("libT").style.display = lr ? "" : "none";
    if (!lr) { $("crumb").textContent = ""; $("libNote").textContent = ""; return; }
    while (libAt != null && !lr.folders[libAt] && !lr.rows.some(e => e.folder === libAt)) libAt = libParent(libAt) < 0 ? null : libParent(libAt);   /* gone: the nearest above */
    const crumb = $("crumb"); crumb.innerHTML = "";
    const top = document.createElement(libAt == null ? "span" : "a"); top.textContent = "+DRIVE"; crumb.append(top);
    if (libAt != null) {                /* v0.40: each level of the path a link up to it */
      top.onclick = () => openFolder(null);
      libChain(libAt).forEach(g => { crumb.append(" / "); const a = document.createElement(g === libAt ? "span" : "a"); a.textContent = libFolder(g); if (g !== libAt) a.onclick = () => openFolder(g); crumb.append(a); });
    }
    const add = (html, cls, onopen) => { const tr = document.createElement("tr"); tr.innerHTML = html; if (cls) tr.className = cls; if (onopen) tr.onclick = e => { if (!e.target.closest("input,button")) onopen(); }; lt.append(tr); return tr; };
    const tick = (key, tr) => { const c = tr.querySelector(".ck input"); if (!c) return; c.checked = libSel.has(key); if (c.checked) tr.classList.add("sel"); c.onchange = e => { e.target.checked ? libSel.add(key) : libSel.delete(key); refresh(); }; };
    let keys = [];
    const nav = $("libNav"); nav.style.display = "none";
    /* the folders in the open one (v0.40: folders inside folders; the top: the top-level
     * ones), each with all it holds; then, in a folder, its own samples */
    const count = new Map(); lr.rows.forEach(e => count.set(e.folder, (count.get(e.folder) || 0) + 1));
    const fs = [...new Set([...lr.folders.map((n, f) => n ? f : -1).filter(f => f >= 0), ...count.keys()])]
      .filter(f => libParent(f) === (libAt == null ? -1 : libAt))
      .sort((a, b) => a < 2 || b < 2 ? a - b : libFolder(a).localeCompare(libFolder(b), undefined, { numeric: true }));
    fs.forEach(f => {
      const held = lr.rows.filter(e => libUnder(e.folder, f)), n = held.length, bytes = held.reduce((a, e) => a + 2 * e.frames, 0);
      const subs = lr.folders.filter((nm, g) => nm && g !== f && libUnder(g, f)).length;
      const what = [n ? n + " sample" + (n > 1 ? "s" : "") : "", subs ? subs + " folder" + (subs > 1 ? "s" : "") : ""].filter(Boolean).join(", ") || "empty";
      const tr = add(`<td class="ck">${n || (f >= 2 && dev.proto >= 6) ? `<input type="checkbox" aria-label="Select the folder">` : ""}</td><td><span class="ico">▸</span>${esc(libFolder(f))} <span class="note">${what}</span></td><td class="num">${n ? fmtSize(bytes) : ""}</td><td></td>`, "folder", () => openFolder(f));
      tick("f" + f, tr); if (n || (f >= 2 && dev.proto >= 6)) keys.push("f" + f);
    });
    if (libAt == null) {
      if (!fs.length) add(`<td></td><td class="note" colspan="3">The library is empty: send samples into it, or make a folder.</td>`);
    } else {
      const nIn = lr.rows.filter(e => e.folder === libAt).length;
      nav.style.display = ""; nav.querySelector(".here").textContent = libPath(libAt);
      $("upBtn").textContent = libParent(libAt) < 0 ? "‹ All folders" : "‹ " + libFolder(libParent(libAt));
      $("navCount").textContent = `${nIn} sample${nIn === 1 ? "" : "s"}`;
      const rows = lr.rows.filter(e => e.folder === libAt).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      const seen = new Map(); rows.forEach(e => seen.set(e.name, (seen.get(e.name) || 0) + 1));
      rows.forEach(e => {
        const tr = add(`<td class="ck"><input type="checkbox" aria-label="Select"></td><td class="slot" title="entry ${e.k}">${esc(e.name)}${seen.get(e.name) > 1 ? ` <span class="note">#${e.k}</span>` : ""}</td><td class="num">${fmtSize(2 * e.frames)}</td><td><button class="x" title="Delete from the +Drive">✕</button></td>`);
        tick(e.k, tr); keys.push(e.k);
        tr.querySelector(".x").onclick = () => libDelete([e.k]);
      });
      if (!rows.length && !fs.length) add(`<td></td><td class="note" colspan="3">Empty folder: drop audio files here, or select samples on the left and Send.</td>`);
    }
    const all = $("libAll"), nk = keys.filter(k => libSel.has(k)).length;
    all.checked = !!keys.length && nk === keys.length; all.indeterminate = nk > 0 && nk < keys.length; all.disabled = !keys.length;
    all.onchange = () => { keys.forEach(k => all.checked ? libSel.add(k) : libSel.delete(k)); refresh(); };
    const free = lr.room != null ? Math.max(0, lr.room - lr.used) : null;
    $("libNote").textContent = `${lr.rows.length} of ${(lr.cap || C.LIB_CAP).toLocaleString()} samples` + (free != null ? ` · ${fmtSize(free)} free` : "") + (libSel.size ? ` · ${selEntries().length} ticked` : "");
  }
  function openFolder(f) { libAt = f; libSel.clear(); refresh(); }
  function selEntries() {             /* the ticked samples, whole folders' included */
    const lr = dev && dev.lib; if (!lr) return [];
    return lr.rows.filter(e => libSel.has(e.k) || libChain(e.folder).some(g => libSel.has("f" + g)));   /* v0.40: a folder's folders too */
  }
  function renderQueue() {
    const qb = $("queue").tBodies[0]; qb.innerHTML = "";
    queue.forEach(q => { const tr = document.createElement("tr"); tr.innerHTML = `<td class="slot">${esc(q.name)}</td><td>${esc(q.into)}</td><td class="num">${fmtSize(q.bytes)}</td><td class="${q.cls || ""}">${esc(q.st)}</td>`; qb.append(tr); });
  }

  /* -- sending -- */
  let busy = false;
  /* WRITE BUF (whose byte 0 is the image's AT) in order, the recordings' hole skipped */
  async function writeOut(buf, at, progress) {
    const chunk = 512, end = at + buf.length;
    let p = at;
    while (p < end) {
      if (p >= C.REC_OFFSET && p < C.REC_END) { p = C.REC_END; continue; }
      let q = Math.min(p + chunk, end);
      if (p < C.REC_OFFSET && q > C.REC_OFFSET) q = C.REC_OFFSET;
      await call(C.CMD.WRITE, [...DN2.be32(p), ...buf.subarray(p - at, q - at)], 5000, 2);
      progress(q - p); p = q;
    }
  }
  /* delete library entries KS (after asking) */
  async function libDelete(ks, folders = []) {
    const lr = dev && dev.lib; if (busy || !lr || (!ks.length && !folders.length)) return;
    const rows = lr.rows.filter(e => ks.includes(e.k));
    /* v0.35: ticked folders go too once they are empty (the instrument's DROP, 26); v0.40:
     * with the folders inside them, the deepest first (the instrument refuses a folder that
     * still holds a folder) */
    folders = dev.proto >= 6 ? folders.filter(f => f >= 2) : [];
    folders = [...new Set(folders.flatMap(f => lr.folders.map((nm, g) => g).filter(g => g >= 2 && (lr.folders[g] || g === f) && libUnder(g, f))))]
      .sort((a, b) => libChain(b).length - libChain(a).length);
    const what = rows.length === 1 && !folders.length ? rows[0].name
      : [rows.length ? `${rows.length} sample${rows.length > 1 ? "s" : ""}` : "", folders.length ? `${folders.length} folder${folders.length > 1 ? "s" : ""}` : ""].filter(Boolean).join(" and ");
    if (!confirm(`Delete ${what} from the +Drive library? This cannot be undone. Project slots already loaded from ${rows.length === 1 ? "it" : "them"} keep their copies.`)) return;
    busy = true; refresh();
    let gone = 0;
    try {
      for (const e of rows) {
        $("sendState").textContent = `deleting ${gone + 1} of ${rows.length}`;
        await call(C.LIB.DELETE, [e.k & 255, e.k >> 8], 10000); gone++;
        log(`${e.name}: deleted from the +Drive`);
      }
      for (const f of folders) {
        const r = await call(C.LIB.DROP, [f], 10000, 1).catch(() => null);
        log(`${libPath(f)}: ${r ? "folder removed" : "folder kept (not empty?)"}`);
      }
      $("sendState").textContent = `deleted ${gone}`; $("sendState").className = "pill ok";
    } catch (x) { log(String(x.message || x)); $("sendState").textContent = "delete failed"; $("sendState").className = "pill bad"; }
    libSel.clear();
    try { await readLib(); } catch (x) { log(String(x.message || x)); }
    busy = false; refresh();
  }
  const folderBytes = name => [...String(name).toUpperCase()].map(ch => ch.charCodeAt(0)).filter(c => c >= 32 && c < 127).slice(0, C.FOLDER_MAX);
  async function newFolder() {
    if (busy || !dev || !dev.lib) return;
    const inside = libAt != null && dev.proto >= 7;        /* v0.40: in the folder that is open */
    const name = (prompt(inside ? `New folder in ${libPath(libAt)} (up to 30 letters):` : "New folder's name (up to 31 letters):", "") || "").trim();
    const b = folderBytes(name).filter(c => !inside || c !== 47).slice(0, inside ? C.FOLDER_MAX - 1 : C.FOLDER_MAX);
    if (!b.length) return;
    busy = true; refresh();
    try {
      const f = inside ? (await call(C.LIB.FOLDER_IN, [libAt, ...b], 10000)).payload[0]
                       : (await call(C.LIB.FOLDER, b, 10000)).payload[0];
      if (f === 0xFF || (inside && f === libAt)) throw new Error(inside && f === libAt ? `the instrument keeps folders ${C.LIB_DEPTH} levels deep at most` : `the instrument refused the folder (${(dev.lib && dev.lib.nf) || 64} folders at most)`);
      log(`folder ${String.fromCharCode(...b)} made`);
      await readLib(); libAt = f; libSel.clear();
    } catch (x) { log(String(x.message || x)); }
    busy = false; refresh();
  }
  async function sendLib() {
    const st = $("sendState"), list = [...toSend()], into = libAt != null ? libFolder(libAt) : null;
    const total = list.reduce((a, it) => a + 2 * it.w.frames.length, 0);
    /* v0.40 (link 7): a dropped folder's folders kept: each level made inside the one before
     * (FOLDER_IN), under the open folder if one is; six levels at most (deeper files go into
     * the sixth). Before: one flat folder per file, as it was */
    const nested = dev.proto >= 7;
    const levelsOf = it => DN2.folderLevels(it.folder || (libAt == null ? "INCOMING" : ""));
    queue = list.map(it => ({ it, name: it.long || it.name,
                              into: nested ? [...(libAt != null ? [libPath(libAt)] : []), ...levelsOf(it)].join("/") || "INCOMING"
                                           : into || (it.folder || "INCOMING").toUpperCase(),
                              bytes: 2 * it.w.frames.length, st: "waiting" }));
    const made = new Map(), capped = new Set();
    async function folderFor(it) {
      let at = libAt == null ? -1 : libAt, key = String(at);
      for (const lv of levelsOf(it)) {
        key += "/" + lv;
        if (!made.has(key)) {
          // the instrument answers a folder it cannot make with status 1 (call() rejects it as
          // "command 30: refused"): almost always the library's 64 folders (every level counts)
          const p = (await call(C.LIB.FOLDER_IN, [at < 0 ? 0xFF : at, ...folderBytes(lv)], 10000).catch(e => {
            throw new Error(/refused/.test(e.message) ? `folder ${lv}: the +Drive library has no room for another folder (${(dev.lib && dev.lib.nf) || 64} at most, every level counts): delete or merge some folders in the browser, then send again` : e.message); })).payload;
          if (p[0] === 0xFF) throw new Error(`folder ${lv}: refused (${(dev.lib && dev.lib.nf) || 64} folders at most)`);
          if (p[1] & 2 && !capped.has(at)) { capped.add(at); log(`${it.folder}: deeper than ${C.LIB_DEPTH} levels; the rest go into ${libFolder(p[0]) || "the sixth level"}`); }
          made.set(key, p[0]);
        }
        at = made.get(key);
      }
      return at < 0 ? (await call(C.LIB.FOLDER, folderBytes("INCOMING"))).payload[0] : at;
    }
    renderQueue();
    let done = 0; const t0 = performance.now();
    st.textContent = "to the +Drive library"; st.className = "pill";
    for (const q of queue) {
      const it = q.it;
      q.st = "sending"; q.cls = "st-run"; renderQueue();
      try {
        const fname = folderBytes(q.into);
        const f = nested ? await folderFor(it) : (await call(C.LIB.FOLDER, fname.length ? fname : folderBytes("INCOMING"))).payload[0];
        if (f === 0xFF) throw new Error(`folder ${q.into}: refused (${(dev.lib && dev.lib.nf) || 64} folders at most)`);
        const data = DN2.libSample({ frames: it.w.frames });
        const b = (await call(C.LIB.BEGIN, DN2.libBegin(it.w.frames.length, f, it.w.rate, it.long || it.name), 10000)).payload;
        const k = new DataView(b.buffer, b.byteOffset, b.length).getUint32(0, true);
        for (let o = 0; o < data.length; o += 512) {
          await call(C.LIB.WRITE, [...DN2.le32(o), ...data.subarray(o, Math.min(o + 512, data.length))], 5000, 1);
          done += Math.min(512, data.length - o);
          if ((done & 0xFFFF) < 512) {
            rate = done / Math.max((performance.now() - t0) / 1000, 0.001);
            $("prog").value = done / total;
            st.textContent = `to the +Drive library ${Math.floor(100 * done / total)} % · ${Math.ceil((total - done) / rate)} s left`;
            q.st = `sending ${Math.floor(100 * Math.min(o + 512, data.length) / data.length)} %`; renderQueue();
          }
        }
        await call(C.LIB.END, DN2.le32(DN2.adler(data)), 20000, 1);
        q.st = "✓ in the library"; q.cls = "st-ok";
        log(`${q.name}: in the library, ${q.into} (entry ${k})`);
        items.splice(items.indexOf(it), 1);
      } catch (e) {
        q.st = "failed: " + (e.message || e); q.cls = "st-bad";
        queue.filter(r => r.st === "waiting").forEach(r => { r.st = "not sent"; r.cls = "st-bad"; });
        renderQueue();
        throw e;
      }
      renderQueue();
    }
    await readLib();
    st.textContent = "done"; st.className = "pill ok"; $("prog").value = 1;
  }
  async function send() {
    busy = true; refresh();
    const st = $("sendState");
    if (mode === "lib") {
      try { await sendLib(); } catch (e) { st.textContent = "failed"; st.className = "pill bad"; log(String(e.message || e)); try { await readLib(); } catch (x) { /* shown on the next refresh */ } }
      busy = false; refresh(); return;
    }
    try {
      st.textContent = "building"; st.className = "pill";
      const audio = it => ({ frames: it.w.frames, rate: it.w.rate, name: it.name, slices: it.slices });
      let parts, end, remember, total;
      const metas = [];                       /* v0.25: each slot's long name and folder */
      const meta = it => ({ long: it.long, folder: it.folder });
      if (mode === "add") {
        const kp = checkKeep();
        if (!kp.kept) throw new Error(kp.why);
        kp.kept.forEach(e => { metas[e.k] = { long: e.long, folder: e.folder }; });
        items.forEach(it => { metas[it.slot] = meta(it); });
        const pl = DN2.addPlan(kp.kept, kp.end, items.map(it => ({ k: it.slot, ...audio(it) })), undefined, undefined,
                               DN2.metaBytes(Array.from({ length: C.POOL_SLOTS }, (_, k) => metas[k] || null)));
        parts = [[pl.dir, 0], [pl.data, pl.at]]; end = pl.end;
        remember = memFromDir(pl.dir, pl.end, metas);
      } else {
        let list;
        if (mode === "fill") { list = items.map(audio); items.forEach((it, k) => { metas[k] = meta(it); }); }
        else { list = []; items.forEach(it => { while (list.length <= it.slot) list.push(null); list[it.slot] = audio(it); metas[it.slot] = meta(it); }); }
        const pool = DN2.attachMeta(DN2.poolBytes(list), DN2.metaBytes(Array.from({ length: C.POOL_SLOTS }, (_, k) => metas[k] || null)));
        parts = [[pool, 0]]; end = pool.length;
        remember = memFromDir(pool.subarray(0, C.DATA_OFFSET), pool.length, metas);
      }
      total = parts.reduce((a, [b, at]) => a + b.length - Math.max(0, Math.min(at + b.length, C.REC_END) - Math.max(at, C.REC_OFFSET)), 0);
      log(`${items.length} sample(s), image to ${fmtMB(end)}, ${fmtMB(total)} to send`);
      queue = items.map(it => ({ name: it.long || it.name, into: "SAMP " + (it.slot + 1), bytes: DN2.itemBytes(it.w.frames.length, it.slices.length), st: "in this send", cls: "st-run" })); renderQueue();
      await call(C.CMD.BEGIN, DN2.be32(end), 10000);
      st.textContent = "to the +Drive"; let done = 0; const t0 = performance.now();
      for (const [buf, at] of parts) {
        await writeOut(buf, at, n => {
          done += n;
          if ((done & 0xFFFF) < 512) {
            const el = (performance.now() - t0) / 1000; rate = done / Math.max(el, 0.001);
            $("prog").value = done / total;
            st.textContent = `to the +Drive ${Math.floor(100 * done / total)} % · ${Math.ceil((total - done) / rate)} s left`;
          }
        });
      }
      await call(C.CMD.END, [], 20000);
      memWrite(remember);
      st.textContent = "into the DSP"; $("prog").value = 0;
      for (;;) {
        const p = (await call(C.CMD.STATUS)).payload;
        const state = DN2.rd32(p, 4), loaded = DN2.rd32(p, 8);
        $("prog").value = Math.min(1, loaded / Math.max(1, end));
        if (state === 4) break;
        if (state === 0) throw new Error("the load stopped: the samples are on the +Drive; power-cycle to load them again");
        await new Promise(r => setTimeout(r, 1000));
      }
      st.textContent = "done"; st.className = "pill ok"; $("prog").value = 1;
      queue.forEach(q => { q.st = "✓ in the slot"; q.cls = "st-ok"; });
      log(`done: ${mode === "fill" ? `SAMP 1–${items.length}` : items.map(it => "SAMP " + (it.slot + 1)).join(", ")}; they load at every power-on`);
      await readDir();
      if (mode === "add") items = [];        /* they are on it now: the list starts again */
    } catch (e) {
      st.textContent = "failed"; st.className = "pill bad"; log(String(e.message || e));
      queue.forEach(q => { q.st = "failed: send again"; q.cls = "st-bad"; });
    }
    busy = false; refresh();
  }

  /* -- wiring -- */
  $("connectBtn").onclick = connect;
  /* v0.36: the diagnostics (link commands 24 DIAG, 25 SCAN, 27 ENTRY; tools/dn2diag.py does the same) */
  const DIAG_KEYS = ["wipes", "info", "where", "mask", "since", "load", "loadPeak", "skipped", "periods", "frames",
                     "scanCount", "scanFirst", "scanDone", "scanSeq"];
  const SCANS = [["voice 1's P-I delay lines", 0x82200000, 2048], ["voice 4's P-I delay lines", 0x82206000, 2048],
                 ["the 16 voices' Machinedrum state", 0x200A0000, 4096], ["the 16 voices' PERC state", 0x2DE180, 512]];
  async function diag() {
    const p = (await call(C.CMD.DIAG, [], 3000, 2)).payload, d = {};
    DIAG_KEYS.forEach((k, i) => d[k] = DN2.rd32(p, 4 * i));
    return d;
  }
  async function scan(addr, words) {
    const be = v => [v >>> 24 & 255, v >>> 16 & 255, v >>> 8 & 255, v & 255];
    const p = (await call(C.CMD.SCAN, [...be(addr), ...be(words)], 3000, 2)).payload;
    const seq = (p[0] << 8) | p[1], t0 = Date.now();
    while (Date.now() - t0 < 5000) {
      const d = await diag();
      if (d.scanSeq === seq && d.scanDone === (seq & 0xFFFF)) return { n: d.scanCount, first: d.scanFirst === 0xFFFFFFFF ? -1 : d.scanFirst };
      await new Promise(r => setTimeout(r, 60));
    }
    throw new Error("a memory scan did not finish");
  }
  function entryVerdict(base, frames, fmt, pool) {
    const off = base - pool, f = fmt & 255;
    if (off < C.DATA_OFFSET) return "plays as empty (its start is before the pool's data)";
    if (off >= C.POOL_BYTES) return "plays as empty (its start is past the pool)";
    if (!frames || frames > C.POOL_BYTES / 4) return `plays as empty (${frames} frames)`;
    if (f > 1) return `plays as empty (format ${f})`;
    if (off + frames * (f ? 2 : 4) > C.POOL_BYTES) return "plays as empty (it runs past the pool)";
    return "plays";
  }
  async function runDiag() {
    if (busy || !dev) return;
    busy = true; refresh();
    const out = [], say = s => { out.push(s); $("diagOut").textContent = out.join("\n"); };
    $("diagState").textContent = "running"; $("diagState").className = "pill";
    $("diagOut").textContent = "";
    try {
      say(`DN2 diagnostics, ${new Date().toLocaleString()}, sample link ${dev.proto}`);
      const d = await diag();
      say(`DSP load ${d.load} % (peak ${(d.loadPeak / 10).toFixed(1)} %), ${d.frames.toLocaleString()} audio frames since power-on`);
      if (d.wipes) {
        const slot = (d.info & 255) + 1, type = d.info >>> 8, w = d.where;
        const where = w !== 0xFFFF && (w & 0x8000) ? `its delay lines, word ${w & 0x7FFF}` : "not its delay lines (its own state, its input or the effects)";
        const ago = d.since === 0xFFFFFFFF ? "" : `, the last ${(d.since / 1500).toFixed(1)} s ago`;
        say(`The output guard silenced a bad voice ${d.wipes} time(s)${ago}: last voice ${slot}, machine type ${type}, the bad value in ${where}`);
      } else say("The output guard has silenced no voice since power-on");
      if (d.skipped) say(`Voices left out for DSP time: ${[...Array(16).keys()].filter(t => d.skipped >> t & 1).map(t => t + 1).join(", ")}`);
      say("Memory scans (bad values: not-a-number or infinite words):");
      for (const [name, addr, words] of SCANS) {
        const r = await scan(addr, words);
        say(`  ${name}: ${r.n ? `${r.n} bad word(s), the first at index ${r.first}` : "clean"}`);
      }
      if (dev.proto >= 6) {
        say("Project slots (what the DSP makes of each):");
        for (const sl of dev.slots) {
          const p = (await call(C.CMD.ENTRY, [sl.k], 3000, 2)).payload;
          const dv = new DataView(Uint8Array.from(p).buffer);
          const base = dv.getUint32(0, true), frames = dv.getUint32(4, true), fmt = dv.getUint32(12, true), pool = DN2.rd32(p, 24);
          say(`  slot ${sl.k + 1} ${sl.name || "(no name)"}${sl.rec ? " (recording)" : ""}: ${entryVerdict(base, frames, fmt, pool)}`);
        }
      }
      $("diagState").textContent = "done"; $("diagState").className = "pill ok";
    } catch (x) {
      const m = String(x.message || x);
      say(/unknown command/.test(m) ? "This firmware has no diagnostics: v0.34 or later is needed." : `Stopped: ${m}`);
      $("diagState").textContent = "failed"; $("diagState").className = "pill bad";
    }
    busy = false; refresh();
  }
  /* v0.39: ERASE MOD DATA (link commands 28 ERASE, 29 its status; docs/erase-mod-data.md) */
  const ERASE_WHY = ["", "refused (outside the mod's regions)", "the card's erase failed 5 times", "a read failed 5 times", "a sector did not erase", "the +Drive is not ready", "the card stayed busy"];
  async function runErase() {
    if (busy || !dev) return;
    if (!confirm("Erase ALL samples and mod data on the instrument's +Drive?\n\nThe pool, every project's sample list, the +Drive library and the mod's settings. Elektron's projects, sounds and presets are not touched.")) return;
    if (!confirm("Are you sure? This cannot be undone.")) return;
    busy = true; refresh();
    const st = $("eraseState"), say = (t, c) => { st.textContent = t; st.className = "pill" + (c ? " " + c : ""); };
    try {
      await call(28, [69, 82, 65, 83, 69], 3000, 2);                  // "ERASE"
      for (;;) {
        await new Promise(r => setTimeout(r, 500));
        const p = (await call(29, [], 3000, 3)).payload;
        const state = p[0], err = p[1], done = DN2.rd32(p, 4), total = DN2.rd32(p, 8), sector = DN2.rd32(p, 12);
        const checks = DN2.rd32(p, 28), nchecks = DN2.rd32(p, 32);
        if (state === 1) say(`erasing ${total ? Math.floor(100 * done / total) : 0} %`);
        else if (state === 2) say(`verifying ${nchecks ? Math.floor(100 * checks / nchecks) : 0} %`);
        else if (state === 3) { say("ERASED: restart the instrument", "ok"); break; }
        else if (state === 4 || err) {
          const goOn = p.length > 52 && p[52];                           // v0.41: asking again carries on
          say(`${goOn ? "paused" : "failed"}: ${ERASE_WHY[err] || err} at sector 0x${sector.toString(16)}${goOn ? " (press Erase again to continue)" : ""}`, "bad"); break;
        }
      }
    } catch (x) {
      const m = String(x.message || x);
      say(/unknown command/.test(m) ? "this firmware cannot erase: v0.39 or later is needed" : `stopped: ${m}`, "bad");
    }
    busy = false; refresh();
  }
  $("eraseBtn").onclick = runErase;
  $("diagBtn").onclick = runDiag;
  $("diagCopy").onclick = () => { try { navigator.clipboard.writeText($("diagOut").textContent); $("diagState").textContent = "copied"; } catch (e) {} };
  $("browseBtn").onclick = () => $("fileIn").click();
  $("fileIn").onchange = e => { addFiles([...e.target.files]); e.target.value = ""; };
  const drop = $("drop"), right = $("rightPane");
  const isItems = e => [...e.dataTransfer.types].includes("application/x-dn2-items");
  ["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { if (isItems(e)) return; e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => { if (!isItems(e)) dropped(e.dataTransfer); });
  /* onto the instrument: rows from the left, or WAVs straight from the computer (into the open folder) */
  const canTake = () => mode === "lib" && dev && dev.lib && !busy;
  ["dragenter", "dragover"].forEach(t => right.addEventListener(t, e => { if (!canTake()) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; right.classList.add("over"); }));
  right.addEventListener("dragleave", e => { if (!right.contains(e.relatedTarget)) right.classList.remove("over"); });
  right.addEventListener("drop", async e => {
    e.preventDefault(); right.classList.remove("over");
    if (!canTake()) return;
    if (!isItems(e)) {
      const before = new Set(items);
      await dropped(e.dataTransfer);
      const fresh = items.filter(it => !before.has(it));
      if (!fresh.length) return;
      items.forEach(it => { it.sel = fresh.includes(it); });
    }
    refresh();
    if (!$("sendBtn").disabled) send();
  });
  $("folderBtn").onclick = () => $("dirIn").click();
  $("dirIn").onchange = e => {
    const fs = [...e.target.files].map(f => { const p = (f.webkitRelativePath || "").split("/"); f.folder = p.slice(0, -1).join("/"); return f; });
    fs.sort((a, b) => (a.folder + "/" + a.name).localeCompare(b.folder + "/" + b.name, undefined, { numeric: true }));
    addFiles(fs); e.target.value = "";
  };
  $("sliceSel").onchange = reslice;
  $("modeSel").onchange = e => { mode = e.target.value; items.forEach(it => { if (mode === "fill") it.slot = null; }); refresh(); };
  $("tabLib").onclick = () => { if (busy) return; mode = "lib"; refresh(); };
  $("tabProj").onclick = () => { if (busy) return; mode = $("modeSel").value; items.forEach(it => { if (mode === "fill") it.slot = null; }); refresh(); };
  $("clearBtn").onclick = () => { items = []; refresh(); };
  $("removeSelBtn").onclick = () => { items = items.filter(it => !it.sel); refresh(); };
  $("listAll").onchange = e => { items.forEach(it => { it.sel = e.target.checked; }); refresh(); };
  $("newFolderBtn").onclick = newFolder;
  $("upBtn").onclick = () => openFolder(libAt == null || libParent(libAt) < 0 ? null : libParent(libAt));   /* v0.40: up a level */
  $("delSelBtn").onclick = () => libDelete(selEntries().map(e => e.k), [...libSel].filter(k => typeof k === "string" && k[0] === "f").map(k => +k.slice(1)));
  $("reloadBtn").onclick = async () => { if (busy || !dev) return; busy = true; refresh(); try { await readDir(); await readLib(); } catch (x) { log(String(x.message || x)); } busy = false; refresh(); };
  $("sendBtn").onclick = send;
  if (navigator.requestMIDIAccess) navigator.requestMIDIAccess({ sysex: true }).then(m => { midi = m; m.onstatechange = fillPorts; fillPorts(); }).catch(() => {});
  else { $("devInfo").textContent = "This browser has no Web MIDI: use Chrome or Edge."; $("devInfo").className = "note bad"; }
  refresh();
})();
