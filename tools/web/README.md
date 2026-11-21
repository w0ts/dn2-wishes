# Wishes sample import (browser)

`index.html` (+ `wishes.css`, the look it shares with the builder) is the whole tool: one page, no server, no packages. It does what
`tools/dn2samples.py send` does, with a window: pick the Digitone II's MIDI ports, drop or
browse WAVs, see which slot each goes to and how much memory is used, sent and left, and
send them over USB (SysEx, sample link 4; firmware v0.22 or later).

- **Run it:** open `index.html` in Chrome or Edge (from disk works), or host it on any
  static site (GitHub Pages from a public repo). Allow MIDI with SysEx when asked.
- **What a send does:** your samples on the instrument are replaced by the list, in its
  order (SAMP 1, 2, ...); recordings stay. The samples go to the +Drive, then into the DSP,
  and load at every power-on.
- **Memory:** 368 MB for yours when the instrument's power-on RAM check passed, else 96 MB
  (`docs/sampler.md`, "400 MB, and a RAM check"). The 32 MB recordings area is skipped.
- `test/test_web_tool.py` runs the page's core under node and checks it builds the same
  image and SysEx as `dn2samples.py`, byte for byte.

## Icon

The page carries its own favicon (embedded in `index.html`, so it shows even when the
file is opened on its own). `icons/` holds the same mark for a desktop shortcut:

- **Windows:** right-click the desktop, **New > Shortcut**, point it at Chrome or Edge with
  the page, e.g. `"C:\Program Files\Google\Chrome\Application\chrome.exe" --app="file:///C:/path/to/tools/web/index.html"`,
  then **Properties > Change Icon...** and pick `icons/wishes.ico`.
- `icons/wishes-512.png` and `icons/wishes-180.png` for anything else (macOS, a
  home-screen icon).

# Wishes builder (browser)

`builder.html` (+ `builder-worker.js`, `wishes-verdict.js`, `wishes-flash.js`, `wishes.css`) builds Wishes for
Digitone II OS 1.12 in the browser (Pyodide 0.27.7, numpy, lzma), from the user's own
Elektron files, by the command line's route: `tools/patcher/dn2patch.build(..., noboot=True)`,
which takes the DSP image the 1.12 build reads (`DT2_SECTIONS`) from the DN2 file itself.

**One build per release, nothing to choose** (the User, 2026-11-19: "we don't have any
customisation anymore, on purpose, everything fits"). The page has three steps, and an optional fourth:

1. **Your stock files:** only the files the release's build reads (its `inputs`: today the
   Digitone II OS 1.12, Digitakt II OS 1.17/1.16, Machinedrum UW OS 1.63 and Monomachine
   OS 1.32B), remembered in the browser.
2. **Build:** one button. A release picker shows only when wishes.json lists more than one
   release (newest first). The release's box shows its file, sha256, gate verdict and room left
   (DSP upload, USB image).
3. **Save and flash:** **Save appears only when the build's sha256 is the one the release's
   gate record clears** (`wishes-verdict.js`); otherwise the page says "not the cleared file; do
   not flash" and shows both hashes. Then: back up with Elektron Transfer, send the .syx with
   Transfer, power-cycle once; back to stock 1.12 the same way with Elektron's own file.
4. **Flash from this page (optional, Chrome/Edge Web MIDI):** shown only beside a CLEARED build.
   It sends the build's verified bytes in memory (or the step-1 stock 1.12 file, only when its
   sha256 is the release's `dn2_sha256`) the way Elektron Transfer does: `wishes-flash.js`,
   byte for byte the OsUpgradeStart/Write messages of a recorded Transfer update (2,048-byte
   chunks, Transfer's CRC variant, one write waiting for its 0xD1 at a time, ~5 ms after each
   reply). Before the start: Ping and SoftwareVersion must answer from a Digitone II on OS 1.12,
   the file passes a packet-by-packet check and the 2 MiB receive limit, the User ticks a
   checklist and confirms once more. Abort sends the cancel (0x52 00) before the last chunk; the
   page never sends a commit: the DN2 asks UPGRADE OS NOW? itself. Checked by
   `scripts/web_flash_check.mjs` (`test/test_web_flash.py`), which also replays the recording.

No release published (no `wishes/wishes.json`, or an empty list): the page says "No release
published yet." in a plain note. Any other load error (a bad response, bad JSON, rows it cannot
build) stays a red error.

- **Bundle:** `python scripts/web_bundle.py --wishes BUILD.syx RELEASE wishes`
  (`DN2_OS112`, `DN2_STOCK_DIR` name Elektron's files) refuses a build without a CLEARED
  `BUILD.syx.gate.json`, rebuilds it the browser's way, then from the zip alone in a clean
  interpreter, and writes the release's row at the top of `wishes/wishes.json` (one build:
  `release, mod_version, os, file, sha256, gate, zip, zip_sha256, inputs, dn2_sha256, budgets`),
  `wishes/vRELEASE/code-<sha>.zip` and the record's verdicts (no paths). The saved file is
  `DN2wishes_vRELEASE.syx`. `--uncleared-test` runs the same pipeline with `"gate": null` (no
  Save; never published).
- **Publish:** `.github/workflows/wishes-pages.yml`, manual only; it runs
  `web_bundle.py --check-site wishes` and stops unless a release is listed, every row is one build
  in that format (the old per-preset rows are refused), every zip is the one listed and every
  listed build has a record that clears it.
- **Try it locally:** `bash scripts/make_site.sh OUTDIR --preview`, copy a bundle into
  `OUTDIR/wishes/` if you have one, and serve OUTDIR over http (`python3 -m http.server`).
- `help.html` shows the version of the newest release in `wishes/wishes.json` (no version when
  none is published).
- Every page carries the same line at the top: the builder, the sample import, help and the repository.
- `test/test_wishes_builder.py`: the refuse-unless-cleared rule (bundler, site check, page) and the
  page's one-build layout; `test/test_help_page.py`: the help page.
