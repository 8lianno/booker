# booker

Turn an EPUB into the **verified essence of a book**: a deep 16-section analytical
dossier (~16–22k words) with source anchors down to the paragraph, an automated
coverage + claim-support audit, a spaced-repetition recall quiz, and clean HTML/PDF —
so you get what the book actually says, checked against the text, in a fraction of the
reading time.

Works with any coding-agent CLI (Claude Code, Codex, Kimi Code, GLM …): the pipeline is
plain Python scripts + markdown workflows, with all state on disk.

## Use

```bash
python3 booker.py new --title "high output management"   # from the Calibre library
python3 booker.py new /path/to/book.epub                 # or a direct path
python3 booker.py status <slug>                          # what's done, what's NEXT
```

Then let your agent follow `AGENTS.md`. Outputs land in `books/<slug>/`:
`dossier.md` / `dossier.html` / `dossier.pdf` / `dossier.epub` (e-reader edition),
`recall.md` (self-test quiz), and a verification report with a score and badge.
Rendered outputs show source anchors as unobtrusive hover markers (toggle in the
HTML: markers · full · hidden); the raw anchors live in `dossier.md`.

## Library

<!-- BOOKER:INDEX -->
| Title | Author | Date | Words | Score / Badge | Links |
|---|---|---|---|---|---|
| High Output Management | Andrew S. Grove | 2026-07-17 | 33,675 | 99.4 · VERIFIED | [epub](books/high-output-management/dossier.epub) · [html](books/high-output-management/dossier.html) · [md](books/high-output-management/dossier.md) · [pdf](books/high-output-management/dossier.pdf) |
<!-- /BOOKER:INDEX -->

## How it works

EPUB → structured extraction (numbered paragraphs) → per-chapter analysis packets
(one fresh context each — no whole-book prompt ever exists) → section-by-section
composition → deterministic verification (anchors, coverage, floors) + sampled
claim-support audit → render + index. Details: `AGENTS.md`, `format/`, `workflow/`.
