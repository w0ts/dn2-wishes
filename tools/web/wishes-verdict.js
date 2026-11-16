/* SPDX-License-Identifier: AGPL-3.0-or-later
 * The Wishes builder's one rule (scripts/wishes_bundle.py, docs: scratch/builder-port-design.md §4):
 * a built file may be saved only when it is byte for byte a file that the project's gate cleared.
 *   cleared(record, sha): the gate record (scripts/ship_gate.py's .gate.json, as the site publishes
 *     it) names this sha256 and every gate passed (n/a: a step that did not apply);
 *   verdict(preset, record, got): {save, text, got, want}. save is true only when the preset lists a
 *     record, that record clears the preset's sha256, and the build's own sha256 GOT is that sha256.
 * Shared by builder.html and the tests (node). */
"use strict";
(function (root) {
  const HEX = /^[0-9a-f]{64}$/;
  function cleared(record, sha) {
    if (!record || typeof record !== "object" || !HEX.test(String(sha)) || record.sha256 !== sha) return false;
    const g = record.gates;
    if (!g || typeof g !== "object" || !Object.keys(g).length) return false;
    return Object.values(g).every(v => /^(PASS|n\/a)/.test(String(v)));
  }
  function verdict(preset, record, got) {
    const want = preset && preset.sha256;
    const no = (text) => ({ save: false, text, got, want: want || null });
    if (!HEX.test(String(got))) return no("The build gave no file; do not flash.");
    if (!preset || !preset.gate || !record) return no("Not the cleared file; do not flash. No gate record clears this version yet.");
    if (!cleared(record, want)) return no("Not the cleared file; do not flash. The gate record does not clear this version's file.");
    if (got !== want) return no("Not the cleared file; do not flash. Your build differs from the cleared file.");
    return { save: true, text: "The cleared file, byte for byte.", got, want };
  }
  const api = { cleared, verdict };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WishesVerdict = api;
})(typeof self !== "undefined" ? self : this);
