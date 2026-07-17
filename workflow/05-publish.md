# Workflow 05 — Render + Index (stages 5–6)

**Kind**: script steps.

## Steps
1. ```
   python3 booker.py render <slug>
   ```
   Produces `dossier.html` (always), `dossier.pdf` (weasyprint/pandoc) and
   `dossier.epub` (pandoc) — a styled, e-reader-ready edition of the dossier.
   PDF/EPUB failures are recorded but are never gates. Add `--skip-pdf` to skip PDF.
   Rendered outputs show anchors as small hover markers (toggleable in HTML);
   the full `[chNN ¶k]` anchors live only in `dossier.md`.
2. ```
   python3 booker.py index
   ```
   Regenerates `catalog.json`, `index.html`, and the README library table.
3. Report to the user: paths of `dossier.md`, `dossier.html`, `dossier.pdf` /
   `dossier.epub` (if any), `recall.md`, the verification score/badge, and total
   word count.

## Definition of done
```
python3 booker.py check <slug> --stage 6
```
exits 0 — the book is complete.
