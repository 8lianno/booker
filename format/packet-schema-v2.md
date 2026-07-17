# Chapter Packet Schema v2

One file per `analyze: true` chapter: `books/<slug>/packets/<chid>.md` (e.g. `packets/ch03.md`).
Write each packet in a FRESH context reading only `text/<chid>.md` (plus `skeleton.json` for
titles/grouping). Never read the whole book. This file is the binding contract; the checker
(`python3 booker.py check <slug> --stage 2 --packet <chid>`) enforces every rule.

## Hard rules

1. All anchors in a packet reference **this packet's own chapter** and fall within its
   paragraph range. Cross-chapter observations go under `## Links` as plain text.
2. 3–7 claims, IDs `C1..C7`; **every claim line ends with ≥1 anchor**.
3. ≥2 evidence items, IDs `E1..`; each has a **quote-bearing anchor** (verbatim fragment
   ≤ 12 words from the cited paragraph) and names the claim it supports (`supports C2`).
4. ≥1 recall question with an anchored answer.
5. All 12 H2 headings present, in order, exactly as spelled below.
6. Frontmatter parses and matches `book.json` (id, paragraph count).
7. Grouped micro-chapters (skeleton `group`): one packet file named after the first id,
   frontmatter lists all member ids, anchors may reference any member id.

## Template

```markdown
---
packet_version: 2
book_slug: <slug>
chapter:
  id: ch03
  number: 3
  title: "Managerial Leverage"
  para_count: 118
  para_range: [1, 118]
status: complete        # draft | complete
---

## Purpose
What this chapter does for the whole book; what later chapters presuppose from it.

## Central Question
The single question the chapter answers.

## Thesis
One- or two-sentence chapter thesis [ch03 ¶6–9].

## Claims
- C1. First key claim, stated precisely [ch03 ¶12].
- C2. Second key claim [ch03 ¶38–41].
- C3. Third key claim [ch03 ¶52 §"Section Heading"].

## Concepts
- term one — introduced — [ch03 ¶31]
- term two — refined (first seen ch01) — [ch03 ¶33]

## Evidence
- E1. Name/short label — type — supports C1 — one-line description of what happens and
  what it proves [ch03 ¶3 "verbatim fragment of twelve words or fewer"] — caveat: … .
- E2. … — type — supports C2 — … [ch03 ¶39 "another short verbatim fragment"] — caveat: none stated.

(type ∈ study | data | case | story | thought-experiment | authority | analogy)

## Reader Assumptions
What the author assumes the reader believes or knows coming in.

## Foundational Vs Illustrative
Foundational: … . Illustrative: … .

## Links
prev: how this builds on the previous chapter. next: what it sets up.

## Retain
The one thing a careful reader must retain from this chapter.

## Tension
Ambiguity, overreach, unresolved tension, or weak spot — from the text itself [ch03 ¶68].

## Recall
- Q: A question whose answer requires understanding, not pattern matching.
  A: 2–5 sentence answer with anchor [ch03 ¶40]. (difficulty: recall | application)
```

## Definition of done (script-checked)

Frontmatter parses; 12 H2 headings in order; claims 3–7 with anchors; ≥2 quote-bearing
evidence items each naming an existing claim; ≥1 recall Q/A with anchored answer;
≥6 valid anchors total; all anchors in-range for this chapter; `status: complete`.
