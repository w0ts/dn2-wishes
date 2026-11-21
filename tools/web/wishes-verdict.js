/* SPDX-License-Identifier: AGPL-3.0-or-later
 * The Wishes builder's one rule (scripts/wishes_bundle.py, docs: scratch/builder-port-design.md §4):
 * a built file may be saved only when it is byte for byte a file that the project's gate cleared.
 *   cleared(record, sha): the gate record (scripts/ship_gate.py's .gate.json, as the site publishes
 *     it) names this sha256 and every gate passed (n/a: a step that did not apply);
 *   verdict(release, record, got): {save, text, got, want}. RELEASE is the release's row of wishes.json
 *     (one build: its sha256 and its gate record's path). save is true only when the row lists a record,
 *     that record clears the row's sha256, and the build's own sha256 GOT is that sha256.
 * Shared by builder.html and the tests (node). */
"use strict";
(function (root) {
  const HEX = /^[0-9a-f]{64}$/;
  function cleared(record, sha) {
    if (!record || typeof record !== "object" || !HEX.test(String(sha)) || record.sha256 !== sha) return false;
    const g = record.gates;
    if (!g || typeof g !== "object" || !Object.keys(g).length) return false;
    // a feature step's KNOWN ISSUE clears too, as ship_gate's CLEARED TO FLASH (named in the record's known_issues)
    const known = Array.isArray(record.known_issues) ? record.known_issues
      : (record.known_issues && typeof record.known_issues === "object" ? Object.keys(record.known_issues) : []);
    return Object.entries(g).every(([k, v]) => /^(PASS|n\/a)/.test(String(v)) || (/^KNOWN/.test(String(v)) && known.includes(k)));
  }
  function verdict(release, record, got) {
    const want = release && release.sha256;
    const no = (text) => ({ save: false, text, got, want: want || null });
    if (!HEX.test(String(got))) return no("The build gave no file; do not flash.");
    if (!release || !release.gate || !record) return no("Not the cleared file; do not flash. No gate record clears this release yet.");
    if (!cleared(record, want)) return no("Not the cleared file; do not flash. The gate record does not clear this release's file.");
    if (got !== want) return no("Not the cleared file; do not flash. Your build differs from the cleared file.");
    return { save: true, text: "The cleared file, byte for byte.", got, want };
  }
  // LOCAL TEST SWITCH (2026-11-21): lets a TEST build that passed only the brick-risk steps through the same
  // verdict, for the User's first flash from the page. Honoured only when ALL hold: the page is on localhost
  // / 127.0.0.1 / [::1], the site is a --preview layout (scripts/make_site.sh writes localtest-preview.json,
  // the public build never does), the address has ?localtest=1, and the release's row carries local_test
  // naming the very sha256 the build must have (scripts/web_bundle.py --local-test SHA).
  const LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"];
  function localTestAllowed(env, release) {
    if (!env || !release || release.gate) return false;
    if (!LOCAL_HOSTS.includes(String(env.hostname))) return false;
    if (env.preview !== true) return false;
    if (!/(^|[?&])localtest=1(&|$)/.test(String(env.query || ""))) return false;
    const t = release.local_test;
    return !!(t && typeof t === "object" && HEX.test(String(t.brick_risk_sha256)) && t.brick_risk_sha256 === release.sha256);
  }
  function verdictLocal(release, record, got, env) {
    const v = verdict(release, record, got);
    if (v.save || !localTestAllowed(env, release) || got !== release.sha256) return v;
    return { save: true, test: true, got, want: release.sha256,
      text: "TEST BUILD, byte for byte the file that passed the brick-risk steps (not the release clearing)." };
  }
  const api = { cleared, verdict, verdictLocal, localTestAllowed };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WishesVerdict = api;
})(typeof self !== "undefined" ? self : this);
