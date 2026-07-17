# Workflow 03 — Compose the Dossier (stage 3)

**Kind**: agent step (judgment). **Context**: `format/dossier-format-v2.md`,
`skeleton.json`, and `packets/*.md` — NEVER the full book text (`text/` is off-limits
here except to double-check a single anchor).

## Purpose
Compose `books/<slug>/dossier.md` — the 16-section analytical dossier — from the packets.
The format spec is the binding contract; read it fully before writing anything.

## Steps
1. Read `format/dossier-format-v2.md` end to end. Read `skeleton.json` for the
   analyzable chapter list and titles.
2. Create `dossier.md` with all 17 H2 headings (`## 0.` … `## 16.`) as a skeleton first,
   so nothing gets forgotten. Leave §16 as a stub containing only the two marker lines:
   ```
   <!-- verification:begin -->
   <!-- verification:end -->
   ```
3. **§5 first**, one packet per pass: for each analyzable chapter in book order, read
   ONLY that packet and write its `### Chapter …` entry (H3 + `_Covers …_` line +
   labeled fields, ≥350 words). Do not summarize packets from memory — open each one.
4. Then the cross-chapter sections, ONE SECTION PER PASS, each from field slices:
   - §4 Terminology: from all packets' `## Concepts` + relevant claims. Dedup terms;
     record first introduction.
   - §6 Argument Chain: from all `## Thesis` + `## Claims`. Steps `A*/P*/M*/I*/C*`,
     every step line anchored.
   - §7 Evidence Ledger: from all `## Evidence` — copy anchors + quote fragments
     VERBATIM from packets. ≥1 row per chapter.
   - §2, §8: from `## Purpose`, `## Reader Assumptions`, `## Links`.
   - §9: from `## Foundational Vs Illustrative`.
   - §10, §12: from `## Tension` fields.
   - §11: practical meaning, grounded in claims you already anchored.
   - §14: 20 ideas from `## Retain` + synthesis; question bank = every packet `## Recall`
     question verbatim + ≥8 new synthesis questions spanning ≥2 chapters; the fixed
     self-test protocol block.
   - §0, §1, §3, §15 last (they describe the whole).
5. Export the §14 question bank 1:1 into `books/<slug>/recall.md` (same Q ids and text,
   answers in `<details>` blocks, plain answer key at the bottom, the how-to-use block).
6. §13 External Evaluation: if you have reliable outside knowledge of the book's
   reception/later research, write it with external citations. If not, write exactly:
   `External research was not performed.` Do not fake external sources.

## Rules
- Every anchor is COPIED from a packet (exceptions: §3 table `[chNN ¶1]`, §13 externals).
  A new cross-chapter claim needs ≥2 packet anchors from the chapters it spans.
- Never shorten later sections because earlier ones ran long. Word floors are per
  section; repair by expanding, never by trimming elsewhere.
- Dense, precise prose. No filler, no praise, no hedging boilerplate.

## Definition of done
```
python3 booker.py check <slug> --stage 3
```
exits 0 (all sections present, total ≥ 14k words). Full quality gates come in stage 4.
