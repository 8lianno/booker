# Workflow 01 — Skeleton (stage 1)

**Kind**: agent step (judgment). **Context needed**: `books/<slug>/book.json` and
`books/<slug>/meta.json` ONLY. Do not read the chapter text files in this stage.

## Purpose
Decide which chapters get analyzed, fix mangled titles, and group micro-chapters, so
stage 2 does exactly the right amount of work.

## Steps
1. Read `books/<slug>/book.json`. Look at every chapter entry: id, title, kind, words,
   paragraphs.
2. Decide `analyze` per chapter:
   - `true` for every substantive chapter (kind `chapter`), including introduction,
     conclusion, epilogue if they carry argument.
   - `false` for front/back matter that carries no argument (title page, copyright,
     contents, dedication, praise, index, pure bibliography). Give a short `reason`.
   - Appendices and notes sections: `true` only if they carry substantive argument.
3. Fix titles that are obviously mangled by extraction (keep them short and faithful).
4. **Grouping** (mainly for `structure=inferred` books): if several tiny consecutive
   entries (< ~800 words each) are really one logical chapter, mark each member with
   `"group": "<head-id>"` where head-id is the FIRST member's id. The head keeps
   `analyze: true`; members also get `analyze: true` plus the `group` field. One packet
   (named after the head) will cover them, and its anchors may cite any member id.
5. Copy the first 12 hex chars of `book_json_sha256` from `meta.json` into the skeleton.
6. Write `books/<slug>/skeleton.json`:

```json
{
  "book_json_sha256_12": "9f3ac21b0d4e",
  "chapters": [
    {"id": "fm01", "analyze": false, "title": "Title Page", "reason": "front matter"},
    {"id": "ch01", "analyze": true,  "title": "The Basics"},
    {"id": "ch02", "analyze": true,  "title": "Part One", "group": "ch02"},
    {"id": "ch03", "analyze": true,  "title": "Continuation", "group": "ch02"},
    {"id": "bm01", "analyze": false, "title": "Index", "reason": "back matter"}
  ]
}
```

Every chapter id from `book.json` must appear exactly once. At least 3 entries must be
`analyze: true`.

## Definition of done
```
python3 booker.py check <slug> --stage 1
```
exits 0.
