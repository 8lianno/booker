<div align="center">
  <h1>📚 Booker</h1>
  <p><b>Automated Literary Intelligence & Narrative Forensics</b></p>
  
  <a href="https://github.com/8lianno/booker"><img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"></a>
  <a href="https://github.com/8lianno/booker"><img src="https://img.shields.io/badge/Engine-NotebookLM-orange?style=for-the-badge&logo=google&logoColor=white" alt="NotebookLM"></a>
  <a href="https://github.com/8lianno/booker"><img src="https://img.shields.io/badge/Render-Pandoc%20%7C%20WeasyPrint-green?style=for-the-badge" alt="Pandoc & WeasyPrint"></a>
  <a href="https://github.com/8lianno/booker"><img src="https://img.shields.io/badge/License-MIT-lightgray?style=for-the-badge" alt="License"></a>
</div>

<br/>

**Booker** is an automated narrative intelligence pipeline. It turns raw EPUBs into **verified, high-yield dossiers**—stripping away the fluff to extract pure plot mechanics, character arcs, thematic DNA, and actionable frameworks in a fraction of the reading time.

Whether it's non-fiction strategic insights or fiction plot forensics, Booker synthesizes the core narrative into beautifully formatted, 15k+ word documents complete with source-anchors and recall quizzes.

---

## ⚡ Features

- 🧠 **Dual Analytical Engines:** Custom processors for both **Fiction** (plot mechanics, worldbuilding, act structures) and **Non-Fiction** (mental models, actionable insights, frameworks).
- 🚀 **NotebookLM Integration:** Bypasses context limits and read timeouts by employing chunked batch processing directly against the NotebookLM API.
- 🎨 **Multi-Format Export:** Generates clean, typography-focused `.epub` for e-readers, `.pdf` for print, `.html` for web, and raw `.md`.
- 🔎 **Source Anchoring:** Extracts verifiable insights, automatically anchoring claims down to the exact chapter and paragraph.
- 🚫 **No AI Fluff:** Strict parsing rules completely ban "conversational filler" and "chatty AI" artifacts. You get pure narrative data.

## 🛠️ Usage

Works seamlessly with any coding-agent CLI (Claude Code, Google Antigravity, Kimi Code). The pipeline relies entirely on Python scripts and markdown workflows with local state.

### Generating a New Dossier
```bash
python3 booker.py new --title "the count of monte cristo"   # Fetches from local Calibre library
python3 booker.py new /path/to/book.epub                    # Or specify a direct path
```

### Rendering & Status
```bash
python3 booker.py status <slug>                             # View processing state and next steps
python3 booker.py render <slug>                             # Generate EPUB, HTML, and PDF exports
python3 booker.py index                                     # Update the README index
```

## 📁 Output Structure

Dossiers are saved in the `books/<slug>/` directory. A complete synthesis produces:
- `dossier.md` (Raw source Markdown)
- `dossier.epub` (Beautifully justified for e-readers)
- `dossier.pdf` (Print-ready document)
- `dossier.html` (Web view with unobtrusive hover markers)
- `recall.md` (Spaced-repetition recall quiz)
- `verification.json` (Coverage, claim-support audit, and scoring)

---

## 📚 Library Index

<!-- BOOKER:INDEX -->
| Title | Author | Date | Words | Score / Badge | Links |
|---|---|---|---|---|---|
| Dopamine Nation: Finding Balance in the Age of Indulgence | Anna Lembke | 2026-07-17 | – | stage 2 (packets) | – |
| High Output Management | Andrew S. Grove | 2026-07-23 | 14,020 | stage 4 (verify) | [epub](books/high-output-management/dossier.epub) · [html](books/high-output-management/dossier.html) · [md](books/high-output-management/dossier.md) · [pdf](books/high-output-management/dossier.pdf) |
| The Count of Monte Cristo | Alexandre Dumas | 2026-07-23 | 54,310 | stage 1 (skeleton) | [epub](books/the-count-of-monte-cristo/dossier.epub) · [html](books/the-count-of-monte-cristo/dossier.html) · [md](books/the-count-of-monte-cristo/dossier.md) · [pdf](books/the-count-of-monte-cristo/dossier.pdf) |
| The Great Gatsby | F. Scott Fitzgerald | 2026-07-23 | 163 | stage 0 (init/extract) | [epub](books/the-great-gatsby/dossier.epub) · [html](books/the-great-gatsby/dossier.html) · [md](books/the-great-gatsby/dossier.md) |
<!-- /BOOKER:INDEX -->

---

## ⚙️ Architecture

1. **EPUB Ingestion:** Raw EPUB is parsed into structured, numbered paragraphs (`ch001`, `fm01`).
2. **NotebookLM Batching:** Chapter journeys are queried in chunks of 15 to bypass API timeouts.
3. **Engine Synthesis:** Based on `genre`, either the Fiction or Non-Fiction synthesizer builds a multi-section narrative framework.
4. **Deterministic Verification:** Coverage and anchors are audited, generating a final badge score.
5. **Rendering Pipeline:** Pandoc and WeasyPrint transform the sanitized markdown into highly styled outputs. 

<div align="center">
  <sub>Built for precision reading and narrative extraction.</sub>
</div>
