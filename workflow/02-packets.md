# Workflow 02 — Chapter Packets (stage 2)

**Kind**: agent step (judgment) — the context-limit workhorse. **One chapter per step.**

## Purpose
Produce one analysis packet per analyzable chapter. Packets are the ONLY compression
layer between the book text and the dossier: every anchor in the final dossier is copied
from a packet. Quality here is quality everywhere.

## The loop
1. ```
   python3 booker.py status <slug>
   ```
   Read the pending packet list from the stage-2 line.
2. Pick ONE pending chapter id.
3. Read that chapter's text — nothing else:
   ```
   python3 booker.py chapter <slug> <chid>
   ```
   (equivalently, read `books/<slug>/text/<chid>.md`). If the chapter is grouped, read
   each member's text file.
4. Read `format/packet-schema-v2.md` (once per session is enough) and write
   `books/<slug>/packets/<chid>.md` following it exactly:
   - 12 H2 headings in order; frontmatter matching `book.json`.
   - 3–7 claims `C1..`, each line ending with a `[<chid> ¶n]` anchor.
   - ≥2 evidence items `E1..`, each with a verbatim quote fragment (≤12 words) inside
     the anchor and `supports C<n>`.
   - ≥1 recall Q/A with an anchored answer.
   - Anchors cite THIS chapter only (or group members). ¶ numbers come from the `[¶n]`
     markers in the text file — never guess them.
5. Check it:
   ```
   python3 booker.py check <slug> --stage 2 --packet <chid>
   ```
   Fix every reported problem until it exits 0.
6. Go to 1. Stop whenever you like — stopping between packets is always safe; any agent
   can resume from `status`.

## Rules
- **One chapter per step.** Never read multiple chapters into one context to "save time";
  that reintroduces the middle-of-book blind spot this design exists to prevent.
- Oversize chapters (`oversize: true` in book.json, > 8k words): read and analyze in two
  halves by ¶ range, then write ONE packet covering the whole chapter.
- Reconstruct ideas in your own words. Verbatim text appears only inside quote fragments.
- Do not use outside knowledge about the book. The text file is the only source.
- Never invent an anchor. If you cannot find a ¶ for a claim, the claim does not go in.

## Definition of done (whole stage)
```
python3 booker.py check <slug> --stage 2
```
exits 0 (all packets pass).
