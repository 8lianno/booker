#!/usr/bin/env python3
"""Structured EPUB extraction for stage 0 (booker.py `new`).

Public contract:

    build(book_dir, epub_path) -> dict     # the book.json dict
    raises StructureError(str) on failure

Side effects: writes <book_dir>/book.json and <book_dir>/text/<chid>.md for
every chapter entry (one [¶n] line per paragraph — stages.py counts them).

Two extraction methods share one structural pipeline:
  * primary  — ebooklib + bs4 importable: paragraphs via BeautifulSoup
    (source.method = "ebooklib")
  * fallback — pure stdlib: html.parser block collector
    (source.method = "stdlib")
Container/OPF/toc plumbing is stdlib zipfile + xml.etree in BOTH paths, so
the methods differ only in HTML→paragraph fidelity. Set BOOKER_FORCE_STDLIB=1
to force the fallback (used by tests).

Determinism: same epub in → byte-identical book.json + text files.
"""

from __future__ import annotations

import bisect
import html.parser
import os
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote

import util

OVERSIZE_WORDS = 8000        # chapters[].oversize = words > this
PART_HEAD_MAX_WORDS = 50     # bare part pages below this merge into "part" labels

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li")
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

DOC_MEDIA = ("application/xhtml+xml", "text/html", "application/html+xml")

# Seed classification only — agents refine kinds in stage 1.
FRONT_RE = re.compile(
    r"(?i)\b(cover|title\s*page|half[- ]?title|copyright|contents|"
    r"dedication|praise|acknowledg\w*|about\s+the\s+author|also\s+by|epigraph)\b")
BACK_RE = re.compile(
    r"(?i)\b(notes?|endnotes?|index|bibliograph\w*|glossar\w*|appendi\w*|"
    r"references|works\s+cited|further\s+reading)\b")


class StructureError(Exception):
    """Raised when an EPUB cannot be turned into a book.json structure."""


# ---------------------------------------------------------------- small helpers

def _probe_primary():
    """True when the ebooklib+bs4 primary path is importable and not disabled."""
    if os.environ.get("BOOKER_FORCE_STDLIB"):
        return False
    try:
        import ebooklib          # noqa: F401
        from ebooklib import epub  # noqa: F401
        import bs4               # noqa: F401
    except ImportError:
        return False
    return True


def _norm_ws(text):
    """Collapse all internal whitespace (incl. newlines, nbsp) to single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


def _local(tag):
    """Local (namespace-stripped, lowercased) name of an ElementTree tag."""
    return str(tag).rsplit("}", 1)[-1].lower()


def _attr(el, name):
    """Attribute lookup ignoring namespace prefixes."""
    for k, v in el.attrib.items():
        if _local(k) == name:
            return v
    return None


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _resolve(base, href):
    """href (relative to base dir inside the zip) → normalized zip path, no fragment."""
    if not href:
        return None
    href = unquote(href.split("#", 1)[0].strip())
    if not href:
        return None
    path = posixpath.join(base, href) if base else href
    return posixpath.normpath(path)


def _decode(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- container / OPF

def _opf_path(zf, names):
    try:
        root = ET.fromstring(zf.read("META-INF/container.xml"))
        for el in root.iter():
            if _local(el.tag) == "rootfile":
                fp = el.get("full-path")
                if fp:
                    return posixpath.normpath(fp)
    except Exception:
        pass
    opfs = sorted(n for n in names if n.endswith(".opf"))
    if opfs:
        return opfs[0]
    raise StructureError("no OPF package document found (bad container.xml, no *.opf)")


def _parse_opf(zf, opf_path):
    """OPF → {version, title, authors, manifest, spine (doc hrefs), ncx, nav}."""
    try:
        root = ET.fromstring(zf.read(opf_path))
    except Exception as e:
        raise StructureError("unparseable OPF %s: %s" % (opf_path, e))
    base = posixpath.dirname(opf_path)
    out = {"version": root.get("version") or "2.0", "title": "", "authors": [],
           "manifest": {}, "spine": [], "ncx": None, "nav": None}

    for el in root.iter():
        loc = _local(el.tag)
        if loc == "title" and not out["title"]:
            out["title"] = _norm_ws(" ".join(el.itertext()))
        elif loc == "creator":
            role = _attr(el, "role") or "aut"
            name = _norm_ws(" ".join(el.itertext()))
            if name and role == "aut":
                out["authors"].append(name)
        elif loc == "item":
            iid, href = el.get("id"), el.get("href")
            if not iid or not href:
                continue
            media = (el.get("media-type") or "").lower()
            props = (el.get("properties") or "").split()
            ab = _resolve(base, href)
            out["manifest"][iid] = {"href": ab, "media": media, "props": props}
            if media == "application/x-dtbncx+xml" and not out["ncx"]:
                out["ncx"] = ab
            if "nav" in props and not out["nav"]:
                out["nav"] = ab

    spine_el = None
    for el in root.iter():
        if _local(el.tag) == "spine":
            spine_el = el
            break
    if spine_el is not None:
        toc_id = spine_el.get("toc")
        if toc_id and toc_id in out["manifest"] and not out["ncx"]:
            out["ncx"] = out["manifest"][toc_id]["href"]
        for c in spine_el:
            if _local(c.tag) != "itemref":
                continue
            item = out["manifest"].get(c.get("idref") or "")
            if item and item["media"] in DOC_MEDIA:
                out["spine"].append(item["href"])
    return out


# ---------------------------------------------------------------- toc parsing

def _parse_ncx(data, base):
    """toc.ncx navMap → flat entries [{label, href, part, head}] (depth ≤ 2)."""
    root = ET.fromstring(data)
    navmap = None
    for el in root.iter():
        if _local(el.tag) == "navmap":
            navmap = el
            break
    if navmap is None:
        return []

    def label_of(np):
        nl = _child(np, "navlabel")
        return _norm_ws(" ".join(nl.itertext())) if nl is not None else ""

    def src_of(np):
        c = _child(np, "content")
        return _resolve(base, c.get("src")) if c is not None else None

    entries = []
    for np in navmap:
        if _local(np.tag) != "navpoint":
            continue
        kids = [c for c in np if _local(c.tag) == "navpoint"]
        label = label_of(np) or "Untitled"
        entries.append({"label": label, "href": src_of(np), "part": None,
                        "head": bool(kids)})
        for kid in kids:  # depth 3+ folds into its depth-2 parent via grouping
            entries.append({"label": label_of(kid) or "Untitled",
                            "href": src_of(kid), "part": label, "head": False})
    return [e for e in entries if e["href"]]


def _parse_nav(data, base):
    """EPUB3 nav.xhtml <nav epub:type=toc> → flat entries (depth ≤ 2)."""
    root = ET.fromstring(data)
    navs = [el for el in root.iter() if _local(el.tag) == "nav"]
    toc_nav = None
    for el in navs:
        t = _attr(el, "type") or ""
        if "toc" in t.split():
            toc_nav = el
            break
    if toc_nav is None and len(navs) == 1:
        toc_nav = navs[0]
    if toc_nav is None:
        return []
    ol = None
    for el in toc_nav.iter():
        if _local(el.tag) == "ol":
            ol = el
            break
    if ol is None:
        return []

    def li_parts(li):
        a = sub = None
        for c in li:
            lc = _local(c.tag)
            if lc in ("a", "span") and a is None:
                a = c
            elif lc == "ol" and sub is None:
                sub = c
        return a, sub

    def label_of(a):
        return _norm_ws(" ".join(a.itertext())) if a is not None else ""

    def href_of(a):
        if a is None or _local(a.tag) != "a":
            return None
        return _resolve(base, _attr(a, "href"))

    entries = []
    for li in ol:
        if _local(li.tag) != "li":
            continue
        a, sub = li_parts(li)
        kids = [c for c in sub if _local(c.tag) == "li"] if sub is not None else []
        label = label_of(a) or "Untitled"
        entries.append({"label": label, "href": href_of(a), "part": None,
                        "head": bool(kids)})
        for kli in kids:
            ka, _ = li_parts(kli)
            entries.append({"label": label_of(ka) or "Untitled",
                            "href": href_of(ka), "part": label, "head": False})
    return [e for e in entries if e["href"]]


def _load_toc(zf, names, opf):
    """Returns ("ncx"|"nav"|"inferred", entries). EPUB2 prefers ncx, EPUB3 nav."""
    order = ["ncx", "nav"] if opf["version"].startswith("2") else ["nav", "ncx"]
    parsers = {"ncx": _parse_ncx, "nav": _parse_nav}
    for kind in order:
        href = opf[kind]
        if not href or href not in names:
            continue
        try:
            entries = parsers[kind](zf.read(href), posixpath.dirname(href))
        except Exception:
            entries = []
        if entries:
            return kind, entries
    return "inferred", []


# ---------------------------------------------------------------- paragraph extraction

def _paras_bs4(data):
    """Primary parser: outermost block elements via BeautifulSoup.

    Returns list of (text, is_heading)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    for el in soup(["script", "style", "head", "title"]):
        el.decompose()
    body = soup.body or soup
    for el in body.find_all(["br", "img", "hr"]):
        el.replace_with(" ")
    blocks = []
    tags = list(BLOCK_TAGS)
    for el in body.find_all(tags):
        if el.find_parent(tags) is not None:
            continue  # nested block (p in blockquote, li in li…) — outermost wins
        text = _norm_ws(el.get_text())
        if text:
            blocks.append((text, el.name in HEADING_TAGS))
    if not blocks:  # unwrapped text (no block markup at all) — line-split fallback
        for line in body.get_text("\n").splitlines():
            line = _norm_ws(line)
            if line:
                blocks.append((line, False))
    return blocks


class _BlockParser(html.parser.HTMLParser):
    """Fallback parser: collect outermost block-element text with stdlib only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []      # [(text, is_heading)]
        self.all_text = []    # every data chunk outside script/style/head
        self._stack = []      # open block tags
        self._outer = None
        self._buf = []
        self._skip = 0

    def _flush(self):
        text = _norm_ws("".join(self._buf))
        if text:
            self.blocks.append((text, self._outer in HEADING_TAGS))
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self._skip += 1
            return
        if tag == "br":
            if self._stack:
                self._buf.append(" ")
            return
        if tag in BLOCK_TAGS:
            if tag == "p" and self._stack and self._stack[-1] == "p":
                self.handle_endtag("p")  # tolerate unclosed <p>
            if not self._stack:
                self._outer = tag
                self._buf = []
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            if self._skip:
                self._skip -= 1
            return
        if tag in BLOCK_TAGS and tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break
            if not self._stack:
                self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        self.all_text.append(data)
        if self._stack:
            self._buf.append(data)

    def close(self):
        super().close()
        if self._stack:
            self._stack = []
            self._flush()


def _paras_stdlib(data):
    """Fallback parser wrapper. Returns list of (text, is_heading)."""
    parser = _BlockParser()
    try:
        parser.feed(_decode(data))
        parser.close()
    except Exception:
        pass
    if parser.blocks:
        return parser.blocks
    blocks = []
    for line in "".join(parser.all_text).splitlines():
        line = _norm_ws(line)
        if line:
            blocks.append((line, False))
    return blocks


# ---------------------------------------------------------------- entry building

def _group_by_toc(spine, toc_entries, doc_paras):
    """Group spine docs under the toc entry whose target precedes them.

    Multiple spine docs per entry are concatenated (¶ numbering continues).
    Bare part-heading pages (<50 words, nested children) are merged into the
    children's "part" label instead of becoming their own chapter."""
    pos = {}
    for i, href in enumerate(spine):
        pos.setdefault(href, i)
    kept, seen = [], set()
    for e in toc_entries:
        href = e["href"]
        if href not in pos or href in seen:
            continue  # off-spine target, or 2nd entry into the same doc
        seen.add(href)
        kept.append({"label": e["label"], "part": e["part"], "head": e["head"],
                     "spine_idx": pos[href], "paras": []})
    if not kept:
        return []
    kept.sort(key=lambda e: e["spine_idx"])
    idxs = [e["spine_idx"] for e in kept]
    for i, href in enumerate(spine):
        j = bisect.bisect_right(idxs, i) - 1
        if j < 0:
            j = 0  # docs before the first toc target join the first entry
        kept[j]["paras"].extend(doc_paras.get(href, []))

    entries = []
    for e in kept:
        words = sum(util.word_count(t) for t, _ in e["paras"])
        if e["head"] and words < PART_HEAD_MAX_WORDS:
            continue  # bare part page — children already carry part=label
        entries.append(e)
    # A surviving head is a "part intro": it belongs to its own part — but only
    # when real child entries exist (nav children that are mere same-doc
    # fragment links collapse into the head, which is then just a chapter).
    child_parts = set(e["part"] for e in entries if e["part"])
    for e in entries:
        if e["head"] and e["part"] is None:
            e["part"] = e["label"] if e["label"] in child_parts else None
    return entries


def _infer_entries(spine, doc_paras):
    """No usable toc: one spine doc = one chapter, titled by its first heading."""
    entries, seen = [], set()
    for href in spine:
        if href in seen:
            continue
        seen.add(href)
        paras = doc_paras.get(href) or []
        if not paras:
            continue
        heading = next((t for t, h in paras if h), None)
        label = heading or ("Untitled %d" % (len(entries) + 1))
        entries.append({"label": label, "part": None, "paras": paras})
    return entries


def _classify(entries):
    """Seed kind = front|chapter|back per entry (label regex + position)."""
    raw = []
    for e in entries:
        if FRONT_RE.search(e["label"]):
            raw.append("front-ish")
        elif BACK_RE.search(e["label"]):
            raw.append("back-ish")
        else:
            raw.append("chapter")
    ch_idx = [i for i, k in enumerate(raw) if k == "chapter"]
    if not ch_idx:
        for e in entries:
            e["kind"] = "chapter"
        return
    first, last = ch_idx[0], ch_idx[-1]
    for i, e in enumerate(entries):
        if raw[i] == "front-ish":
            e["kind"] = "front" if i < first else ("back" if i > last else "chapter")
        elif raw[i] == "back-ish":
            e["kind"] = "back" if i > last else "chapter"
        else:
            e["kind"] = "chapter"


# ---------------------------------------------------------------- output

def _write_chapter_md(path, chid, title, texts, words):
    lines = ["# %s — %s  (%d paragraphs, %d words)" % (chid, title, len(texts), words)]
    for i, text in enumerate(texts):
        lines.append("[¶%d] %s" % (i + 1, text))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- build

def build(book_dir, epub_path):
    """Extract structure from epub_path into book_dir (book.json + text/*.md).

    Returns the book.json dict; raises StructureError on failure."""
    book_dir, epub_path = Path(book_dir), Path(epub_path)
    try:
        zf = zipfile.ZipFile(str(epub_path))
    except Exception as e:
        raise StructureError("cannot open epub %s: %s" % (epub_path, e))

    use_primary = _probe_primary()
    parse_doc = _paras_bs4 if use_primary else _paras_stdlib

    with zf:
        names = set(zf.namelist())
        opf_path = _opf_path(zf, names)
        opf = _parse_opf(zf, opf_path)
        spine = [h for h in opf["spine"] if h in names]
        if not spine:
            raise StructureError("no readable documents in OPF spine")

        doc_paras = {}
        for href in spine:
            if href not in doc_paras:
                doc_paras[href] = parse_doc(zf.read(href))

        toc_kind, toc_entries = _load_toc(zf, names, opf)
        entries = _group_by_toc(spine, toc_entries, doc_paras) if toc_entries else []
        if entries:
            structure_kind = "toc"
        else:
            toc_kind, structure_kind = "inferred", "inferred"
            entries = _infer_entries(spine, doc_paras)
    if not entries:
        raise StructureError("no text extracted from any spine document")

    _classify(entries)

    title = opf["title"]
    if not title:
        stem = epub_path.stem
        title = stem if stem.lower() != "book" else book_dir.name

    try:
        source_file = str(epub_path.relative_to(book_dir))
    except ValueError:
        source_file = "source/book.epub"

    text_dir = book_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)

    totals = {"front": 0, "chapter": 0, "back": 0}
    for e in entries:
        totals[e["kind"]] += 1
    prefix = {"front": "fm", "chapter": "ch", "back": "bm"}
    counters = {"front": 0, "chapter": 0, "back": 0}

    chapters = []
    total_words = total_paras = 0
    for i, e in enumerate(entries):
        kind = e["kind"]
        counters[kind] += 1
        width = 3 if totals[kind] > 99 else 2
        chid = "%s%0*d" % (prefix[kind], width, counters[kind])
        texts = [t for t, _ in e["paras"]]
        words = sum(util.word_count(t) for t in texts)
        headings = [{"para": j + 1, "text": t}
                    for j, (t, h) in enumerate(e["paras"]) if h]
        chapters.append({
            "id": chid,
            "index": i + 1,
            "title": e["label"],
            "part": e.get("part"),
            "kind": kind,
            "words": words,
            "paragraphs": len(texts),
            "oversize": words > OVERSIZE_WORDS,
            "headings": headings,
        })
        _write_chapter_md(text_dir / ("%s.md" % chid), chid, e["label"], texts, words)
        total_words += words
        total_paras += len(texts)

    if total_words == 0:
        raise StructureError("extraction produced zero words (DRM or image-only epub?)")

    book = {
        "slug": book_dir.name,
        "title": title,
        "authors": opf["authors"],
        "source": {
            "file": source_file,
            "sha256": util.sha256_file(epub_path),
            "toc": toc_kind,
            "method": "ebooklib" if use_primary else "stdlib",
            "structure": structure_kind,
        },
        "stats": {
            "words": total_words,
            "chapters": totals["chapter"],
            "front": totals["front"],
            "back": totals["back"],
            "paragraphs": total_paras,
        },
        "chapters": chapters,
    }
    util.save_json(book_dir / "book.json", book)
    return book
