#!/usr/bin/env python3
"""Deterministic EPUB2 fixture builder for booker tests. stdlib zipfile ONLY.

build_fixture_epub(dest, chapters=5, words_per_chapter=2600) writes a valid
minimal EPUB2: mimetype (stored, first entry), META-INF/container.xml,
OEBPS/content.opf, OEBPS/toc.ncx and one XHTML file per chapter. Chapter text
is seeded pseudo-prose (no random state, no datetime) so repeated builds are
byte-identical. Each chapter carries one known sentinel sentence
("The quick brown fox number N jumps over the lazy dog.") for anchor/quote
tests, plus two <h2> section headings.

Runnable:  python3 tests/make_fixture.py <dest.epub> [chapters] [words_per_chapter]
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

BOOK_TITLE = "Fixture Book"
BOOK_AUTHOR = "Test Author"
BOOK_UID = "urn:uuid:f1e2d3c4-0000-4000-8000-b00c00f1c700"

CHAPTER_NAMES = (
    "Origins", "Momentum", "Turning Points", "Consequences", "Resolution",
    "Echoes", "Departure", "Return", "Threshold", "Synthesis",
)

# Fixed vocabulary for the pseudo-prose generator.
WORDS = (
    "the analysis shows that careful readers notice gradual change and steady "
    "patterns emerge when systems adapt under pressure while feedback loops "
    "shape behaviour over time because incentives quietly govern choices since "
    "structure precedes outcome and habits compound across many small decisions"
).split()

ZIP_DATE = (2020, 1, 1, 0, 0, 0)


def sentinel(n):
    """The known sentinel sentence embedded once in chapter n."""
    return "The quick brown fox number %d jumps over the lazy dog." % n


# ---------------------------------------------------------------- pseudo-text

class _Rng(object):
    """Tiny LCG — deterministic across Python versions, no random module."""

    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFF

    def _next(self):
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF
        return self.state >> 8

    def randint(self, low, high):
        return low + self._next() % (high - low + 1)

    def choice(self, seq):
        return seq[self._next() % len(seq)]


def _sentence(rng):
    n_words = rng.randint(8, 16)
    words = [rng.choice(WORDS) for _ in range(n_words)]
    return words[0].capitalize() + " " + " ".join(words[1:]) + "."


def _paragraphs(rng, budget):
    """Paragraphs of 3–6 sentences totalling at least `budget` words."""
    paras, total = [], 0
    while total < budget:
        para = " ".join(_sentence(rng) for _ in range(rng.randint(3, 6)))
        paras.append(para)
        total += len(para.split())
    return paras


# ---------------------------------------------------------------- documents

def _chapter_xhtml(number, name, words_per_chapter):
    rng = _Rng(0xB00C + number * 7919)
    paras = _paragraphs(rng, words_per_chapter)
    # sentinel goes in as its own second paragraph
    paras.insert(1, sentinel(number))

    blocks = ["<h1>Chapter %d: %s</h1>" % (number, name)]
    h2_at = {max(2, len(paras) // 3): "Section %d.1: Early %s" % (number, name),
             max(3, (2 * len(paras)) // 3): "Section %d.2: Late %s" % (number, name)}
    for i, para in enumerate(paras):
        if i in h2_at:
            blocks.append("<h2>%s</h2>" % h2_at[i])
        blocks.append("<p>%s</p>" % para)

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        "<head><title>Chapter %d: %s</title></head>\n"
        "<body>\n%s\n</body>\n</html>\n" % (number, name, "\n".join(blocks))
    )


def _container_xml():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        '    <rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    )


def _content_opf(n_chapters):
    items, refs = [], []
    for i in range(1, n_chapters + 1):
        items.append('    <item id="chap%d" href="chapter%02d.xhtml" '
                     'media-type="application/xhtml+xml"/>' % (i, i))
        refs.append('    <itemref idref="chap%d"/>' % i)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'unique-identifier="bookid" version="2.0">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:opf="http://www.idpf.org/2007/opf">\n'
        "    <dc:title>%s</dc:title>\n"
        '    <dc:creator opf:role="aut">%s</dc:creator>\n'
        "    <dc:language>en</dc:language>\n"
        '    <dc:identifier id="bookid">%s</dc:identifier>\n'
        "  </metadata>\n"
        "  <manifest>\n"
        '    <item id="ncx" href="toc.ncx" '
        'media-type="application/x-dtbncx+xml"/>\n'
        "%s\n"
        "  </manifest>\n"
        '  <spine toc="ncx">\n'
        "%s\n"
        "  </spine>\n"
        "</package>\n" % (BOOK_TITLE, BOOK_AUTHOR, BOOK_UID,
                          "\n".join(items), "\n".join(refs))
    )


def _toc_ncx(chapter_names):
    points = []
    for i, name in enumerate(chapter_names, 1):
        points.append(
            '    <navPoint id="navpoint-%d" playOrder="%d">\n'
            "      <navLabel><text>Chapter %d: %s</text></navLabel>\n"
            '      <content src="chapter%02d.xhtml"/>\n'
            "    </navPoint>" % (i, i, i, name, i))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
        '"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        "  <head>\n"
        '    <meta name="dtb:uid" content="%s"/>\n'
        '    <meta name="dtb:depth" content="1"/>\n'
        '    <meta name="dtb:totalPageCount" content="0"/>\n'
        '    <meta name="dtb:maxPageNumber" content="0"/>\n'
        "  </head>\n"
        "  <docTitle><text>%s</text></docTitle>\n"
        "  <navMap>\n"
        "%s\n"
        "  </navMap>\n"
        "</ncx>\n" % (BOOK_UID, BOOK_TITLE, "\n".join(points))
    )


# ---------------------------------------------------------------- assembly

def _add(zf, name, data, compress_type=zipfile.ZIP_DEFLATED):
    info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
    info.compress_type = compress_type
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def build_fixture_epub(dest, chapters=5, words_per_chapter=2600):
    """Write a deterministic EPUB2 fixture to dest; return Path(dest)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    names = [CHAPTER_NAMES[(i - 1) % len(CHAPTER_NAMES)]
             for i in range(1, chapters + 1)]
    with zipfile.ZipFile(dest, "w") as zf:
        _add(zf, "mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        _add(zf, "META-INF/container.xml", _container_xml())
        _add(zf, "OEBPS/content.opf", _content_opf(chapters))
        _add(zf, "OEBPS/toc.ncx", _toc_ncx(names))
        for i, name in enumerate(names, 1):
            _add(zf, "OEBPS/chapter%02d.xhtml" % i,
                 _chapter_xhtml(i, name, words_per_chapter))
    return dest


def main(argv):
    if len(argv) < 2:
        print("usage: python3 tests/make_fixture.py <dest.epub> "
              "[chapters] [words_per_chapter]", file=sys.stderr)
        return 1
    chapters = int(argv[2]) if len(argv) > 2 else 5
    wpc = int(argv[3]) if len(argv) > 3 else 2600
    path = build_fixture_epub(argv[1], chapters=chapters, words_per_chapter=wpc)
    print("wrote %s (%d chapters, ~%d words/chapter)" % (path, chapters, wpc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
