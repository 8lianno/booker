# Workflow 00 — Init / Extract (stage 0)

**Kind**: script step (deterministic). **You need**: an EPUB path or a book title.

## Inputs
- An `.epub` file, or a title present in the Calibre library.

## Steps
1. If you only have a title, preview the match first:
   ```
   python3 booker.py resolve --title "high output management"
   ```
   If the top match is wrong or ambiguous, use the explicit path form below.
2. Create the book:
   ```
   python3 booker.py new --title "high output management"
   # or
   python3 booker.py new "/path/to/book.epub" [--slug my-slug]
   ```
3. Read the command output. Confirm the resolved title/author is the book the user
   intended. If not: delete `books/<slug>/` and re-run with `--epub` or a better title.
4. If the output shows `structure=inferred`, the EPUB had no usable table of contents —
   chapter boundaries were guessed from spine files. Stage 1 then needs extra care
   (expect mis-split or micro chapters; use `group` liberally).

## Rules
- Never re-run `new` on an existing slug without `--force`. `--force` renames the old
  directory to `books/<slug>.bak-<timestamp>` — anchors are never silently renumbered.
- Never read `source/book.epub` directly in later stages; the pipeline's source of truth
  is `book.json` + `text/`.

## Definition of done
```
python3 booker.py check <slug> --stage 0
```
exits 0. Then run `python3 booker.py status <slug>` and follow NEXT.
