#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make the site's About page from README.md: python3 scripts/make_about.py README.md OUT/about.html [ICONS_URL_PREFIX]

README.md is the one source: it is the repository's front page and, through this script, the About page of the
Wishes site, in the shared style (tools/web/wishes.css on top of https://w0ts.github.io/site-style/common.css).
Only the Markdown README.md uses is handled: # ## ### headings, paragraphs, - lists (a line indented under an item
continues it), `code`, **bold**, *italic*, [text](url), and raw HTML blocks (the icon tables), whose
docs/img/icons/ paths are moved to ICONS_URL_PREFIX (default about-icons/), where make_site.sh copies the icons.
The text before the first "## " is the page's lead; each "## " part is a box (<section>), as on the other pages.
Anything else in the README fails loudly instead of being published half-formed."""
import html
import re
import sys
from pathlib import Path

REPO = "https://github.com/w0ts/dn2-wishes"
NAV = ('<nav class="site" aria-label="Wishes pages"><a href="about.html" aria-current="page">about</a><a href="./">builder</a>'
       '<a href="samples.html">sample import</a><a href="presets.html">presets</a><a href="help.html">help</a>'
       '<a href="%s" aria-label="GitHub" title="GitHub"><svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg></a></nav>' % REPO)
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
    closer = ""            # the box open at this point: the lead under the title, then one <section> per "## " part
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("#"):
            m = re.match(r"(#+) (.*)", line)
            if not m or len(m.group(1)) > 3:
                raise SystemExit("make_about: unsupported heading: %r" % line)
            if len(m.group(1)) == 1:
                title = m.group(2)
                body.append('<header class="site"><div class="titlebar"><h1><a href="https://w0ts.github.io/">w0ts</a> / DN2-Wishes · about</h1></div>%s</header>' % "@@NAV@@")
                body.append('<div class="lead">')
                closer = "</div>"
            else:
                if len(m.group(1)) == 2:
                    body.append(closer + "<section>")
                    closer = "</section>"
                tag = "h%d" % len(m.group(1))
                body.append("<%s>%s</%s>" % (tag, inline(m.group(2)), tag))
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
    body.append(closer)
    return title, "\n".join(body)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>w0ts / DN2-Wishes · about</title>
<link rel="icon" type="image/png" href="icons/wishes-192.png">
<link rel="apple-touch-icon" href="icons/wishes-180.png">
<link rel="stylesheet" href="https://w0ts.github.io/site-style/common.css">
<link rel="stylesheet" href="wishes.css">
<style>
/* the About page's own layout: the README's intro as the lead, each "## " part a box (common.css does the column) */
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
