#!/usr/bin/env python3
"""Booker-native dossier renderer: HTML + PDF + EPUB with reading-first typography.

The canonical dossier.md keeps full inline anchors ([ch03 ¶45 "quote"]) because
verification depends on them. Rendered outputs convert every anchor into an
unobtrusive superscript marker whose full reference lives in a tooltip (HTML) or
stays tiny (PDF/EPUB), so the text reads clean. The HTML adds a references
toggle: markers · full · hidden.

Requires pandoc for the good path (present on this machine); falls back to the
vendored render_dossier.py behavior for HTML-only when pandoc is missing.
Python 3.9+, stdlib only.
"""

from __future__ import annotations

import html as html_mod
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# anchor bracket whose content starts like a chapter ref; never a markdown link
ANCHOR_RE = re.compile(
    r"\[((?:ch|fm|bm)\d{2}\s*(?:¶|p)\s*\d+[^\]]*)\](?!\()")
COVERS_RE = re.compile(r"^_Covers \[([^\]]+)\]_\s*$")

CSS = """
:root { --ink: #1c1c1c; --muted: #8a8a8a; --line: #e3ddd3; --accent: #7a5c2e; }
html { scroll-behavior: smooth; }
body {
  max-width: 760px; margin: 56px auto; padding: 0 32px;
  color: var(--ink);
  font-family: Charter, "Iowan Old Style", Georgia, "Times New Roman", serif;
  font-size: 17px; line-height: 1.7;
  text-align: justify; hyphens: auto; -webkit-hyphens: auto;
  text-rendering: optimizeLegibility; font-kerning: normal;
}
h1, h2, h3, h4 {
  font-family: "Avenir Next", Avenir, "Segoe UI", -apple-system, sans-serif;
  line-height: 1.28; text-align: left; hyphens: none; letter-spacing: -0.01em;
}
header#title-block-header { margin-bottom: 2.2rem; }
h1.title { font-size: 1.9rem; border-bottom: 3px double var(--accent); padding-bottom: .4rem; }
h1 { font-size: 1.75rem; margin-top: 2.2em; }
h2 { font-size: 1.4rem; margin-top: 2.1em; border-bottom: 1px solid var(--line); padding-bottom: .3rem; }
h3 { font-size: 1.12rem; margin-top: 1.7em; color: #2e2a24; }
p { margin: 0.75em 0; }
strong { color: #000; }
blockquote { border-left: 3px solid var(--accent); margin-left: 0; padding-left: 1rem; color: #504a41; font-style: italic; }
code { background: #f5f2ec; padding: .08rem .3rem; border-radius: 4px; font-size: .82em; }
pre { background: #f7f5f0; border: 1px solid var(--line); border-radius: 8px; padding: .9rem 1rem; overflow-x: auto; line-height: 1.45; text-align: left; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1.2rem 0; font-size: .86em; line-height: 1.45; text-align: left; hyphens: none; }
th, td { border: 1px solid var(--line); padding: .45rem .6rem; vertical-align: top; }
th { background: #f4f0e8; font-family: "Avenir Next", Avenir, sans-serif; font-size: .92em; }
tr:nth-child(even) td { background: #fbfaf7; }
hr { border: none; border-top: 1px solid var(--line); margin: 2.5rem auto; width: 40%; }
nav#TOC {
  background: #faf8f3; border: 1px solid var(--line); border-radius: 10px;
  padding: 1rem 1.6rem; margin: 2rem 0 3rem; font-size: .9em; text-align: left;
  font-family: "Avenir Next", Avenir, sans-serif; column-count: 2; column-gap: 2rem;
}
nav#TOC::before { content: "Contents"; font-weight: 600; display: block; margin-bottom: .5rem; }
nav#TOC ul { margin: 0; padding-left: 1.1rem; list-style: none; }
nav#TOC a { color: var(--ink); text-decoration: none; }
nav#TOC a:hover { color: var(--accent); }
a { color: var(--accent); }

/* --- source references ------------------------------------------------ */
sup.ref {
  color: var(--muted); font-size: .62em; line-height: 0; cursor: help;
  padding: 0 .06em; user-select: none;
}
sup.ref:hover { color: var(--accent); }
body[data-refs="hidden"] sup.ref { display: none; }
body[data-refs="full"] sup.ref::after {
  content: " " attr(title);
  font-size: .85em; color: var(--muted); font-family: ui-monospace, Menlo, monospace;
  letter-spacing: -0.02em;
}
div.covers {
  color: var(--muted); font-size: .78em; margin: -0.4em 0 1em;
  font-family: "Avenir Next", Avenir, sans-serif; text-align: left;
}
#reftoggle {
  position: fixed; top: 14px; right: 14px; z-index: 10;
  font: 12px "Avenir Next", Avenir, sans-serif; color: #5c5648;
  background: #faf8f3; border: 1px solid var(--line); border-radius: 999px;
  padding: .35rem .8rem; cursor: pointer;
}
#reftoggle:hover { border-color: var(--accent); color: var(--accent); }
details { margin: .6em 0; }
details summary { cursor: pointer; color: var(--accent); }

/* --- print / PDF ------------------------------------------------------- */
@page {
  margin: 20mm 17mm;
  @bottom-center { content: counter(page); font-size: 9px; color: #999; }
}
@media print {
  body { max-width: none; margin: 0; padding: 0; font-size: 10.4pt; }
  #reftoggle { display: none; }
  sup.ref { font-size: .58em; color: #b0a89a; }
  nav#TOC { column-count: 2; }
  h1, h2 { page-break-after: avoid; break-after: avoid-page; }
  h2 { page-break-before: page; break-before: page; }
  nav#TOC + * , header#title-block-header + * { page-break-before: avoid; }
  table, blockquote, pre { page-break-inside: avoid; }
}
"""

JS = """
(function () {
  var modes = ["markers", "full", "hidden"];
  var labels = {markers: "refs: markers", full: "refs: full", hidden: "refs: hidden"};
  var body = document.body;
  var btn = document.createElement("button");
  btn.id = "reftoggle";
  var mode = localStorage.getItem("booker-refs") || "markers";
  function apply(m) { body.setAttribute("data-refs", m); btn.textContent = labels[m]; }
  apply(mode);
  btn.addEventListener("click", function () {
    mode = modes[(modes.indexOf(mode) + 1) % modes.length];
    localStorage.setItem("booker-refs", mode);
    apply(mode);
  });
  body.appendChild(btn);
})();
"""

EPUB_CSS = """
body { text-align: justify; hyphens: auto; -webkit-hyphens: auto; line-height: 1.6; }
h1, h2, h3 { font-family: sans-serif; line-height: 1.3; text-align: left; hyphens: none; }
h1 { font-size: 1.5em; border-bottom: 2px solid #7a5c2e; padding-bottom: 0.2em; }
h2 { font-size: 1.2em; }
p { margin: 0.4em 0; text-indent: 0; }
blockquote { border-left: 3px solid #7a5c2e; margin-left: 0; padding-left: 0.8em; font-style: italic; }
sup.ref { font-size: 0.6em; color: #999; }
div.covers { color: #999; font-size: 0.75em; font-family: sans-serif; }
table { border-collapse: collapse; width: 100%; font-size: 0.8em; text-align: left; }
th, td { border: 1px solid #ccc; padding: 0.3em 0.4em; vertical-align: top; }
th { background: #f0ece4; }
code { font-size: 0.85em; }
"""


def _run(cmd, timeout=None):
    try:
        return subprocess.run(cmd, check=False, text=True, capture_output=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "",
                                           exc.stderr or "timed out")


def _ref_sup(content):
    tip = html_mod.escape(re.sub(r"\s+", " ", content).strip(), quote=True)
    return '<sup class="ref" title="%s">°</sup>' % tip


def transform_markdown(text):
    """Replace inline anchors with superscript reference markers.

    Fenced code blocks are left untouched (the §0/§16 YAML blocks). Markdown
    links, [ext: …] citations and plain bracketed text never match the anchor
    pattern, so §13 links survive as links.
    """
    out = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        m = COVERS_RE.match(line)
        if m:
            out.append('<div class="covers">%s</div>'
                       % html_mod.escape(m.group(1).replace("¶", "¶ ")))
            continue
        out.append(ANCHOR_RE.sub(lambda mm: _ref_sup(mm.group(1)), line))
    return "\n".join(out) + "\n"


def _pandoc_supports(flag):
    probe = _run(["pandoc", "--help"])
    return flag in (probe.stdout or "")


def render(book_dir, title, authors=None, skip_pdf=False, pdf_timeout=300):
    """Render book_dir/dossier.md → dossier.html (+ .pdf, .epub).

    Returns {"html": str, "pdf": str, "epub": str} status strings.
    """
    book_dir = Path(book_dir)
    md_path = book_dir / "dossier.md"
    html_path = book_dir / "dossier.html"
    pdf_path = book_dir / "dossier.pdf"
    epub_path = book_dir / "dossier.epub"
    authors = authors or []

    source = md_path.read_text(encoding="utf-8")
    transformed = transform_markdown(source)
    status = {"html": "html_failed", "pdf": "pdf_skipped", "epub": "epub_skipped"}

    have_pandoc = bool(shutil.which("pandoc"))
    with tempfile.TemporaryDirectory(prefix="booker-render-") as tmp:
        tmp = Path(tmp)
        tmd = tmp / "dossier.md"
        tmd.write_text(transformed, encoding="utf-8")

        # ---- HTML ----------------------------------------------------------
        if have_pandoc:
            r = _run(["pandoc", str(tmd), "--standalone", "--toc", "--toc-depth=2",
                      "--from", "markdown+smart", "--to", "html5",
                      "--metadata", "title=%s" % title,
                      "--metadata", "lang=en",
                      "-o", str(html_path)])
            if r.returncode == 0 and html_path.exists():
                doc = html_path.read_text(encoding="utf-8")
                inject = "<style>%s</style>" % CSS
                doc = doc.replace("</head>", inject + "\n</head>", 1)
                doc = doc.replace("</body>", "<script>%s</script>\n</body>" % JS, 1)
                html_path.write_text(doc, encoding="utf-8")
                status["html"] = "html_ok_pandoc"
        if status["html"] != "html_ok_pandoc":
            import render_dossier
            body = render_dossier.fallback_markdown_to_html(transformed)
            html_path.write_text(
                "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
                "<title>%s</title><style>%s</style></head><body>%s"
                "<script>%s</script></body></html>\n"
                % (html_mod.escape(title), CSS, body, JS), encoding="utf-8")
            status["html"] = "html_ok_fallback"

        # ---- PDF -----------------------------------------------------------
        if not skip_pdf:
            if shutil.which("weasyprint"):
                r = _run(["weasyprint", str(html_path), str(pdf_path)],
                         timeout=pdf_timeout)
                if r.returncode == 0 and pdf_path.exists():
                    status["pdf"] = "pdf_ok_weasyprint"
                elif r.returncode == 124:
                    status["pdf"] = "pdf_failed_weasyprint_timeout"
                else:
                    status["pdf"] = "pdf_failed_weasyprint"
            elif have_pandoc:
                r = _run(["pandoc", str(tmd), "-o", str(pdf_path)], timeout=pdf_timeout)
                status["pdf"] = ("pdf_ok_pandoc" if r.returncode == 0 and pdf_path.exists()
                                 else "pdf_failed_pandoc_or_pdf_engine")
            else:
                status["pdf"] = "pdf_skipped_no_weasyprint_or_pandoc"

        # ---- EPUB ----------------------------------------------------------
        if have_pandoc:
            ecss = tmp / "epub.css"
            ecss.write_text(EPUB_CSS, encoding="utf-8")
            split_flag = ("--split-level=1" if _pandoc_supports("--split-level")
                          else "--epub-chapter-level=1")
            cmd = ["pandoc", str(tmd), "--from", "markdown+smart",
                   "--metadata", "title=%s — Dossier" % title,
                   "--metadata", "lang=en"]
            for a in authors:
                cmd += ["--metadata", "author=%s" % a]
            cmd += ["--toc", "--toc-depth=1",
                    "--shift-heading-level-by=-1", split_flag,
                    "--css", str(ecss), "-o", str(epub_path)]
            r = _run(cmd, timeout=pdf_timeout)
            status["epub"] = ("epub_ok_pandoc" if r.returncode == 0 and epub_path.exists()
                              else "epub_failed_pandoc")
        else:
            status["epub"] = "epub_skipped_no_pandoc"

    return status
