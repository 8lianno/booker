#!/usr/bin/env python3
"""booker — EPUB → verified analytical dossier pipeline.

Agent-agnostic: all orchestration state lives on disk under books/<slug>/;
any coding-agent CLI resumes by running `status` and doing exactly the NEXT action.
See AGENTS.md for the quickstart and workflow/*.md for each step.

Python 3.9+ compatible, stdlib-only core. Optional deps (ebooklib, bs4,
weasyprint, pandoc) are probed at runtime with graceful fallbacks.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import util  # noqa: E402
import stages  # noqa: E402

DEFAULT_LIBRARY = os.environ.get("BOOKER_LIBRARY", "/Users/ali/Calibre Library")
BOOKS_TXT = os.environ.get("BOOKER_CATALOG", "/Users/ali/books.txt")


def _fail(msg):
    print("ERROR: %s" % msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- commands

def cmd_resolve(args):
    import resolve
    cands = resolve.resolve_title(args.title, Path(DEFAULT_LIBRARY))
    if args.json:
        print(json.dumps(cands[:5], indent=2, ensure_ascii=False))
        return
    if not cands:
        _fail("no EPUB matched %r under %s" % (args.title, DEFAULT_LIBRARY))
    for c in cands[:5]:
        print("%.3f  %s — %s\n       %s" % (c["score"], c["title"], c.get("author", "?"), c["path"]))


def cmd_new(args):
    import resolve
    import structure

    if args.epub:
        epub = Path(args.epub).expanduser()
        if not epub.exists():
            _fail("no such file: %s" % epub)
        title_guess = epub.stem
        resolution = {"method": "path", "query": str(epub)}
    elif args.title:
        cands = resolve.resolve_title(args.title, Path(DEFAULT_LIBRARY))
        if not cands:
            _fail("no EPUB matched %r under %s" % (args.title, DEFAULT_LIBRARY))
        if len(cands) > 1 and cands[0]["score"] - cands[1]["score"] < 0.05:
            lines = ["ambiguous title %r — candidates:" % args.title]
            for c in cands[:5]:
                lines.append("  %.3f  %s — %s" % (c["score"], c["title"], c.get("author", "?")))
            lines.append("re-run with a more specific --title or --epub <path>")
            _fail("\n".join(lines))
        epub = Path(cands[0]["path"])
        title_guess = cands[0]["title"]
        resolution = {"method": "title", "query": args.title, "match": cands[0]}
    else:
        _fail("give an EPUB path or --title \"…\"")

    slug = args.slug or util.slugify(title_guess)
    bd = util.book_dir(slug)
    if bd.exists():
        if not args.force:
            _fail("books/%s already exists (use --force to re-extract; anchors will be "
                  "renumbered and the old dir kept as .bak)" % slug)
        bak = bd.with_name("%s.bak-%s" % (slug, datetime.now().strftime("%Y%m%d-%H%M%S")))
        bd.rename(bak)
        print("moved old dir to %s" % bak)

    (bd / "source").mkdir(parents=True)
    dest = bd / "source" / "book.epub"
    shutil.copy2(epub, dest)

    print("extracting structure from %s …" % epub.name)
    book = structure.build(bd, dest)

    meta = {
        "slug": slug,
        "title": book.get("title"),
        "authors": book.get("authors", []),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_epub": str(epub),
        "resolution": resolution,
        "extraction": book.get("source", {}),
        "epub_sha256": util.sha256_file(dest),
        "book_json_sha256": util.sha256_text((bd / "book.json").read_text(encoding="utf-8")),
    }
    try:
        import resolve as _r
        meta["calibre"] = _r.enrich_from_catalog(book.get("title") or title_guess, Path(BOOKS_TXT))
    except Exception:
        meta["calibre"] = {}
    util.save_json(bd / "meta.json", meta)

    ok, msgs = stages.check_stage(slug, 0)
    if not ok:
        print("stage 0 gate FAILED:")
        for m in msgs:
            print("  - %s" % m)
        sys.exit(1)
    print("created books/%s  (%d chapters, %d words, structure=%s)"
          % (slug, book["stats"]["chapters"], book["stats"]["words"],
             book.get("source", {}).get("structure", "?")))
    _print_status(slug)


def _print_status(slug):
    st = stages.stage_status(slug)
    for s in st["stages"]:
        mark = "✓" if s["complete"] else ("→" if s["n"] == st["current"] else "·")
        print("%s stage %d (%s): %s" % (mark, s["n"], s["name"], s["detail"]))
    print("NEXT: %s" % st["next"])


def cmd_status(args):
    st = stages.stage_status(args.slug)
    if args.json:
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return
    if st["current"] == -1:
        _fail(st["next"])
    _print_status(args.slug)


def cmd_list(args):
    books = sorted(p.name for p in util.BOOKS_DIR.iterdir()
                   if p.is_dir() and not p.name.startswith(".") and ".bak-" not in p.name) \
        if util.BOOKS_DIR.exists() else []
    if not books:
        print("no books yet — python3 booker.py new --title \"…\"")
        return
    for slug in books:
        st = stages.stage_status(slug)
        stage_txt = "complete" if st["current"] == 7 else "stage %d (%s)" % (
            st["current"], stages.STAGE_NAMES[st["current"]])
        print("%-40s %s" % (slug, stage_txt))


def cmd_check(args):
    if args.stage is None:
        st = stages.stage_status(args.slug)
        _print_status(args.slug)
        sys.exit(0 if st["current"] == 7 else 1)
    ok, msgs = stages.check_stage(args.slug, args.stage, packet=args.packet)
    label = "stage %d" % args.stage + (" packet %s" % args.packet if args.packet else "")
    if ok:
        print("OK: %s gate passed" % label)
        sys.exit(0)
    print("FAIL: %s" % label)
    for m in msgs:
        print("  - %s" % m)
    sys.exit(1)


def cmd_chapter(args):
    path = util.book_dir(args.slug) / "text" / ("%s.md" % args.chid)
    if not path.exists():
        _fail("no such chapter text: %s" % path)
    sys.stdout.write(path.read_text(encoding="utf-8"))


def cmd_verify(args):
    import verify
    bd = util.book_dir(args.slug)
    if not (bd / "dossier.md").exists():
        _fail("no dossier.md yet — finish stage 3 first")
    results = verify.verify_dossier(bd)
    print("verification: %s  score=%.1f  badge=%s"
          % ("PASS" if results["pass"] else "FAIL", results.get("score", 0.0),
             results.get("badge", "?")))
    for f in results.get("failures", []):
        print("  - %s" % f)
    if results.get("repair_list"):
        print("repair list (%d items) written to verification.json" % len(results["repair_list"]))
    sys.exit(0 if results["pass"] else 1)


def cmd_render(args):
    import render_book
    bd = util.book_dir(args.slug)
    md = bd / "dossier.md"
    if not md.exists():
        _fail("no dossier.md for %s" % args.slug)
    meta = util.load_json(bd / "meta.json")
    status = render_book.render(bd, meta.get("title") or args.slug,
                                authors=meta.get("authors") or [],
                                skip_pdf=args.skip_pdf, pdf_timeout=args.pdf_timeout)
    for key in ("html", "pdf", "epub"):
        print("%s_status=%s" % (key, status[key]))
    if not (bd / "dossier.html").exists():
        _fail("renderer failed: %s" % status["html"])
    meta["render"] = {
        "dossier_sha256": util.sha256_text(md.read_text(encoding="utf-8")),
        "rendered": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "html": (bd / "dossier.html").exists(),
        "pdf": (bd / "dossier.pdf").exists(),
        "epub": (bd / "dossier.epub").exists(),
        "status": status,
    }
    util.save_json(bd / "meta.json", meta)
    made = ["dossier.html"]
    if meta["render"]["pdf"]:
        made.append("dossier.pdf")
    if meta["render"]["epub"]:
        made.append("dossier.epub")
    print("rendered: %s" % " + ".join(made))


def cmd_index(args):
    import indexer
    catalog = indexer.build_index(REPO_ROOT)
    print("indexed %d book(s) → catalog.json, index.html, README.md table"
          % len(catalog.get("books", [])))


def cmd_nlm_setup(args):
    import notebooklm_adapter
    bd = util.book_dir(args.slug)
    meta = util.load_json(bd / "meta.json") if (bd / "meta.json").exists() else {}
    title = meta.get("title") or args.slug
    text_dir = bd / "text"
    if not text_dir.exists():
        _fail("No text/ directory found for %s. Run 'booker new' first." % args.slug)
    result = notebooklm_adapter.setup_book_notebook(args.slug, title, text_dir)
    meta["notebooklm"] = {
        "notebook_id": result["notebook_id"],
        "url": result["url"],
        "sources_count": result["sources_count"],
    }
    util.save_json(bd / "meta.json", meta)
    print("NotebookLM setup complete! Notebook URL: %s" % result["url"])


def cmd_nlm_synthesize(args):
    import narrative_synthesizer
    bd = util.book_dir(args.slug)
    meta = util.load_json(bd / "meta.json") if (bd / "meta.json").exists() else {}
    nb_id = meta.get("notebooklm", {}).get("notebook_id")
    out_file = narrative_synthesizer.synthesize_dossier(args.slug, genre=args.genre, notebook_id=nb_id)
    print("Dossier synthesized: %s" % out_file)


def cmd_nlm_audio(args):
    import notebooklm_adapter
    bd = util.book_dir(args.slug)
    meta = util.load_json(bd / "meta.json") if (bd / "meta.json").exists() else {}
    nb_id = meta.get("notebooklm", {}).get("notebook_id")
    if not nb_id:
        _fail("NotebookLM not set up for %s. Run 'booker nlm-setup' first." % args.slug)
    res = notebooklm_adapter.create_audio_podcast(nb_id)
    print("Audio Podcast Generation Result: %s" % res)


def main(argv=None):
    p = argparse.ArgumentParser(prog="booker", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="stage 0: resolve, extract, structure a book")
    s.add_argument("epub", nargs="?", help="path to an .epub file")
    s.add_argument("--title", help="fuzzy title lookup in the Calibre library")
    s.add_argument("--slug", help="override the generated slug")
    s.add_argument("--force", action="store_true", help="re-extract over an existing slug")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("nlm-setup", help="create NotebookLM notebook & upload chapter sources")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_nlm_setup)

    s = sub.add_parser("nlm-synthesize", help="dual-engine narrative dossier synthesis")
    s.add_argument("slug")
    s.add_argument("--genre", choices=["fiction", "non-fiction"], help="override detected genre")
    s.set_defaults(fn=cmd_nlm_synthesize)

    s = sub.add_parser("nlm-audio", help="generate NotebookLM Deep Dive Audio Podcast")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_nlm_audio)

    s = sub.add_parser("resolve", help="preview title→EPUB resolution (top 5)")
    s.add_argument("--title", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_resolve)

    s = sub.add_parser("status", help="stage table + NEXT action")
    s.add_argument("slug")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("list", help="all books and their current stage")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("check", help="run deterministic gate(s); exit 0/1")
    s.add_argument("slug")
    s.add_argument("--stage", type=int, choices=range(7))
    s.add_argument("--packet", help="check a single packet (with --stage 2)")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("chapter", help="print text/<chid>.md for one chapter")
    s.add_argument("slug")
    s.add_argument("chid")
    s.set_defaults(fn=cmd_chapter)

    s = sub.add_parser("verify", help="stage 4a: deterministic verification → verification.json")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("render", help="stage 5: dossier.md → HTML (+PDF)")
    s.add_argument("slug")
    s.add_argument("--skip-pdf", action="store_true")
    s.add_argument("--pdf-timeout", type=int, default=300)
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("index", help="stage 6: regenerate catalog.json + index.html + README table")
    s.set_defaults(fn=cmd_index)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

