#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make the site's About page from README.md: python3 scripts/make_about.py README.md OUT/about.html [ICONS_URL_PREFIX]

README.md is the one source: it is the repository's front page and, through this script, the About page of the
Wishes site, in the shared style (tools/web/wishes.css on top of https://w0ts.github.io/site-style/common.css).
Only the Markdown README.md uses is handled: # ## headings, paragraphs, - lists (a line indented under an item
continues it), `code`, **bold**, *italic*, [text](url), and raw HTML blocks (the icon tables), whose
docs/img/icons/ paths are moved to ICONS_URL_PREFIX (default about-icons/), where make_site.sh copies the icons.
Anything else in the README fails loudly instead of being published half-formed."""
import html
import re
import sys
from pathlib import Path

REPO = "https://github.com/w0ts/dn2-wishes"
NAV = ('<nav class="site" aria-label="Wishes pages"><a href="./">builder</a><a href="samples.html">sample import</a>'
       '<a href="help.html">help</a><a href="presets.html">presets</a><a href="about.html" aria-current="page">about</a>'
       '<a href="%s">github.com/w0ts/dn2-wishes</a></nav>' % REPO)
# files the README links to that are not on the site: the repository's own page
SITE_FILES = {"LICENSE", "THIRD-PARTY.md"}


def inline(text: str) -> str:
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*|\[([^\]]+)\]\(([^)]+)\)", text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        code, bold, ital, label, url = m.groups()
        if code is not None:
            out.append("<code>%s</code>" % html.escape(code, quote=False))
        elif bold is not None:
            out.append("<b>%s</b>" % html.escape(bold, quote=False))
        elif ital is not None:
            out.append("<i>%s</i>" % html.escape(ital, quote=False))
        else:
            if not re.match(r"https?://", url) and url not in SITE_FILES:
                url = "%s/blob/main/%s" % (REPO, url)
            out.append('<a href="%s">%s</a>' % (html.escape(url), inline(label)))
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def convert(md: str, icons: str) -> tuple[str, str]:
    title, body = "About", []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("#"):
            m = re.match(r"(#+) (.*)", line)
            if not m or len(m.group(1)) > 2:
                raise SystemExit("make_about: unsupported heading: %r" % line)
            if len(m.group(1)) == 1:
                title = m.group(2)
                body.append('<header class="site"><div class="titlebar"><h1><a href="https://w0ts.github.io/">w0ts</a> / Wishes · about</h1></div>%s</header>' % "@@NAV@@")
            else:
                body.append("<h2>%s</h2>" % inline(m.group(2)))
            i += 1
        elif line.startswith("<"):
            block = []
            while i < len(lines) and lines[i].strip():
                block.append(lines[i])
                i += 1
            body.append("\n".join(block).replace("docs/img/icons/", icons))
        elif line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip() and (lines[i].startswith("- ") or lines[i].startswith("  ")):
                if lines[i].startswith("- "):
                    items.append(lines[i][2:])
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            body.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(t) for t in items))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "<", "- ")):
                para.append(lines[i].strip())
                i += 1
            body.append("<p>%s</p>" % inline(" ".join(para)))
    return title, "\n".join(body)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>w0ts / Wishes · about</title>
<link rel="icon" type="image/png" href="icons/wishes-192.png">
<link rel="apple-touch-icon" href="icons/wishes-180.png">
<link rel="stylesheet" href="https://w0ts.github.io/site-style/common.css">
<link rel="stylesheet" href="wishes.css">
<style>
/* the About page's own layout: the README, in a column */
main { max-width: 860px; }
h2 { margin: var(--sp-5) 0 var(--sp-2); }
table { margin: var(--sp-2) 0; }
td { padding: 6px 10px 6px 0; }
td:first-child { width: 64px; }
td img { display: block; image-rendering: pixelated; }
ul { padding-left: 20px; }
</style>
</head>
<body>
<main>
%(body)s
</main>
</body>
</html>
"""


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    icons = sys.argv[3] if len(sys.argv) == 4 else "about-icons/"
    _, body = convert(src.read_text(encoding="utf-8"), icons)
    dst.write_text(PAGE % {"body": body.replace("@@NAV@@", NAV)}, encoding="utf-8")


if __name__ == "__main__":
    main()
