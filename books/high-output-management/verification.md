# Verification Report — High Output Management (Andrew S. Grove)

- **Dossier hash**: `cadcfdf7b67d` (first 12 of final `dossier_sha256` in `verification.json`)
- **Result**: PASS — score **99.4**, badge **VERIFIED**
- **Claim support**: 0.975 (19 supported + 1 partial, 0 unsupported, over the 20-claim seeded sample)
- **Auditor**: claude-fable-5, fresh context, adversarial (did not compose the dossier; judged each claim only against the anchored paragraphs ±2 in `text/`)
- **Deterministic checks**: 1199/1199 anchors valid, 65/65 quotes matched (63 exact, 2 fuzzy), 19/19 chapter coverage, 17/17 section floors, recall parity ok.

Note: the audit was run twice. A first 20-claim sample (dossier sha `0a7a8aa2bda3`) was audited in full — 17 supported, 3 partial, 0 unsupported. Rewriting the §16 prose then re-derived the sample (sha `e7eb06a8b799`), and the fresh 20-claim sample below was audited from scratch; 7 claims carried over between samples and kept their verdicts.

## Audit table (final sample)

| Claim | Verdict | Note |
|---|---|---|
| S6:C3 | supported | ¶43 "a business with one employee: yourself"; ¶46 "You own it as a sole proprietor" — verbatim. |
| S5:ch02 | supported | ¶4-6 best-run company, self-made, personally written; ¶11 the three aspects of genius as claimed. |
| S5:ch03 | supported | ¶20 similar flow of activity; ¶10 build backward from limiting step, offset; ¶34 fix at lowest-value stage. |
| S7:row06 | **partial** | Example exact (¶43 Intel stagger chart of re-forecast orders), but the "leading indicators… in time for corrective action" framing lives in ¶38-40, outside the ¶43±2 window. |
| S6:C1 | supported | ch05 ¶81-84 leverage equation and activity mix; ch18 ¶9 and ch15 ¶11 cast training and appraisal in the same leverage calculus. |
| S5:ch06 | supported | ¶4 near-verbatim: both managerial tasks occur only face-to-face; meeting is the medium of managerial work. |
| S6:M4 | supported | ch07 ¶4-6 knowledge/position power divergence; ¶8-11 free discussion, clear decision, full support; ¶13 lowest competent level; ¶29-30 the six questions verbatim. |
| S7:row15 | supported | ¶41-42 exact: Columbus hit every key result, missed the objective, still performed well; MBO not a legal document. |
| S7:row16 | supported | ¶7 regional egg purchasing centers; ¶6-9 settle each activity on its own terms. |
| S5:ch10 | supported | ¶19 Grove's Law verbatim; ¶8 responsiveness-vs-leverage; ¶25-27 central allocators rejected, middle managers named. |
| S5:ch11 | supported | ¶10 dual reporting as the solution; ¶11 peer group as functional supervisor; ¶15-16 ambiguous, nothing simpler works. |
| S7:row21 | supported | ¶12 exact: engineering work "by the bit" cannot be priced by the free market. |
| S7:row24 | supported | ¶32-33 exact: ring-toss experiment; gamblers, conservatives, achievers testing their limits. |
| S6:I6 | supported | ¶6 TRM defined; ¶9 styles by TRM plus monitoring; ¶10 no value judgment; ¶26 raising TRM = leverage, high-TRM style takes least time. |
| S6:I7 | supported | ch15 ¶11-12 review as most important task-relevant feedback, purpose = improve performance; ch17 ¶6, ¶13-15 bonuses, merit curves, promotion on performance; ch16 ¶7, ¶30-31 interviewing and the quit conversation. |
| S7:row29 | supported | ¶27 exact: the most thoroughly interviewed hire was "a disaster" from day one. |
| S7:row31 | supported | ¶14 exact: last place in a footrace accepted; workplace ranking highly charged. |
| S5:ch18 | supported | ¶5 costs of undertrained employees; ¶7-9 the two levers, highest leverage; ¶12-14 process not event, practicing authority as role model. |
| S7:row34 | supported | ¶2-3 exact: 100 points' worth of honestly performed assignments makes "a distinctly better manager." |
| S7:row02 | supported | ¶31-32 exact: Intel's four 25% quarters; "all our employees 'produce' in some sense." |

## What a reader should still double-check

1. **Anchor-window drift on synthesis sentences.** The one partial (S7:row06) and the three partials in the first-round sample (S5:ch01, S6:I5, and row06 again) all had the same shape: the substance is genuinely in the book, but a clause draws on paragraphs 1-3 beyond the cited ±2 window (e.g. "leading indicators / corrective action" at ch04 ¶38-40; "manager as coach" at ch13 ¶54; the production-leverage-peak triad at ch01 ¶31-34/¶53). If you follow an anchor and don't find a specific clause, read a page around it before concluding the dossier invented it.
2. **Sample coverage.** 20 of ~1,200 anchored claims (~1.7%) were audited across two samples (33 distinct claims total). Unsampled claims are warranted by the mechanical anchor/quote checks plus process, not individual human inspection.
3. **Interpretive sections.** §10 (tensions), §11 (misreadings), and §14 (synthesis) are the dossier's own constructions argued from anchored evidence; Grove does not state them as such.
4. **Numbers quoted from a 1983/1995 text.** Figures like the 30-50% work-simplification reduction, the 2-4% classroom-time share, or the criminal-justice cost arithmetic are Grove's period claims, reproduced faithfully — not independently verified facts about today.
