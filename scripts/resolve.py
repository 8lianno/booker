#!/usr/bin/env python3
"""Calibre title resolution + catalog enrichment for booker.

Two entry points, both stdlib-only:

    resolve_title(query, library_root) -> list[dict]
        Fuzzy-match a title against the EPUBs in a Calibre library tree.
        Layout assumed: Author/Title (id)/Title - Author.epub. Each candidate:
        {"path", "title", "author", "score", "calibre_id"} sorted by score desc.

    enrich_from_catalog(title, books_txt) -> dict
        Pull {"calibre_id", "pubdate", "tags"} for a title out of a WRAPPED
        fixed-width `calibredb list` dump. Defensive: returns {} on ANY failure,
        never raises.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import util

SCORE_FLOOR = 0.35
TOKEN_BONUS = 0.20
CATALOG_MATCH_MIN = 0.60

_ID_SUFFIX = re.compile(r"\((\d+)\)\s*$")


# ---------------------------------------------------------------- title resolution

def _norm(text):
    """casefold + strip punctuation -> single-spaced token string."""
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return " ".join(text.split()).casefold()


def _score(query_norm, title_norm):
    ratio = difflib.SequenceMatcher(None, query_norm, title_norm).ratio()
    q_tokens = set(query_norm.split())
    t_tokens = set(title_norm.split())
    if q_tokens and q_tokens <= t_tokens:
        ratio += TOKEN_BONUS
    return min(ratio, 1.0)


def resolve_title(query, library_root):
    """All EPUBs under library_root whose title scores > 0.35 vs query,
    sorted by score descending."""
    root = Path(library_root)
    if not root.exists():
        return []
    query_norm = _norm(query or "")
    out = []
    for epub in sorted(root.rglob("*.epub")):
        stem = epub.stem
        if " - " in stem:
            title, author = stem.rsplit(" - ", 1)
        else:
            title, author = stem, ""
        m = _ID_SUFFIX.search(epub.parent.name)
        calibre_id = int(m.group(1)) if m else None
        score = _score(query_norm, _norm(title))
        if score > SCORE_FLOOR:
            out.append({
                "path": str(epub),
                "title": title.strip(),
                "author": author.strip(),
                "score": round(score, 4),
                "calibre_id": calibre_id,
            })
    out.sort(key=lambda c: (-c["score"], c["title"], c["path"]))
    return out


# ---------------------------------------------------------------- catalog parsing

def _column_bounds(header):
    """(name, start, end) triples for each column of a calibredb list header.

    Handles both separator styles: an explicit separator char (`--separator ;`)
    at fixed offsets, or plain fixed-width columns split on runs of spaces."""
    if ";" in header:
        bounds = []
        prev = 0
        for i, ch in enumerate(header):
            if ch == ";":
                bounds.append((prev, i))
                prev = i + 1
        if header[prev:].strip():
            bounds.append((prev, None))
    else:
        starts = [m.start() for m in re.finditer(r"\S+", header)]
        bounds = []
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else None
            bounds.append((start, end))
    cols = []
    for start, end in bounds:
        name = (header[start:end] if end is not None else header[start:]).strip().casefold()
        cols.append((name, start, end))
    return cols


def _cells(line, cols):
    out = []
    for _, start, end in cols:
        out.append(line[start:end] if end is not None else line[start:])
    return out


def _parse_catalog(text):
    """Parse wrapped fixed-width calibredb output into a list of records.

    The header row defines column offsets. Data rows wrap: continuation rows
    have a blank id column and are string-concatenated per column (no space)
    onto the previous record."""
    lines = text.splitlines()
    if not lines:
        return []
    cols = _column_bounds(lines[0])
    names = [c[0] for c in cols]
    if "id" not in names or "title" not in names:
        return []
    id_idx = names.index("id")

    records = []
    current = None
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = _cells(line, cols)
        id_cell = cells[id_idx].strip()
        if id_cell.isdigit():
            if current is not None:
                records.append(current)
            current = [c.strip() for c in cells]
        elif not id_cell and current is not None:
            for i, cell in enumerate(cells):
                current[i] += cell.strip()
        # anything else (rulers, noise) is ignored
    if current is not None:
        records.append(current)
    return [dict(zip(names, rec)) for rec in records]


def _despace(text):
    """Normalized comparison key with all spaces removed — wrapped catalog
    titles lose spaces at wrap points, so compare space-insensitively."""
    return util.normalize_for_match(text).replace(" ", "")


def enrich_from_catalog(title, books_txt):
    """{"calibre_id", "pubdate", "tags"} for the best catalog match, else {}.
    Never raises."""
    try:
        if not title:
            return {}
        path = Path(books_txt)
        if not path.exists():
            return {}
        records = _parse_catalog(path.read_text(encoding="utf-8", errors="replace"))
        if not records:
            return {}

        target = _despace(title)
        if not target:
            return {}
        best, best_ratio = None, 0.0
        for rec in records:
            key = _despace(rec.get("title", ""))
            if not key:
                continue
            if key == target:
                best, best_ratio = rec, 1.0
                break
            ratio = difflib.SequenceMatcher(None, target, key).ratio()
            if ratio > best_ratio:
                best, best_ratio = rec, ratio
        if best is None or best_ratio < CATALOG_MATCH_MIN:
            return {}

        tags = [t.strip() for t in best.get("tags", "").split(",") if t.strip()]
        return {
            "calibre_id": int(best["id"]),
            "pubdate": best.get("pubdate", ""),
            "tags": tags,
        }
    except Exception:
        return {}
