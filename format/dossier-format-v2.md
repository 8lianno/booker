# Dossier Format v2 — Output Contract

This is the binding contract for `books/<slug>/dossier.md`. The deterministic checker
(`python3 booker.py verify <slug>`) enforces every rule marked **[checked]**. Read this
whole file before composing any section.

Supersedes the v1 spec (16-section reader-equivalent dossier). Section order and identity
are unchanged; v2 adds source anchors, per-section floors, and machine-detectable structure.

## Purpose

A smart reader who did NOT read the book must be able to understand: the problem the author
solves, what the author really believes, how the book is structured, how ideas build chapter
by chapter, major terms and why they matter, central examples and evidence, load-bearing vs
secondary material, practical implications, internal tensions, and limits — with every
substantive claim traceable to a location in the source.

## Global rules

1. **Total length**: 16,000–22,000 words across §1–§15 (excluding tables' anchor columns
   and §16 machine blocks). **[checked: total ≥ 14,000 hard floor]**
2. **Exact H2 headings**, in order, machine-detectable **[checked]**:
   `## 0. Source Note And Confidence` … `## 16. Coverage Audit And Verification`
   (17 headings total; full list in `sections-v2.json`).
3. **Anchor density**: ≥ 5 anchors per 1,000 words across §2–§12 combined. **[checked]**
4. **Anchor provenance**: every anchor in the dossier must be copied from a chapter packet
   (`packets/*.md`). Exceptions: (a) §3 structure-table auto-anchors `[chNN ¶1]`,
   (b) §13 external citations. New cross-chapter synthesis claims must cite ≥2
   packet-derived anchors from the chapters they span. **[checked]**
5. **No fabricated anchors**: every anchor must resolve against `book.json` / `text/`.
   **[checked: ≥98% resolve, zero nonexistent chapter ids]**
6. **Source discipline**: the extracted text is the only source for §0–§12 and §14–§15.
   Outside knowledge is allowed ONLY in §13. Never copy long passages; verbatim quotes
   are ≤ 12 words and live inside anchors.

### Style (retained from v1, still binding)

Dense, precise, readable. No generic praise, no motivational fluff, no filler transitions.
Preserve nuance and distinctions; explain relationships between ideas. Plain language
without oversimplifying. Be blunt where fidelity is limited. Do not beautify weak evidence.
Do not flatten contradictions. Keep faithful reconstruction separate from external critique.
Never shorten later sections because earlier sections were long.

## Anchor grammar

Canonical inline form: `[ch03 ¶45]`

```
anchor   = "[" ref *( "; " ref ) "]"
ref      = chap " " para [ " " sect ] [ " " quote ]
chap     = ("ch" | "fm" | "bm") 2DIGIT          ; chapter id from book.json
para     = "¶" idx [ ("–"|"-") idx ]            ; 1-based ¶ index; range span ≤ 8
sect     = "§" DQUOTE heading DQUOTE            ; verbatim heading from book.json
quote    = DQUOTE fragment DQUOTE               ; ≤ 12 words, verbatim from cited ¶
```

- ASCII alias `p45` for `¶45` is accepted and normalized at verify time.
- Multiple refs: `[ch03 ¶45; ch07 ¶12]` or adjacent brackets `[ch03 ¶45][ch07 ¶12]`.
- Validation **[checked]**: chapter id exists; ¶ ≤ paragraph count; range start ≤ end,
  span ≤ 8; `§"…"` must match a recorded heading (case/whitespace-insensitive); quote
  fragments must match the cited paragraph(s) after normalization (lowercase, straight
  quotes/dashes, collapsed whitespace) — exact within cited ¶, fuzzy within ±1 ¶.
- **Quote-bearing anchors are required** in: packet Evidence items, §7 ledger rows, and
  §14 recall answers that hinge on exact terminology. **Discouraged** in flowing prose
  (use plain `[chNN ¶k]` there).

Example prose:

> Because stocks change only through their flows, delays between action and visible
> result are structural, not accidental [ch01 ¶38–41].

> The chapter pivots at the section on bounded rationality, where the argument shifts
> from describing feedback to indicting market omniscience [ch04 ¶55 §"Bounded Rationality"].

## Section contract

Floors are checker-enforced; ceilings are guidance. "Anchor min" counts valid anchors.

| § | Heading (exact H2 text after `## `) | Words floor–ceiling | Anchor min |
|---|---|---|---|
| 0 | `0. Source Note And Confidence` | 150–400 + YAML block | 0 |
| 1 | `1. One-Page Orientation` | 300–600 | 0 |
| 2 | `2. What This Book Is Trying To Do` | 600–1000 | 3 |
| 3 | `3. Structural Architecture` | 1500–2500 | 1/chapter row |
| 4 | `4. Full Terminology And Concept System` | 3000–5000 | 1/entry |
| 5 | `5. Chapter-By-Chapter Reader Guide` | F(N)/chapter (below) | 3/chapter |
| 6 | `6. Main Argument Chain` | 1000–1800 | 1/step |
| 7 | `7. Evidence Ledger` | 1500–2500 | 1/row (quoted) |
| 8 | `8. Narrative, Worldview, And Persuasive Strategy` | 1000–1800 | 5 |
| 9 | `9. Load-Bearing Versus Secondary` | 400–800 | 1/indispensable item |
| 10 | `10. What Readers Usually Misunderstand` | 400–800 | 1/correction |
| 11 | `11. Practical Meaning` | 700–1200 | 4 |
| 12 | `12. Internal Tensions And Limits` | 500–1000 | 2/tension |
| 13 | `13. External Evaluation And Updates` | 400–1500 | 0 (external) |
| 14 | `14. Memory And Recall` | 1200–2000 | 1/idea + 1/answer |
| 15 | `15. What This Dossier Cannot Fully Replace` | 200–400 | 0 |
| 16 | `16. Coverage Audit And Verification` | machine blocks | n/a |

### §0 Source Note And Confidence

Prose (full book or excerpt? extraction quality? missing sections? how limitations affect
confidence) plus a fenced YAML block **[checked: parses, sha/counts match book.json]**:

```yaml
source:
  extraction: ebooklib        # or stdlib-fallback
  book_sha256_12: 9f3ac21b0d4e
  chapters: 17
  paragraphs: 1123
  ocr_quality: clean          # clean | minor | degraded
  structure: toc              # toc | inferred
```

### §3 Structural Architecture

Prose on parts/blocks/accumulation PLUS a mandatory structure table — one row per
`analyze: true` chapter **[checked: every such chapter id appears exactly once]**:

`| Chapter | Part/Block | Contribution | Anchor |` — anchor is the chapter opener `[chNN ¶1]`.

### §4 Full Terminology And Concept System

Every important term/concept/distinction/framework/model/metaphor. Standardized entry
**[checked: entry count ≥ max(15, chapter_count); each entry has 6 fields; Example anchored]**:

```
**Term** (introduced [chNN ¶k])
- Definition: …
- Intended meaning: …
- Role in system: …
- Adjacent concepts: …
- Example: … [chNN ¶k]
- Misunderstanding to avoid: …
```

### §5 Chapter-By-Chapter Reader Guide

One H3 entry per `analyze: true` chapter, in book order **[checked]**:

```
### Chapter {N} — {Title}
_Covers [chNN ¶1–{last}]_
```

(For unnumbered chapters — introduction, conclusion — use `### {Title}` but keep the
`_Covers …_` line; the checker maps entries to chapters via that anchor.)

Required labeled fields per entry: **Thesis** (anchored), **Why it matters**, **What it
adds**, **Core concepts**, **Key evidence** (each item anchored), **Retain**.

Per-chapter word floor **[checked]**: `F(N) = 350` if chapter_count ≤ 22, else
`max(150, floor(7700 / N))`. Applies identically to chapter 1 and chapter N.
**Back-half decay check [checked]**: mean words of the last ⌈N/4⌉ entries ≥ 0.70 × mean
of the first ⌈N/4⌉ entries.

### §6 Main Argument Chain

Steps carry IDs and every step line carries ≥1 anchor **[checked by regex on lines
starting `A|P|M|I|C + digit + .`]**:

- `A1., A2., …` starting assumptions
- `P1., …` premises
- `M1., …` mechanisms
- `I1., …` intermediate claims
- `C1., …` final conclusions

Multi-chapter steps cite ≥2 anchors. Then prose on implications.

### §7 Evidence Ledger

Mandatory table + interpretive prose. Columns **[checked: parse, enums, row count ≥
max(12, 1 per chapter), every row quote-bearing]**:

`| # | Claim it supports | Evidence item | Type | Anchor | Quote (≤12w) | Weight | Caveat |`

Type ∈ {study, data, case, story, thought-experiment, authority, analogy}.
Weight ∈ {foundational, illustrative, rhetorical, transitional}.
The ≥1-row-per-chapter minimum forces middle-chapter evidence in.

### §9 Load-Bearing Versus Secondary

Four labeled lists: **Indispensable** (each item anchored), **Supporting**,
**Memorable but secondary**, **Sounds important but isn't structurally central**.

### §10 What Readers Usually Misunderstand

≥5 pairs **[checked]**: `**Misreading:** … **Correction:** … [anchor]`

### §12 Internal Tensions And Limits

Only from the book itself. ≥3 items; each cites the two (or more) passages in tension —
≥2 anchors per item **[checked]**. Every item must trace to ≥1 packet Tension field.

### §13 External Evaluation And Updates

Clearly labeled outside-the-book. External citations as markdown links or
`[ext: Author Year, source]`. Book anchors allowed only for "what the author claimed"
clauses. **[checked: either ≥3 external citations OR the literal sentence
"External research was not performed."]**

### §14 Memory And Recall

1. **20 must-remember ideas** — each ends with ≥1 anchor. Drawn from packet Retain
   fields (one per chapter guaranteed) plus synthesis.
2. **15 compressed memory hooks** — anchors optional.
3. **Recall question bank** — N = chapter_count + 8 questions, minimum 20:
   one per chapter (verbatim from packet Recall fields) + ≥8 synthesis questions
   spanning ≥2 chapters (anchored to both). Machine format **[checked]**:
   `**Q07** (recall|application|synthesis; ch04, ch07) — question text`
   then `**A** — 2–5 sentence answer [anchor(s)]`.
4. **Self-test protocol** (fixed block): sessions day 0 / 3 / 10 / 30. Per question:
   produce an answer BEFORE revealing → self-grade 0/1/2 → for 0/1, reread the anchored
   source paragraphs and the referenced dossier section, then explain in one sentence
   WHY the answer is true → re-queue 0/1 items into the next session.

The bank is exported 1:1 to `recall.md` **[checked: identical question IDs and text]**.

### §16 Coverage Audit And Verification

Three blocks; do not hand-edit the first:

1. Deterministic block, injected by the checker between
   `<!-- verification:begin -->` / `<!-- verification:end -->` (fenced YAML; raw copy in
   `verification.json`).
2. Agent-audit block: 20 sampled claims (seeded sample from `booker.py verify`),
   verdict supported/partial/unsupported each with anchor and one-line note, plus
   self-rated confidence (1–10) for structure/concepts/terminology/evidence/chapters/
   practical fidelity — explicitly labeled self-rated.
3. Prose: completeness statement, known gaps, what a reader should double-check.

## Composition rules (packets → dossier)

Whole-book text never enters a single prompt. Packets are the compression layer.

| Packet field | Feeds |
|---|---|
| Purpose, Links | §3, §5 |
| Central Question, Thesis | §5; §6 steps |
| Claims (C*) | §5, §6, §7 claim column |
| Concepts | §4 (deduped union, first-introduction recorded), §5 |
| Evidence (E*) | §7 rows (anchor + quote copied verbatim), §5 key evidence |
| Reader Assumptions | §2, §8 |
| Foundational vs Illustrative | §7 Weight, §9 |
| Retain | §5 Retain, §14 ideas |
| Tension | §12, §10 |
| Recall (Q/A) | §14 bank → recall.md |

Procedure:

1. **§5 first**, one packet per compose step, in chapter order.
2. **Cross-chapter sections** (§2–§4, §6–§12, §14) are built from field slices of all
   packets (concepts-only, evidence-only, …), never from raw book text.
3. **Each section is its own compose step** (fresh context where possible).
4. **Repair is additive**: a section under floor gets targeted expansion; trimming
   earlier sections to rebalance is prohibited.

## Verification score and badge

```
score = 100 × ( 0.35 × anchor_validity_rate
              + 0.25 × claim_support          # (supported + 0.5×partial) / 20
              + 0.20 × coverage               # packets ∧ §5 chapters fraction
              + 0.10 × quote_match_rate
              + 0.10 × completeness )         # sections meeting floor / 17
```

Hard gates (all must hold for PASS): anchors ≥98% resolve with 0 nonexistent chapter
ids and 0 provenance violations; claim support ≥ 0.90 (≥18/20 effective) with 0
unsupported §6 steps; 100% chapter coverage (packets and §5); quote match ≥ 90%;
17/17 sections present with ≥15/17 floors met (§4, §5, §6, §7 floors mandatory);
§5 back-half ratio ≥ 0.70.

Badge: **VERIFIED** = all gates AND score ≥ 90 · **VERIFIED-WITH-WARNINGS** = all hard
gates, score 75–89 or ≤2 soft-floor misses · **FAILED** = any hard gate missed →
targeted repair pass, re-verify.
