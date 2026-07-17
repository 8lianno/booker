#!/usr/bin/env python3
"""End-to-end unit tests for the booker pipeline.

Run from the repo root:  python3 -m unittest tests.test_pipeline -v

Everything runs in temp dirs — util.BOOKS_DIR is overridden in setUp and
restored in tearDown, so /Users/ali/booker/books/ is never touched.

structure.py and verify.py are developed concurrently; tests that need them
are guarded with skipIf so the suite degrades gracefully until they land.
"""

from __future__ import annotations

import importlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT / "scripts"), str(REPO_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import util  # noqa: E402
import stages  # noqa: E402
import resolve  # noqa: E402
import indexer  # noqa: E402
import make_fixture  # noqa: E402


def _try_import(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


structure = _try_import("structure")
verify = _try_import("verify")

REAL_BOOKS_TXT = Path("/Users/ali/books.txt")


# ---------------------------------------------------------------- base

class BookerTestCase(unittest.TestCase):
    """Temp sandbox: points util.BOOKS_DIR at <tmp>/books for the test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="booker-test-"))
        self._saved_books_dir = util.BOOKS_DIR
        util.BOOKS_DIR = self.tmp / "books"
        util.BOOKS_DIR.mkdir(parents=True)

    def tearDown(self):
        util.BOOKS_DIR = self._saved_books_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- shared helpers ----------------------------------------------------

    def build_fixture_book(self, slug, chapters=5):
        """Fixture EPUB → structure.build into books/<slug>; returns (bd, book)."""
        bd = util.book_dir(slug)
        (bd / "source").mkdir(parents=True)
        epub = bd / "source" / "book.epub"
        make_fixture.build_fixture_epub(epub, chapters=chapters)
        book = structure.build(bd, epub)
        return bd, book

    def write_meta(self, bd, slug):
        sha = util.sha256_text((bd / "book.json").read_text(encoding="utf-8"))
        util.save_json(bd / "meta.json", {
            "slug": slug,
            "title": "Fixture Book",
            "authors": ["Test Author"],
            "created": "2026-07-17T00:00:00+00:00",
            "book_json_sha256": sha,
        })
        return sha


# ---------------------------------------------------------------- structure

@unittest.skipIf(structure is None, "structure.py not available yet (integration)")
class TestStructure(BookerTestCase):

    def test_chapters_and_paragraph_counts_match_markers(self):
        bd, book = self.build_fixture_book("fixture-a")
        real = [c for c in book.get("chapters", []) if c.get("kind") == "chapter"]
        self.assertEqual(len(real), 5)
        self.assertGreater(book.get("stats", {}).get("words", 0), 10000)
        for c in book["chapters"]:
            path = bd / "text" / ("%s.md" % c["id"])
            self.assertTrue(path.exists(), "missing %s" % path)
            n_markers = len(re.findall(r"^\[¶\d+\]", path.read_text(encoding="utf-8"), re.M))
            self.assertEqual(n_markers, c.get("paragraphs"),
                             "¶ marker count mismatch in %s" % c["id"])

    def test_build_is_deterministic(self):
        bd1, _ = self.build_fixture_book("fixture-b1")
        bd2, _ = self.build_fixture_book("fixture-b2")
        names1 = sorted(p.name for p in (bd1 / "text").glob("*.md"))
        names2 = sorted(p.name for p in (bd2 / "text").glob("*.md"))
        self.assertEqual(names1, names2)
        for name in names1:
            self.assertEqual((bd1 / "text" / name).read_bytes(),
                             (bd2 / "text" / name).read_bytes(),
                             "text/%s differs between identical builds" % name)
        # book.json byte-identical modulo the differing dir/slug strings
        b1 = (bd1 / "book.json").read_text(encoding="utf-8") \
            .replace(str(bd1), "BD").replace("fixture-b1", "SLUG")
        b2 = (bd2 / "book.json").read_text(encoding="utf-8") \
            .replace(str(bd2), "BD").replace("fixture-b2", "SLUG")
        self.assertEqual(b1, b2, "book.json differs between identical builds")

    def test_sentinel_sentences_present_in_text(self):
        bd, book = self.build_fixture_book("fixture-c")
        blob = "\n".join((bd / "text" / ("%s.md" % c["id"])).read_text(encoding="utf-8")
                         for c in book["chapters"])
        for n in range(1, 6):
            self.assertIn("quick brown fox number %d" % n, blob)


# ---------------------------------------------------------------- anchors

ANCHOR_SAMPLE = (
    'One [ch03 ¶45]. Alias [ch03 p46]. Range [ch03 ¶45–48]. '
    'Ascii range [ch03 ¶45-48]. Multi [ch03 ¶45; ch07 ¶12]. '
    'Heading [ch04 ¶55 §"Bounded Rationality"]. '
    'Quote [ch01 ¶3 "verbatim fragment here"].'
)


@unittest.skipIf(verify is None, "verify.py not available yet (integration)")
class TestAnchors(BookerTestCase):

    def test_parse_anchors_grammar(self):
        parsed = verify.parse_anchors(ANCHOR_SAMPLE)
        # 7 anchors / 8 refs — accept either granularity
        self.assertGreaterEqual(len(parsed), 7)
        flat = repr(parsed)
        for token in ("ch01", "ch03", "ch04", "ch07", "45", "48", "12", "55",
                      "Bounded Rationality", "verbatim fragment here"):
            self.assertIn(token, flat, "parse_anchors lost %r" % token)

    # -- validation against a real fixture book ----------------------------

    def _validate(self, bd, text):
        """True iff every anchor in text resolves and no quote is unmatched."""
        book = verify.load_book(bd)
        anchors = verify.parse_anchors(text)
        if not anchors:
            return False
        for a in anchors:
            r = verify.validate_anchor(a, book)
            if not r.get("ok"):
                return False
            if a.get("quote") and r.get("quote_status") == "unmatched":
                return False
        return True

    def _fixture_with_sentinel(self):
        if structure is None:
            self.skipTest("structure.py not available yet (integration)")
        bd, book = self.build_fixture_book("fixture-anchors")
        chid = book["chapters"][0]["id"]
        text = (bd / "text" / ("%s.md" % chid)).read_text(encoding="utf-8")
        para = None
        current = None
        for line in text.splitlines():
            m = re.match(r"^\[¶(\d+)\]", line)
            if m:
                current = int(m.group(1))
            if current and "quick brown fox number 1" in line:
                para = current
                break
        self.assertIsNotNone(para, "sentinel not found in %s" % chid)
        return bd, book, chid, para

    def test_good_anchor_ok(self):
        bd, book, chid, para = self._fixture_with_sentinel()
        self.assertTrue(self._validate(bd, "Claim [%s ¶%d]." % (chid, para)))

    def test_out_of_range_paragraph_fails(self):
        bd, book, chid, para = self._fixture_with_sentinel()
        n = book["chapters"][0]["paragraphs"]
        self.assertFalse(self._validate(bd, "Claim [%s ¶%d]." % (chid, n + 500)))

    def test_unknown_chapter_fails(self):
        bd, book, chid, para = self._fixture_with_sentinel()
        self.assertFalse(self._validate(bd, "Claim [ch99 ¶1]."))

    def test_quote_exact_match(self):
        bd, book, chid, para = self._fixture_with_sentinel()
        self.assertTrue(self._validate(
            bd, 'Claim [%s ¶%d "quick brown fox number 1"].' % (chid, para)))

    def test_quote_fuzzy_within_one_paragraph(self):
        bd, book, chid, para = self._fixture_with_sentinel()
        self.assertTrue(self._validate(
            bd, 'Claim [%s ¶%d "quick brown fox number 1"].' % (chid, para + 1)))

    def test_quote_unmatched_fails(self):
        bd, book, chid, para = self._fixture_with_sentinel()
        self.assertFalse(self._validate(
            bd, 'Claim [%s ¶%d "purple elephants dance on the moon"].' % (chid, para)))


# ---------------------------------------------------------------- stage gates

class TestStageGates(BookerTestCase):

    def test_stage0_fails_on_fresh_dir(self):
        util.book_dir("empty-book").mkdir(parents=True)
        ok, msgs = stages.check_stage("empty-book", 0)
        self.assertFalse(ok)
        self.assertTrue(msgs)

    @unittest.skipIf(structure is None, "structure.py not available yet (integration)")
    def test_stage0_passes_after_build(self):
        bd, book = self.build_fixture_book("fixture-gate")
        self.write_meta(bd, "fixture-gate")
        ok, msgs = stages.check_stage("fixture-gate", 0)
        self.assertTrue(ok, "stage 0 gate failed: %s" % msgs)
        # the fixture must clear the 10k-word DRM/garbage gate
        self.assertGreater(book["stats"]["words"], 10000)

    # -- hand-written skeleton pass/fail cases ------------------------------

    def _minimal_book(self, slug):
        bd = util.book_dir(slug)
        (bd / "text").mkdir(parents=True)
        chapters = []
        for i in (1, 2, 3):
            chid = "ch%02d" % i
            chapters.append({"id": chid, "kind": "chapter",
                             "title": "Chapter %d" % i, "paragraphs": 2, "words": 4000})
            (bd / "text" / ("%s.md" % chid)).write_text(
                "[¶1] First paragraph.\n\n[¶2] Second paragraph.\n", encoding="utf-8")
        util.save_json(bd / "book.json", {
            "title": "Mini", "authors": ["A. Writer"], "chapters": chapters,
            "stats": {"chapters": 3, "words": 12000},
        })
        sha = self.write_meta(bd, slug)
        return bd, util.sha12(sha)

    def _skeleton(self, ids, sha12):
        return {"book_json_sha256_12": sha12,
                "chapters": [{"id": i, "analyze": True} for i in ids]}

    def test_stage1_pass(self):
        bd, sha12 = self._minimal_book("skel-ok")
        util.save_json(bd / "skeleton.json", self._skeleton(["ch01", "ch02", "ch03"], sha12))
        ok, msgs = stages.check_stage("skel-ok", 1)
        self.assertTrue(ok, "stage 1 gate failed: %s" % msgs)

    def test_stage1_missing_id_fails(self):
        bd, sha12 = self._minimal_book("skel-missing")
        util.save_json(bd / "skeleton.json", self._skeleton(["ch01", "ch02"], sha12))
        ok, msgs = stages.check_stage("skel-missing", 1)
        self.assertFalse(ok)
        self.assertTrue(any("missing" in m for m in msgs), msgs)

    def test_stage1_duplicate_id_fails(self):
        bd, sha12 = self._minimal_book("skel-dup")
        util.save_json(bd / "skeleton.json",
                       self._skeleton(["ch01", "ch02", "ch03", "ch03"], sha12))
        ok, msgs = stages.check_stage("skel-dup", 1)
        self.assertFalse(ok)
        self.assertTrue(any("duplicate" in m for m in msgs), msgs)

    def test_stage1_stale_sha_fails(self):
        bd, _ = self._minimal_book("skel-stale")
        util.save_json(bd / "skeleton.json",
                       self._skeleton(["ch01", "ch02", "ch03"], "deadbeefdead"))
        ok, msgs = stages.check_stage("skel-stale", 1)
        self.assertFalse(ok)
        self.assertTrue(any("stale" in m for m in msgs), msgs)


# ---------------------------------------------------------------- resolve

class TestResolve(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="booker-lib-"))
        for rel in (
            "Ann Author/Deep Work (12)/Deep Work - Ann Author.epub",
            "Bob Writer/Deep Learning (7)/Deep Learning - Bob Writer.epub",
            "Carol Poet/Shallow Water (3)/Shallow Water - Carol Poet.epub",
        ):
            path = self.tmp / rel
            path.parent.mkdir(parents=True)
            path.write_bytes(b"fake epub")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolve_ranks_exact_title_first(self):
        cands = resolve.resolve_title("deep work", self.tmp)
        self.assertTrue(cands)
        top = cands[0]
        self.assertEqual(top["title"], "Deep Work")
        self.assertEqual(top["author"], "Ann Author")
        self.assertEqual(top["calibre_id"], 12)
        self.assertTrue(top["path"].endswith(".epub"))
        scores = [c["score"] for c in cands]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(s > 0.35 for s in scores))

    def test_resolve_unrelated_query_returns_nothing(self):
        self.assertEqual(resolve.resolve_title("zebra xylophone quartz", self.tmp), [])

    def test_resolve_missing_library(self):
        self.assertEqual(resolve.resolve_title("deep work", self.tmp / "nope"), [])

    @unittest.skipUnless(REAL_BOOKS_TXT.exists(), "no real books.txt on this machine")
    def test_enrich_from_real_catalog(self):
        out = resolve.enrich_from_catalog("Self-Compassion", REAL_BOOKS_TXT)
        self.assertIsInstance(out, dict)
        if out:
            self.assertIn("calibre_id", out)
            self.assertIsInstance(out["calibre_id"], int)
            self.assertIn("pubdate", out)
            self.assertIn("tags", out)

    def test_enrich_never_raises(self):
        self.assertEqual(resolve.enrich_from_catalog("x", Path("/nonexistent/books.txt")), {})
        garbage = self.tmp / "garbage.txt"
        garbage.write_bytes(b"\x00\xff\x00 not a catalog \xfe")
        self.assertEqual(resolve.enrich_from_catalog("Deep Work", garbage), {})
        self.assertEqual(resolve.enrich_from_catalog("", REAL_BOOKS_TXT), {})


# ---------------------------------------------------------------- indexer

class TestIndexer(BookerTestCase):

    def _fake_completed_book(self):
        slug = "fake-book"
        bd = util.book_dir(slug)
        (bd / "text").mkdir(parents=True)
        dossier = "# Fake Book Dossier\n\n" + ("insight " * 400).strip() + "\n"
        (bd / "dossier.md").write_text(dossier, encoding="utf-8")
        (bd / "dossier.html").write_text("<html><body>ok</body></html>\n", encoding="utf-8")
        sha = util.sha256_text(dossier)
        chapters = []
        for i in (1, 2, 3):
            chid = "ch%02d" % i
            chapters.append({"id": chid, "kind": "chapter",
                             "title": "Chapter %d" % i, "paragraphs": 2, "words": 4000})
            (bd / "text" / ("%s.md" % chid)).write_text(
                "[¶1] One.\n\n[¶2] Two.\n", encoding="utf-8")
        util.save_json(bd / "book.json", {
            "title": "Fake Book", "authors": ["Jane Q. Tester"],
            "chapters": chapters, "stats": {"chapters": 3, "words": 12000},
        })
        self.write_meta(bd, slug)
        meta = util.load_json(bd / "meta.json")
        meta.update({"title": "Fake Book", "authors": ["Jane Q. Tester"],
                     "created": "2026-07-01T00:00:00+00:00"})
        util.save_json(bd / "meta.json", meta)
        util.save_json(bd / "verification.json", {
            "pass": True, "score": 93.5, "badge": "VERIFIED",
            "checked_at": "2026-07-02T00:00:00+00:00", "dossier_sha256": sha,
        })
        return slug, sha

    def test_build_index_catalog_fields(self):
        slug, sha = self._fake_completed_book()
        catalog = indexer.build_index(self.tmp)

        self.assertTrue((self.tmp / "catalog.json").exists())
        on_disk = util.load_json(self.tmp / "catalog.json")
        self.assertEqual(on_disk, catalog)
        self.assertIn("generated", catalog)
        self.assertEqual(len(catalog["books"]), 1)

        e = catalog["books"][0]
        self.assertEqual(e["slug"], slug)
        self.assertEqual(e["title"], "Fake Book")
        self.assertEqual(e["authors"], ["Jane Q. Tester"])
        self.assertIsInstance(e["stage"], int)
        self.assertTrue(0 <= e["stage"] <= 7)
        self.assertEqual(e["created"], "2026-07-01T00:00:00+00:00")
        self.assertEqual(e["completed"], "2026-07-02T00:00:00+00:00")
        self.assertGreater(e["dossier_words"], 100)
        self.assertEqual(e["dossier_sha256"], sha)
        self.assertEqual(e["verification"],
                         {"pass": True, "score": 93.5, "badge": "VERIFIED"})
        self.assertEqual(e["files"]["md"], "books/%s/dossier.md" % slug)
        self.assertEqual(e["files"]["html"], "books/%s/dossier.html" % slug)
        self.assertNotIn("pdf", e["files"])

        html_text = (self.tmp / "index.html").read_text(encoding="utf-8")
        self.assertIn("Booker Library", html_text)
        self.assertIn("Fake Book", html_text)
        self.assertNotIn('src="http', html_text)  # self-contained

        readme = (self.tmp / "README.md").read_text(encoding="utf-8")
        self.assertIn("<!-- BOOKER:INDEX -->", readme)
        self.assertIn("<!-- /BOOKER:INDEX -->", readme)
        self.assertIn("Fake Book", readme)

    def test_build_index_idempotent(self):
        self._fake_completed_book()
        cat1 = indexer.build_index(self.tmp)
        html1 = (self.tmp / "index.html").read_bytes()
        readme1 = (self.tmp / "README.md").read_bytes()
        cat2 = indexer.build_index(self.tmp)
        self.assertEqual(html1, (self.tmp / "index.html").read_bytes())
        self.assertEqual(readme1, (self.tmp / "README.md").read_bytes())
        cat1.pop("generated")
        cat2.pop("generated")
        self.assertEqual(cat1, cat2)

    def test_readme_markers_replaced_not_duplicated(self):
        self._fake_completed_book()
        readme = self.tmp / "README.md"
        readme.write_text("# My Repo\n\nintro prose\n\n"
                          "<!-- BOOKER:INDEX -->\nOLD CONTENT\n<!-- /BOOKER:INDEX -->\n"
                          "\ntrailing prose\n", encoding="utf-8")
        indexer.build_index(self.tmp)
        text = readme.read_text(encoding="utf-8")
        self.assertNotIn("OLD CONTENT", text)
        self.assertIn("intro prose", text)
        self.assertIn("trailing prose", text)
        self.assertIn("Fake Book", text)
        self.assertEqual(text.count("<!-- BOOKER:INDEX -->"), 1)

    def test_readme_markers_appended_when_missing(self):
        self._fake_completed_book()
        readme = self.tmp / "README.md"
        readme.write_text("# My Repo\n\nno markers here\n", encoding="utf-8")
        indexer.build_index(self.tmp)
        text = readme.read_text(encoding="utf-8")
        self.assertIn("no markers here", text)
        self.assertIn("<!-- BOOKER:INDEX -->", text)
        self.assertLess(text.index("no markers here"), text.index("<!-- BOOKER:INDEX -->"))

    def test_bak_dirs_skipped(self):
        self._fake_completed_book()
        bak = util.BOOKS_DIR / "fake-book.bak-20260101-000000"
        bak.mkdir()
        (bak / "meta.json").write_text("{}", encoding="utf-8")
        catalog = indexer.build_index(self.tmp)
        self.assertEqual([b["slug"] for b in catalog["books"]], ["fake-book"])


if __name__ == "__main__":
    unittest.main()
