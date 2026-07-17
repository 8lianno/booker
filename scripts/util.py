#!/usr/bin/env python3
"""Shared helpers for booker. Python 3.9+, stdlib only."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = REPO_ROOT / "books"
FORMAT_DIR = REPO_ROOT / "format"


def book_dir(slug):
    return BOOKS_DIR / slug


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha12(hexdigest):
    return hexdigest[:12]


def word_count(text):
    return len(re.findall(r"\S+", text))


def slugify(title):
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", text) or "book"


def normalize_for_match(text):
    """Normalization used for quote-fragment matching and heading comparison."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace("…", "...")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.rstrip(".,;:!?")


def sections_config():
    return load_json(FORMAT_DIR / "sections-v2.json")
