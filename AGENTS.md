# booker — agent instructions

booker turns an EPUB into a **verified analytical dossier**: a 16-section, ~16–22k-word
reader-equivalent digest with machine-validated source anchors, a claim audit, a recall
quiz, and HTML/PDF output — plus a library index across all finished books.

This repo is agent-CLI-agnostic (Claude Code, Codex, Kimi Code, GLM, …). All pipeline
state lives on disk under `books/<slug>/`; there is nothing to remember between
sessions. Any agent resumes any book by running `status` and doing exactly the NEXT
action.

## Quickstart — produce one full book

```
1. python3 booker.py new --title "high output management"
2. python3 booker.py status <slug>        # repeat after EVERY step
3. Follow the workflow file named in NEXT until status shows all stages complete.
```

## The pipeline (7 stages, state-machine on disk)

| Stage | What | Who | Workflow file |
|---|---|---|---|
| 0 | extract EPUB → `book.json` + numbered-¶ `text/` | script | `workflow/00-init.md` |
| 1 | classify chapters → `skeleton.json` | agent | `workflow/01-skeleton.md` |
| 2 | one analysis packet per chapter → `packets/` | agent | `workflow/02-packets.md` |
| 3 | compose 16-section `dossier.md` + `recall.md` | agent | `workflow/03-compose.md` |
| 4 | deterministic checks + claim audit → PASS badge | both | `workflow/04-verify.md` |
| 5 | render HTML/PDF/EPUB | script | `workflow/05-publish.md` |
| 6 | update library `catalog.json` / `index.html` | script | `workflow/05-publish.md` |

Every step's definition-of-done is a literal command:
`python3 booker.py check <slug> [--stage N] [--packet chNN]` (exit 0 = done).

## Hard rules (all agents, all stages)

1. **Never invent an anchor.** Anchors like `[ch03 ¶45]` must come from the `[¶n]`
   markers in `books/<slug>/text/<chid>.md`. The verifier resolves every one.
2. **Never read `source/book.epub` directly.** `book.json` + `text/` are the source of
   truth after stage 0.
3. **One packet per step** in stage 2. Do not batch chapters into one context.
4. **The dossier is composed from packets**, never from raw book text.
5. Stopping mid-pipeline is always safe. Do not track progress anywhere except the
   files themselves — `status` recomputes everything from disk.
6. Word floors are repaired by expanding the failing section, never by trimming others.

## Repo map

```
booker.py            CLI: new · resolve · status · list · check · chapter · verify · render · index
scripts/             implementation (structure, verify, resolve, stages, indexer, render, extract)
format/              binding output contracts: dossier-format-v2.md, packet-schema-v2.md, sections-v2.json
workflow/            the 6 step-by-step instruction files above
books/<slug>/        all per-book state (see workflow files for exact filenames)
catalog.json, index.html   generated library index — never hand-edit
```

## Environment notes

- Default `python3` is 3.9 — everything works there (stdlib fallbacks). If ebooklib is
  missing, stage-0 extraction falls back to a stdlib parser and marks
  `structure=inferred`.
- The user's Calibre library (`--title` resolution) is at `/Users/ali/Calibre Library`
  (override with `BOOKER_LIBRARY`).
