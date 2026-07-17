#!/usr/bin/env python3
"""Stage definitions and deterministic completion gates for the booker pipeline.

Every gate is pure file inspection — no model judgment. Contract:

    check_stage(slug, n)      -> (ok: bool, messages: list[str])
    stage_status(slug)        -> dict (see below)

stage_status(slug) returns:
    {
      "slug": ..., "stages": [{"n": 0, "name": ..., "complete": bool, "detail": str}],
      "current": <first incomplete stage n, or 7 if all complete>,
      "next": "<one-line NEXT action for any agent CLI>"
    }
"""

from __future__ import annotations

import re
from pathlib import Path

import util

STAGE_NAMES = {
    0: "init/extract",
    1: "skeleton",
    2: "packets",
    3: "compose",
    4: "verify",
    5: "render",
    6: "index",
}

NEXT_HINTS = {
    0: "script step — run: python3 booker.py new … (see workflow/00-init.md)",
    1: "agent step — open workflow/01-skeleton.md; write skeleton.json",
    2: "agent step — open workflow/02-packets.md; pending: {pending}",
    3: "agent step — open workflow/03-compose.md; write dossier.md section by section",
    4: "run: python3 booker.py verify {slug}; then workflow/04-verify.md",
    5: "run: python3 booker.py render {slug}  (workflow/05-publish.md)",
    6: "run: python3 booker.py index  (workflow/05-publish.md)",
}


# ---------------------------------------------------------------- helpers

def _bd(slug):
    return util.book_dir(slug)


def analyzable_chapters(skeleton):
    """Chapter entries that need their own packet: analyze==true and not a
    member of a group headed by another id."""
    out = []
    for entry in skeleton.get("chapters", []):
        if not entry.get("analyze"):
            continue
        group = entry.get("group")
        if group and group != entry["id"]:
            continue  # member; covered by the group head's packet
        out.append(entry)
    return out


def pending_packets(slug):
    bd = _bd(slug)
    try:
        skeleton = util.load_json(bd / "skeleton.json")
    except Exception:
        return []
    pending = []
    import verify
    for entry in analyzable_chapters(skeleton):
        ok, _ = verify.check_packet(bd, entry["id"])
        if not ok:
            pending.append(entry["id"])
    return pending


# ---------------------------------------------------------------- gates

def check_stage0(slug):
    bd = _bd(slug)
    msgs = []
    for name in ("meta.json", "book.json"):
        if not (bd / name).exists():
            return False, ["missing %s" % name]
    try:
        meta = util.load_json(bd / "meta.json")
        book = util.load_json(bd / "book.json")
    except Exception as e:
        return False, ["unparseable meta/book json: %s" % e]

    chapters = book.get("chapters", [])
    real = [c for c in chapters if c.get("kind") == "chapter"]
    if not real:
        msgs.append("no chapters of kind 'chapter' in book.json")
    words = book.get("stats", {}).get("words", 0)
    if words <= 10000:
        msgs.append("total words %s <= 10000 — extraction looks broken (DRM/garbage gate)" % words)
    for c in chapters:
        tf = bd / "text" / ("%s.md" % c["id"])
        if not tf.exists():
            msgs.append("missing text/%s.md" % c["id"])
            continue
        n_markers = len(re.findall(r"^\[¶\d+\]", tf.read_text(encoding="utf-8"), re.M))
        if n_markers != c.get("paragraphs"):
            msgs.append("text/%s.md has %d ¶ markers, book.json says %s"
                        % (c["id"], n_markers, c.get("paragraphs")))
    if not meta.get("book_json_sha256"):
        msgs.append("meta.json missing book_json_sha256")
    return (not msgs), msgs


def check_stage1(slug):
    bd = _bd(slug)
    if not (bd / "skeleton.json").exists():
        return False, ["missing skeleton.json"]
    try:
        skeleton = util.load_json(bd / "skeleton.json")
        meta = util.load_json(bd / "meta.json")
        book = util.load_json(bd / "book.json")
    except Exception as e:
        return False, ["unparseable json: %s" % e]

    msgs = []
    want_sha = util.sha12(meta.get("book_json_sha256", ""))
    got_sha = skeleton.get("book_json_sha256_12", "")
    if want_sha and got_sha != want_sha:
        msgs.append("skeleton book_json_sha256_12 %r != current %r (stale skeleton — re-run stage 1)"
                    % (got_sha, want_sha))

    book_ids = [c["id"] for c in book.get("chapters", [])]
    skel_ids = [c.get("id") for c in skeleton.get("chapters", [])]
    if sorted(book_ids) != sorted(skel_ids):
        missing = set(book_ids) - set(skel_ids)
        extra = set(skel_ids) - set(book_ids)
        if missing:
            msgs.append("skeleton missing chapter ids: %s" % ", ".join(sorted(missing)))
        if extra:
            msgs.append("skeleton has unknown chapter ids: %s" % ", ".join(sorted(extra)))
    if len(skel_ids) != len(set(skel_ids)):
        msgs.append("duplicate chapter ids in skeleton")

    for entry in skeleton.get("chapters", []):
        if "analyze" not in entry:
            msgs.append("%s: missing analyze true/false" % entry.get("id"))
        group = entry.get("group")
        if group and group not in skel_ids:
            msgs.append("%s: group head %r not a chapter id" % (entry.get("id"), group))
        if group and group != entry.get("id"):
            heads = [c for c in skeleton["chapters"] if c.get("id") == group]
            if heads and not heads[0].get("analyze"):
                msgs.append("%s: group head %s is not analyze:true" % (entry.get("id"), group))

    n_analyze = len([c for c in skeleton.get("chapters", []) if c.get("analyze")])
    if n_analyze < 3:
        msgs.append("only %d chapters marked analyze:true (need >= 3)" % n_analyze)
    return (not msgs), msgs


def check_stage2(slug, packet=None):
    bd = _bd(slug)
    ok1, msgs1 = check_stage1(slug)
    if not ok1:
        return False, ["stage 1 incomplete"] + msgs1
    skeleton = util.load_json(bd / "skeleton.json")
    import verify
    msgs = []
    targets = analyzable_chapters(skeleton)
    if packet:
        targets = [c for c in targets if c["id"] == packet]
        if not targets:
            return False, ["%s is not an analyzable chapter (check skeleton.json)" % packet]
    for entry in targets:
        ok, pm = verify.check_packet(bd, entry["id"])
        if not ok:
            msgs.append("packet %s: %s" % (entry["id"], "; ".join(pm)))
    return (not msgs), msgs


def check_stage3(slug):
    bd = _bd(slug)
    if not (bd / "dossier.md").exists():
        return False, ["missing dossier.md"]
    import verify
    return verify.light_check_dossier(bd)


def check_stage4(slug):
    bd = _bd(slug)
    msgs = []
    vpath = bd / "verification.json"
    if not vpath.exists():
        return False, ["missing verification.json — run: python3 booker.py verify %s" % slug]
    try:
        v = util.load_json(vpath)
    except Exception as e:
        return False, ["unparseable verification.json: %s" % e]
    if not v.get("pass"):
        msgs.append("verification.json pass=false — repair failures and re-run verify")
    cur = util.sha256_text((bd / "dossier.md").read_text(encoding="utf-8")) if (bd / "dossier.md").exists() else ""
    if v.get("dossier_sha256") != cur:
        msgs.append("verification is stale (dossier.md changed since verify) — re-run verify")
    vmd = bd / "verification.md"
    if not vmd.exists():
        msgs.append("missing verification.md (agent claim audit — workflow/04-verify.md)")
    elif util.sha12(cur) not in vmd.read_text(encoding="utf-8"):
        msgs.append("verification.md does not reference current dossier hash %s — stale audit"
                    % util.sha12(cur))
    return (not msgs), msgs


def check_stage5(slug):
    bd = _bd(slug)
    msgs = []
    if not (bd / "dossier.html").exists():
        return False, ["missing dossier.html — run: python3 booker.py render %s" % slug]
    try:
        meta = util.load_json(bd / "meta.json")
    except Exception as e:
        return False, ["unparseable meta.json: %s" % e]
    cur = util.sha256_text((bd / "dossier.md").read_text(encoding="utf-8"))
    if meta.get("render", {}).get("dossier_sha256") != cur:
        msgs.append("render is stale (dossier.md changed) — re-run render")
    return (not msgs), msgs


def check_stage6(slug):
    bd = _bd(slug)
    catalog_path = util.REPO_ROOT / "catalog.json"
    if not catalog_path.exists():
        return False, ["missing catalog.json — run: python3 booker.py index"]
    try:
        catalog = util.load_json(catalog_path)
    except Exception as e:
        return False, ["unparseable catalog.json: %s" % e]
    entry = next((b for b in catalog.get("books", []) if b.get("slug") == slug), None)
    if entry is None:
        return False, ["%s not in catalog.json — run: python3 booker.py index" % slug]
    cur = util.sha256_text((bd / "dossier.md").read_text(encoding="utf-8"))
    if entry.get("dossier_sha256") != cur:
        return False, ["catalog entry stale — re-run: python3 booker.py index"]
    return True, []


CHECKS = {
    0: check_stage0,
    1: check_stage1,
    2: check_stage2,
    3: check_stage3,
    4: check_stage4,
    5: check_stage5,
    6: check_stage6,
}


def check_stage(slug, n, packet=None):
    if n == 2:
        return check_stage2(slug, packet=packet)
    return CHECKS[n](slug)


def stage_status(slug):
    bd = _bd(slug)
    if not bd.exists():
        return {"slug": slug, "stages": [], "current": -1,
                "next": "unknown slug %r — run: python3 booker.py list" % slug}
    stages = []
    current = 7
    for n in range(7):
        ok, msgs = check_stage(slug, n)
        detail = "ok" if ok else (msgs[0] if msgs else "incomplete")
        if n == 2 and not ok:
            pend = pending_packets(slug)
            done = 0
            try:
                skeleton = util.load_json(bd / "skeleton.json")
                done = len(analyzable_chapters(skeleton)) - len(pend)
                detail = "%d/%d packets complete" % (done, done + len(pend))
            except Exception:
                pass
        stages.append({"n": n, "name": STAGE_NAMES[n], "complete": ok, "detail": detail})
        if not ok and current == 7:
            current = n
    if current == 7:
        nxt = "nothing — all 7 stages complete"
    else:
        hint = NEXT_HINTS[current]
        if current == 2:
            hint = hint.format(pending=", ".join(pending_packets(slug)) or "?")
        else:
            hint = hint.format(slug=slug)
        nxt = hint
    return {"slug": slug, "stages": stages, "current": current, "next": nxt}
