#!/usr/bin/env python3
"""Library index for booker (stage 6).

build_index(repo_root) scans repo_root/books/*/ (skipping *.bak-*) and writes:

    1. repo_root/catalog.json — {"generated": iso-utc, "books": [entries]}
    2. repo_root/index.html   — self-contained library page (embedded CSS)
    3. repo_root/README.md    — table between <!-- BOOKER:INDEX --> markers

Idempotent: re-running without changes reproduces index.html and README.md
byte-identically; only catalog.json's "generated" timestamp moves.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path

import stages
import util

INDEX_BEGIN = "<!-- BOOKER:INDEX -->"
INDEX_END = "<!-- /BOOKER:INDEX -->"

# Look kept consistent with scripts/render_dossier.py CSS.
CSS = """
body {
  max-width: 960px;
  margin: 48px auto;
  padding: 0 28px;
  color: #171717;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 16px;
  line-height: 1.62;
}
h1 {
  font-size: 2rem;
  line-height: 1.25;
  border-bottom: 2px solid #111;
  padding-bottom: 0.35rem;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1rem 0;
}
th, td {
  border: 1px solid #d7d7d7;
  padding: 0.45rem 0.55rem;
  vertical-align: top;
  text-align: left;
}
th { background: #f4f4f4; }
a { color: #0b62c4; }
tr.inprogress td { color: #9a9a9a; }
tr.inprogress a { color: #9a9a9a; }
p.empty { color: #666; }
"""


# ---------------------------------------------------------------- entries

def _stage_fallback(bd):
    """Best-effort stage estimate when the real gates cannot run (e.g. a
    sibling module is missing). Coarse by design."""
    stage = 0
    if (bd / "meta.json").exists() and (bd / "book.json").exists():
        stage = 1
    if (bd / "skeleton.json").exists():
        stage = 2
    if (bd / "dossier.md").exists():
        stage = 4
    try:
        if util.load_json(bd / "verification.json").get("pass"):
            stage = 5
            if (bd / "dossier.html").exists():
                stage = 6
    except Exception:
        pass
    return stage


def _book_stage(bd, slug):
    try:
        st = stages.stage_status(slug)
        if st.get("current", -1) >= 0:
            return st["current"]
    except Exception:
        pass
    return _stage_fallback(bd)


def _load_or_empty(path):
    try:
        return util.load_json(path)
    except Exception:
        return {}


def _book_entry(bd):
    slug = bd.name
    meta = _load_or_empty(bd / "meta.json")
    book = _load_or_empty(bd / "book.json")

    verification = None
    completed = None
    vraw = _load_or_empty(bd / "verification.json") if (bd / "verification.json").exists() else {}
    if vraw:
        verification = {
            "pass": bool(vraw.get("pass")),
            "score": vraw.get("score"),
            "badge": vraw.get("badge"),
        }
        if vraw.get("pass"):
            completed = vraw.get("checked_at")

    dossier_words = None
    dossier_sha256 = None
    md = bd / "dossier.md"
    if md.exists():
        text = md.read_text(encoding="utf-8")
        dossier_words = util.word_count(text)
        dossier_sha256 = util.sha256_text(text)

    files = {}
    for key, name in (("md", "dossier.md"), ("html", "dossier.html"),
                      ("pdf", "dossier.pdf"), ("epub", "dossier.epub"),
                      ("slides", "presentation.html")):
        if (bd / name).exists():
            files[key] = "books/%s/%s" % (slug, name)

    return {
        "slug": slug,
        "title": meta.get("title") or book.get("title") or slug,
        "authors": meta.get("authors") or book.get("authors") or [],
        "stage": _book_stage(bd, slug),
        "created": meta.get("created"),
        "completed": completed,
        "dossier_words": dossier_words,
        "verification": verification,
        "dossier_sha256": dossier_sha256,
        "files": files,
    }


# ---------------------------------------------------------------- rendering

def _fmt_date(entry):
    date = entry.get("completed") or entry.get("created") or ""
    return date[:10] if date else "–"


def _fmt_words(entry):
    words = entry.get("dossier_words")
    return "{:,}".format(words) if words else "–"


def _fmt_score(entry):
    if entry["stage"] < 7:
        return "stage %d (%s)" % (entry["stage"],
                                  stages.STAGE_NAMES.get(entry["stage"], "?"))
    v = entry.get("verification") or {}
    score, badge = v.get("score"), v.get("badge")
    if isinstance(score, (int, float)):
        return "%.1f · %s" % (score, badge or "?")
    return badge or "–"


def _html_row(entry):
    links = " · ".join('<a href="%s">%s</a>' % (html.escape(rel, quote=True), key)
                       for key, rel in sorted(entry["files"].items()))
    cls = "" if entry["stage"] == 7 else ' class="inprogress"'
    cells = (
        html.escape(entry["title"] or ""),
        html.escape(", ".join(entry["authors"])),
        html.escape(_fmt_date(entry)),
        html.escape(_fmt_words(entry)),
        html.escape(_fmt_score(entry)),
        links or "–",
    )
    return "<tr%s><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" \
        % ((cls,) + cells)


def _render_html(entries):
    rows = "\n".join(_html_row(e) for e in entries)
    body = ('<table>\n<thead><tr><th>Title</th><th>Author</th><th>Date</th>'
            '<th>Words</th><th>Score / Badge</th><th>Links</th></tr></thead>\n'
            '<tbody>\n%s\n</tbody>\n</table>' % rows) if entries \
        else '<p class="empty">No books yet — python3 booker.py new --title "…"</p>'
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            "<title>Booker Library</title><style>%s</style></head>\n"
            "<body>\n<h1>Booker Library</h1>\n%s\n</body></html>\n" % (CSS, body))


def _md_cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _render_md_table(entries):
    lines = ["| Title | Author | Date | Words | Score / Badge | Links |",
             "|---|---|---|---|---|---|"]
    for e in entries:
        links = " · ".join("[%s](%s)" % (key, rel) for key, rel in sorted(e["files"].items()))
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            _md_cell(e["title"]), _md_cell(", ".join(e["authors"])),
            _fmt_date(e), _fmt_words(e), _md_cell(_fmt_score(e)), links or "–"))
    if not entries:
        lines.append("| _no books yet_ |  |  |  |  |  |")
    return "\n".join(lines)


def _update_readme(readme_path, table_md):
    block = "%s\n%s\n%s" % (INDEX_BEGIN, table_md, INDEX_END)
    if not readme_path.exists():
        readme_path.write_text("# Booker Library\n\n%s\n" % block, encoding="utf-8")
        return
    text = readme_path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(INDEX_BEGIN) + r".*?" + re.escape(INDEX_END), re.S)
    if pattern.search(text):
        new = pattern.sub(lambda _m: block, text, count=1)
    else:
        new = text.rstrip("\n") + "\n\n%s\n" % block
    if new != text:
        readme_path.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------- build

def build_index(repo_root):
    """Scan repo_root/books/*/ and (re)write catalog.json, index.html and the
    README.md index table. Returns the catalog dict."""
    repo_root = Path(repo_root)
    books_dir = repo_root / "books"

    def scan():
        found = []
        if books_dir.exists():
            for bd in sorted(books_dir.iterdir()):
                if not bd.is_dir() or bd.name.startswith(".") or ".bak-" in bd.name:
                    continue
                found.append(_book_entry(bd))
        found.sort(key=lambda e: ((e["title"] or "").casefold(), e["slug"]))
        return found

    # Two passes: the stage-6 gate reads catalog.json, so a book indexed for the
    # first time would otherwise show as incomplete in its own fresh entry.
    entries = scan()
    util.save_json(repo_root / "catalog.json",
                   {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "books": entries})
    entries = scan()

    catalog = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "books": entries,
    }
    util.save_json(repo_root / "catalog.json", catalog)
    (repo_root / "index.html").write_text(_render_html(entries), encoding="utf-8")
    _update_readme(repo_root / "README.md", _render_md_table(entries))
    return catalog
