/* SPDX-License-Identifier: AGPL-3.0-or-later
 * The Wishes builder: the build in Python (Pyodide) off the page's thread.
 * The route is the command line's (tools/patcher/dn2patch.build with noboot=True, OS 1.12): the code
 * zip of the release's one build (scripts/wishes_bundle.py), the user's own Elektron files, nothing else.
 * In:  {zip: url, zipSha, modVersion, dn2Sha, inputs: ["dn2","dt2","md"(,"mnm")],
 *       files: {dn2, dt2, md[, mnm]}: {name, bytes}}
 * Out: {log: text} ... then {done: bytes, stock: the stock 1.12 .syx it was built from} or {error: text}
 * The page checks the bytes' sha256 against the gate record itself (wishes-verdict.js). */
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
importScripts(PYODIDE + "pyodide.js");

let py = null;
let tree = null;      // {sha, dir}: the unpacked code, kept between builds

async function hex(buf) {
  const h = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function fetchChecked(url, sha, what) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error("could not fetch " + what + " (" + r.status + ")");
  const b = new Uint8Array(await r.arrayBuffer());
  if ((await hex(b)) !== sha) throw new Error(what + "'s sha256 is not the one wishes.json lists; stopping");
  return b;
}

function shortError(err) {
  let msg = String(err && err.message || err);
  const m = msg.match(/(PatchError|ModError|DspError|VersionError): (.*)/);
  if (m) return m[2];
  if (msg.includes("Traceback")) {
    const lines = msg.trim().split("\n");
    const k = lines.findLastIndex(l => /^\w*(Error|Exception)\b/.test(l));
    return (k >= 0 ? lines.slice(k) : lines.slice(-1)).join(" ");
  }
  return msg;
}

self.onmessage = async (e) => {
  const d = e.data;
  const log = (t) => self.postMessage({ log: t });
  const t0 = performance.now();
  const stamp = () => ((performance.now() - t0) / 1000).toFixed(1) + " s";
  try {
    if (!py) {
      log("Loading Python (Pyodide, once)...");
      py = await loadPyodide({ indexURL: PYODIDE });
      log("Loading numpy and lzma (Pyodide's, once)... [" + stamp() + "]");
      await py.loadPackage(["numpy", "lzma"]);
      // the build tool's closing note is for its command-line users; the page's checks do that job
      const dev = /Nothing has been sent to an instrument|dnfw inspect|docs\/flashing\.md|recovery route .* is proven/;
      const out = (t) => { if (!dev.test(t)) log(t); };
      py.setStdout({ batched: out });
      py.setStderr({ batched: out });
      log("Python ready [" + stamp() + "]");
    }
    if (!tree || tree.sha !== d.zipSha) {
      log("Fetching the build code...");
      const zip = await fetchChecked(d.zip, d.zipSha, "the build code");
      const dir = "/tree" + Date.now();
      py.FS.mkdirTree(dir + "/code");
      py.unpackArchive(zip, "zip", { extractDir: dir + "/code" });
      // dnfw.modversion reads VERSION beside the code's folder; the bundle does not carry it
      py.FS.writeFile(dir + "/VERSION", d.modVersion + "\n");
      tree = { sha: d.zipSha, dir };
    }
    const run = "/run" + Date.now();
    py.FS.mkdirTree(run + "/in");
    for (const k of d.inputs) py.FS.writeFile(run + "/in/" + k, d.files[k].bytes);
    log("Building (about a minute or more; the page stays usable)... [" + stamp() + "]");
    py.globals.set("TREE", tree.dir);
    py.globals.set("RUN", run);
    py.globals.set("DN2SHA", d.dn2Sha);
    py.globals.set("MNM", d.inputs.includes("mnm") ? run + "/in/mnm" : null);
    const tb = performance.now();
    py.runPython(`
import sys, os, pathlib, hashlib
for m in [m for m in sys.modules if m == "dnfw" or m.startswith("dnfw.") or m in ("dn2patch", "noboot")]:
    del sys.modules[m]
for k in ("DT2_SECTIONS", "DT2_SECTION7", "MD_OS_BIN", "MNM_OS", "DN2MK2_PARTS"):
    os.environ.pop(k, None)          # the whole mod, as the tree builds it: nothing from an earlier run
sys.path = [p for p in sys.path if not p.startswith("/tree")]
sys.path.insert(0, TREE + "/code")
import dn2patch
dn2patch.WORK = pathlib.Path(RUN + "/work")
STOCK = dn2patch.unzip(pathlib.Path(RUN + "/in/dn2").read_bytes(), (".syx",))
if hashlib.sha256(STOCK).hexdigest() != DN2SHA:
    raise dn2patch.PatchError("the Digitone II file is not Elektron's OS 1.12 (another OS, or a modified file). Wishes is built only from the stock OS 1.12 file.")
SHA = dn2patch.build(RUN + "/in/dn2", RUN + "/in/dt2", RUN + "/in/md", RUN + "/out.syx", mnm=MNM, noboot=True)
pathlib.Path(RUN + "/stock.syx").write_bytes(STOCK)     # for the page's optional flash back to stock (it re-checks the sha256)
`);
    log("Built in " + ((performance.now() - tb) / 1000).toFixed(1) + " s [" + stamp() + " since this request]");
    const out = py.FS.readFile(run + "/out.syx");
    const stock = py.FS.readFile(run + "/stock.syx");
    for (const f of ["/out.syx", "/stock.syx"]) { try { py.FS.unlink(run + f); } catch (_) { /* the page has the bytes */ } }
    self.postMessage({ done: out, stock, buildSeconds: (performance.now() - tb) / 1000 }, [out.buffer, stock.buffer]);
  } catch (err) {
    self.postMessage({ error: shortError(err) });
  }
};
