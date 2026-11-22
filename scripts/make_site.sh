#!/usr/bin/env bash
# Lay out the Wishes site (the builder, the sample import, the help, the presets) exactly as GitHub Pages serves it.
#
# usage: scripts/make_site.sh OUTDIR [--preview]
#   The wishes-pages workflow runs it into _site. --preview is for looking at the pages locally
#   (python3 -m http.server --directory OUTDIR): a missing wishes/ bundle is allowed there (the builder
#   then says "No release published yet."), never in the workflow.
# The front page is the builder; the sample import is samples.html (the sources keep their names). The presets page
# lists presets/ (the repository's folder) with one zip of all, made reproducibly by scripts/presets_zip.py into OUTDIR/presets/.
set -eu
out="${1:?usage: scripts/make_site.sh OUTDIR [--preview]}"
preview="${2:-}"
here="$(cd "$(dirname "$0")/.." && pwd)"
web="$here/tools/web"

rm -rf "$out"
mkdir -p "$out/icons"
cp "$web/builder-worker.js" "$web/wishes-verdict.js" "$web/wishes-flash.js" "$web/wishes.css" "$out/"
# the About page is the front page (the User, 2026-11-22); index.html is written beside about.html below
cp "$web/builder.html" "$out/builder.html"
cp "$web/index.html" "$out/samples.html"
cp "$web/help.html" "$out/help.html"
cp "$web/presets.html" "$out/presets.html"
python3 "$here/scripts/presets_zip.py" "$out/presets" >/dev/null
cp "$web/manifest.webmanifest" "$out/"
# the About page: tools/web/about.md (its source) through scripts/make_about.py, with its icons (docs/img/icons) beside it
mkdir -p "$out/about-icons"
cp "$here/docs/img/icons/"*.png "$out/about-icons/"
python3 "$here/scripts/make_about.py" "$web/about.md" "$out/about.html" about-icons/
cp "$out/about.html" "$out/index.html"
cp "$web/icons/wishes-"*.png "$out/icons/"
cp "$here/LICENSE" "$here/THIRD-PARTY.md" "$out/"
if [ -d "$here/wishes" ]; then
  cp -R "$here/wishes" "$out/wishes"
elif [ "$preview" != "--preview" ]; then
  echo "make_site: no wishes/ bundle (scripts/web_bundle.py --wishes writes it)" >&2
  exit 1
fi
# the local test switch (docs: scratch/web-flash-howto.md): a bundle built with web_bundle.py --local-test is allowed in a
# --preview layout only, which also gets the marker the page asks for; the public layout refuses it here, and the
# Pages check (web_bundle.py --check-site) refuses its row too
if [ -d "$out/wishes" ] && grep -q '"local_test"' "$out/wishes/wishes.json" 2>/dev/null; then
  if [ "$preview" != "--preview" ]; then
    echo "make_site: wishes/ holds a --local-test build; it goes only into a --preview site" >&2
    rm -rf "$out"
    exit 1
  fi
  echo '{"preview": true}' > "$out/localtest-preview.json"
fi
echo "site laid out in $out"
