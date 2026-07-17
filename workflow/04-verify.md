# Workflow 04 — Verify (stage 4)

**Kind**: script + agent. The checker finds problems; you repair and then audit claims
against the source. Order matters — follow it exactly.

## Steps

### 4a. Deterministic pass + repair loop
1. ```
   python3 booker.py verify <slug>
   ```
2. Open `books/<slug>/verification.json`. Work through `failures` and `repair_list`:
   broken anchors, under-floor sections, missing table rows, recall mismatches.
   Repair rules:
   - Fix anchors by opening the cited chapter text (`python3 booker.py chapter <slug>
     <chid>`) and correcting the ¶ number or quote — never by deleting the claim unless
     it is actually unsupported.
   - Expand under-floor sections; never trim other sections to compensate.
3. Re-run `verify` until the only remaining blocker is `audit: pending`.

### 4b. Claim audit (fresh eyes)
The audit must be done against the SOURCE, not against your memory of composing.
If your CLI supports sub-agents or a fresh session, do this part there.

4. In `verification.json`, find `audit_sample` — 20 claims, each with id, section,
   text, anchor.
5. For each claim: read the anchored paragraph(s) ±2 in `text/<chid>.md`. Verdict:
   - `supported` — the passage states or directly entails the claim.
   - `partial` — related but the claim generalizes/sharpens beyond the passage.
   - `unsupported` — the passage does not back the claim.
6. Write `books/<slug>/audit.json`:
   ```json
   {
     "dossier_sha256": "<copy dossier_sha256_pre_injection from verification.json>",
     "auditor": "<your model/CLI name>, fresh context",
     "results": [
       {"id": "<claim id>", "verdict": "supported", "note": "one line"}
     ]
   }
   ```
7. If any verdict is `unsupported`: fix the dossier (correct the claim to what the text
   supports, or re-anchor it), then RESTART from step 1 — the sample re-derives from the
   changed text.
8. ```
   python3 booker.py verify <slug>
   ```
   folds the audit in. It must now print PASS with a score and badge.

### 4c. Audit report
9. Write `books/<slug>/verification.md` — a short human report: the 12-char dossier
   hash from `verification.json` (`dossier_sha256` first 12 chars — the gate greps for
   it), score/badge, the audit table (claim → verdict → note), anything a reader should
   double-check. Also rewrite the prose part of dossier §16 (outside the marker block)
   to state completeness honestly using the real numbers.

## Definition of done
```
python3 booker.py check <slug> --stage 4
```
exits 0.
