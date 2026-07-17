#!/usr/bin/env python3
"""Anchor grammar, packet checker, and dossier verifier (format v2).

Enforcement engine for format/dossier-format-v2.md and format/packet-schema-v2.md.
Every rule marked [checked] in those contracts is enforced here. Public contract
(used by booker.py and stages.py):

    check_packet(book_dir, chid)   -> (ok: bool, messages: list[str])
    light_check_dossier(book_dir)  -> (ok: bool, messages: list[str])   # stage 3 gate
    verify_dossier(book_dir)       -> dict  # stage 4a: writes verification.json,
                                            # injects the §16 machine block

Internal API reusable by other modules:

    parse_anchors(text)      -> list of {"raw","chap","start","end","sect","quote","pos"}
    validate_anchor(a, book) -> {"ok","reason","quote_status"}
    load_book(book_dir)      -> Book (lazy text/<chid>.md access)

Notes:
- `_Covers [chNN ¶…]_` lines in §5 are entry→chapter mapping devices, not
  citations; their anchors are excluded from validity/density/provenance stats.
- dossier_sha256 in verification.json is the sha of dossier.md AFTER block
  injection (what stages.check_stage4 compares). audit.json freshness compares
  the sha of the dossier WITHOUT the injected block, so re-injection never
  invalidates a fresh audit.
"""

from __future__ import annotations

import difflib
import math
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import util

CHECKER_VERSION = "2.0"

PACKET_H2 = ["Purpose", "Central Question", "Thesis", "Claims", "Concepts",
             "Evidence", "Reader Assumptions", "Foundational Vs Illustrative",
             "Links", "Retain", "Tension", "Recall"]

QUOTE_MAX_WORDS = 12
RANGE_SPAN_MAX = 8
FUZZY_RATIO_MIN = 0.80

_VERIF_BEGIN = "<!-- verification:begin -->"
_VERIF_END = "<!-- verification:end -->"
_VERIF_RE = re.compile(r"[ \t]*<!-- verification:begin -->.*?<!-- verification:end -->[ \t]*\n?",
                       re.S)


# ---------------------------------------------------------------- mini YAML

def _strip_comment(line):
    """Drop a trailing ' # …' comment that is not inside a quoted string."""
    out = []
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _yaml_scalar_in(token):
    token = token.strip()
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        return [_yaml_scalar_in(t) for t in inner.split(",")] if inner else []
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    low = token.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    if re.match(r"^-?\d+$", token):
        return int(token)
    if re.match(r"^-?\d+\.\d+$", token):
        return float(token)
    return token


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _mini_yaml_block(lines, i, indent):
    """Parse a same-indent run of lines as a dict or list. Returns (value, i)."""
    if lines[i].lstrip().startswith("- "):
        out = []
        while i < len(lines) and _indent_of(lines[i]) == indent \
                and lines[i].lstrip().startswith("- "):
            out.append(_yaml_scalar_in(lines[i].lstrip()[2:]))
            i += 1
        return out, i
    obj = {}
    while i < len(lines):
        ind = _indent_of(lines[i])
        if ind != indent:
            break
        m = re.match(r"([^\s:][^:]*):\s*(.*)$", lines[i].strip())
        if not m:
            raise ValueError("unparseable line: %r" % lines[i])
        key, val = m.group(1).strip(), m.group(2).strip()
        i += 1
        if val:
            obj[key] = _yaml_scalar_in(val)
        elif i < len(lines) and _indent_of(lines[i]) > indent:
            obj[key], i = _mini_yaml_block(lines, i, _indent_of(lines[i]))
        else:
            obj[key] = None
    return obj, i


def _mini_yaml(text):
    """Stdlib fallback parser for the restricted YAML shapes booker emits:
    nested maps by indentation, scalar values, inline [a, b] lists, '- ' lists."""
    lines = []
    for raw in text.splitlines():
        line = _strip_comment(raw.replace("\t", "  "))
        if line.strip():
            lines.append(line)
    if not lines:
        return {}
    value, _ = _mini_yaml_block(lines, 0, _indent_of(lines[0]))
    return value


def _yaml_load(text):
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(text)


# ---------------------------------------------------------------- book access

class Book:
    """book.json plus lazily-loaded text/<chid>.md paragraph lists."""

    def __init__(self, book_dir, data):
        self.dir = Path(book_dir)
        self.data = data
        self.chapters = {c["id"]: c for c in data.get("chapters", [])}
        self.chapter_ids = [c["id"] for c in data.get("chapters", [])]
        self._paras = {}

    def chapter(self, chid):
        return self.chapters.get(chid)

    def para_count(self, chid):
        c = self.chapters.get(chid) or {}
        n = c.get("paragraphs")
        return n if n is not None else len(self.paragraphs(chid))

    def paragraphs(self, chid):
        """Paragraph texts for one chapter; index 0 = ¶1."""
        if chid not in self._paras:
            paras = []
            path = self.dir / "text" / ("%s.md" % chid)
            if path.exists():
                txt = path.read_text(encoding="utf-8")
                marks = list(re.finditer(r"^\[¶(\d+)\][ \t]*", txt, re.M))
                for i, mk in enumerate(marks):
                    end = marks[i + 1].start() if i + 1 < len(marks) else len(txt)
                    paras.append(txt[mk.end():end].strip())
            self._paras[chid] = paras
        return self._paras[chid]

    def headings(self, chid):
        c = self.chapters.get(chid) or {}
        out = []
        for h in (c.get("headings") or []):
            out.append(h.get("text", "") if isinstance(h, dict) else str(h))
        return out


def load_book(book_dir):
    return Book(book_dir, util.load_json(Path(book_dir) / "book.json"))


# ---------------------------------------------------------------- anchor grammar

_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
_REF_RE = re.compile(
    r'^((?:ch|fm|bm)\d{2})\s+(?:¶|p)(\d+)(?:[–-](\d+))?'
    r'(?:\s+§["“]([^"“”]+)["”])?'
    r'(?:\s+["“]([^"“”]+)["”])?$'
)


def parse_anchors(text):
    """Find all source anchors in text. ASCII 'p45' is normalized to ¶45; a
    bracket may hold several refs joined by '; '. Non-anchor brackets (markdown
    links, [ext: …], inline lists) are ignored."""
    out = []
    for m in _BRACKET_RE.finditer(text):
        if text[m.end():m.end() + 1] == "(":
            continue  # markdown link
        parts = [p.strip() for p in m.group(1).split(";")]
        refs = []
        for part in parts:
            rm = _REF_RE.match(part)
            if not rm:
                refs = None
                break
            refs.append(rm)
        if not refs:
            continue
        for rm in refs:
            start = int(rm.group(2))
            end = int(rm.group(3)) if rm.group(3) else start
            out.append({"raw": rm.group(0), "chap": rm.group(1),
                        "start": start, "end": end,
                        "sect": rm.group(4), "quote": rm.group(5),
                        "pos": m.start()})
    return out


def _quote_status(fragment, book, chap, start, end):
    """exact | fuzzy | unmatched for a verbatim fragment vs the cited ¶(s)."""
    frag = util.normalize_for_match(fragment)
    if not frag:
        return "unmatched"
    paras = book.paragraphs(chap)
    cited = " ".join(util.normalize_for_match(p) for p in paras[start - 1:end])
    if frag in cited:
        return "exact"
    lo, hi = max(0, start - 2), min(len(paras), end + 1)
    window = " ".join(util.normalize_for_match(p) for p in paras[lo:hi])
    if frag in window:
        return "fuzzy"
    words = cited.split()
    span = len(frag.split())
    best = 0.0
    for i in range(0, max(1, len(words) - span + 1)):
        cand = " ".join(words[i:i + span])
        r = difflib.SequenceMatcher(None, frag, cand).ratio()
        if r > best:
            best = r
    return "fuzzy" if best >= FUZZY_RATIO_MIN else "unmatched"


def validate_anchor(a, book):
    """Validate one parsed anchor against the book. quote_status is set only
    for quote-bearing anchors that pass the structural checks."""
    def bad(reason):
        return {"ok": False, "reason": reason, "quote_status": None}

    chap = a["chap"]
    if chap not in book.chapter_ids:
        return bad("nonexistent chapter id %s" % chap)
    start, end = a["start"], a["end"]
    if start < 1:
        return bad("¶ index must be >= 1")
    if end < start:
        return bad("range start ¶%d > end ¶%d" % (start, end))
    if end - start + 1 > RANGE_SPAN_MAX:
        return bad("span too large (¶%d–%d covers %d ¶, max %d)"
                   % (start, end, end - start + 1, RANGE_SPAN_MAX))
    n = book.para_count(chap)
    if end > n:
        return bad("¶%d beyond %s paragraph count %d" % (end, chap, n))
    if a.get("sect"):
        want = util.normalize_for_match(a["sect"])
        have = [util.normalize_for_match(h) for h in book.headings(chap)]
        if want not in have:
            return bad("unknown heading §\"%s\" in %s" % (a["sect"], chap))
    res = {"ok": True, "reason": None, "quote_status": None}
    if a.get("quote"):
        if util.word_count(a["quote"]) > QUOTE_MAX_WORDS:
            return bad("quote fragment longer than %d words" % QUOTE_MAX_WORDS)
        res["quote_status"] = _quote_status(a["quote"], book, chap, start, end)
    return res


# ---------------------------------------------------------------- packet checker

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)\Z", re.S)


def _split_h2(body):
    """Split markdown into [(h2_heading, section_text), …]; text before the
    first H2 is dropped."""
    out = []
    matches = list(re.finditer(r"^## +(.+?)\s*$", body, re.M))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out.append((m.group(1).strip(), body[m.end():end]))
    return out


def _packet_members(book_dir, chid):
    """Chapter ids a packet may cite: the head plus any skeleton group members."""
    members = [chid]
    try:
        skeleton = util.load_json(Path(book_dir) / "skeleton.json")
    except Exception:
        return members
    for c in skeleton.get("chapters", []):
        if c.get("group") == chid and c.get("id") != chid:
            members.append(c["id"])
    return members


def check_packet(book_dir, chid):
    """Full definition-of-done check for packets/<chid>.md (packet-schema-v2)."""
    bd = Path(book_dir)
    if not (bd / "book.json").exists():
        return False, ["missing book.json"]
    try:
        book = load_book(bd)
    except Exception as e:
        return False, ["unparseable book.json: %s" % e]
    if chid not in book.chapter_ids:
        return False, ["unknown chapter id %s (not in book.json)" % chid]
    members = _packet_members(bd, chid)
    for mid in members:
        if not (bd / "text" / ("%s.md" % mid)).exists():
            return False, ["missing text/%s.md" % mid]
    ppath = bd / "packets" / ("%s.md" % chid)
    if not ppath.exists():
        return False, ["missing packets/%s.md" % chid]
    text = ppath.read_text(encoding="utf-8")

    msgs = []
    fm_m = _FRONTMATTER_RE.match(text)
    if not fm_m:
        return False, ["missing or unterminated YAML frontmatter"]
    try:
        fm = _yaml_load(fm_m.group(1)) or {}
    except Exception as e:
        return False, ["frontmatter does not parse: %s" % e]
    body = fm_m.group(2)

    # -- frontmatter fields
    ch = fm.get("chapter") or {}
    if ch.get("id") != chid:
        msgs.append("frontmatter chapter.id %r != %s" % (ch.get("id"), chid))
    head_pc = book.para_count(chid)
    group_pc = sum(book.para_count(m) for m in members)
    if ch.get("para_count") not in (head_pc, group_pc):
        msgs.append("frontmatter para_count %r != book.json paragraphs %d"
                    % (ch.get("para_count"), head_pc))
    if fm.get("status") != "complete":
        msgs.append("status is %r, need status: complete" % fm.get("status"))

    # -- 12 exact H2 headings, in order
    sections = _split_h2(body)
    found = [h for h, _ in sections]
    for h in PACKET_H2:
        if h not in found:
            msgs.append("missing H2 heading: ## %s" % h)
    seq = [h for h in found if h in PACKET_H2]
    want = [h for h in PACKET_H2 if h in seq]
    if seq != want:
        msgs.append("H2 headings out of order (found %s)" % " > ".join(seq))
    sec = dict((h, t) for h, t in sections)

    # -- every anchor: this chapter (or group member), in range, valid
    n_valid = 0
    for a in parse_anchors(body):
        v = validate_anchor(a, book)
        if not v["ok"]:
            msgs.append("invalid anchor [%s]: %s" % (a["raw"], v["reason"]))
        elif a["chap"] not in members:
            msgs.append("anchor [%s] cites %s — packet may only cite %s"
                        % (a["raw"], a["chap"], "/".join(members)))
        else:
            n_valid += 1
    if n_valid < 6:
        msgs.append("only %d valid anchors in packet (need >= 6)" % n_valid)

    # -- claims: 3–7 lines "- CN." each with >=1 valid anchor
    claim_ids = []
    for m in re.finditer(r"^\s*-\s*C(\d+)\.(.*)$", sec.get("Claims", ""), re.M):
        cid, line = int(m.group(1)), m.group(0)
        claim_ids.append(cid)
        ok_line = any(validate_anchor(a, book)["ok"] and a["chap"] in members
                      for a in parse_anchors(line))
        if not ok_line:
            msgs.append("claim C%d has no valid anchor" % cid)
    if not 3 <= len(claim_ids) <= 7:
        msgs.append("found %d claim lines (need 3–7 '- CN.' claims)" % len(claim_ids))

    # -- evidence: >=2 items, each quote-bearing (exact|fuzzy) + supports C<n>
    ev_body = sec.get("Evidence", "")
    starts = list(re.finditer(r"^\s*-\s*E(\d+)\.", ev_body, re.M))
    if len(starts) < 2:
        msgs.append("found %d evidence items (need >= 2 '- EN.' items)" % len(starts))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(ev_body)
        item = ev_body[m.start():end]
        eid = "E%s" % m.group(1)
        quoted_ok = False
        for a in parse_anchors(item):
            v = validate_anchor(a, book)
            if (v["ok"] and a["chap"] in members and a.get("quote")
                    and v["quote_status"] in ("exact", "fuzzy")):
                quoted_ok = True
        if not quoted_ok:
            msgs.append("%s: no quote-bearing valid anchor (verbatim fragment "
                        "<= 12 words matching the cited ¶, exact or fuzzy)" % eid)
        sm = re.search(r"supports\s+C(\d+)", item)
        if not sm:
            msgs.append("%s: missing 'supports C<n>'" % eid)
        elif int(sm.group(1)) not in claim_ids:
            msgs.append("%s: supports C%s which is not a claim id" % (eid, sm.group(1)))

    # -- recall: >=1 Q with an A containing >=1 valid anchor
    rc_body = sec.get("Recall", "")
    q_marks = list(re.finditer(r"^\s*-?\s*Q\s*:", rc_body, re.M))
    got_recall = False
    for i, m in enumerate(q_marks):
        end = q_marks[i + 1].start() if i + 1 < len(q_marks) else len(rc_body)
        item = rc_body[m.start():end]
        am = re.search(r"\bA\s*:", item)
        if not am:
            continue
        answer = item[am.end():]
        if any(validate_anchor(a, book)["ok"] and a["chap"] in members
               for a in parse_anchors(answer)):
            got_recall = True
    if not got_recall:
        msgs.append("no recall Q with an anchored A (need >= 1)")

    return (not msgs), msgs


# ---------------------------------------------------------------- dossier: shared

def _strip_verification_block(text):
    return _VERIF_RE.sub("", text)


def _canonical_pre_text(text):
    """Dossier text without the injected §16 machine block, newline-canonical.
    sha256 of this string is stable across repeated verify runs."""
    return _strip_verification_block(text).rstrip("\n") + "\n"


def _dossier_headings(cfg):
    return [s["heading"] for s in cfg["sections"]]


def _heading_order_msgs(found, expected):
    msgs = []
    for h in expected:
        if h not in found:
            msgs.append("missing section heading: ## %s" % h)
    seq = [h for h in found if h in expected]
    want = [h for h in expected if h in seq]
    if seq != want:
        msgs.append("section headings out of order")
    dupes = sorted(set(h for h in seq if seq.count(h) > 1))
    for h in dupes:
        msgs.append("duplicate section heading: ## %s" % h)
    return msgs


def light_check_dossier(book_dir):
    """Stage 3 gate: 17 H2 headings present in order + total word floor."""
    bd = Path(book_dir)
    path = bd / "dossier.md"
    if not path.exists():
        return False, ["missing dossier.md"]
    cfg = util.sections_config()
    text = _strip_verification_block(path.read_text(encoding="utf-8"))
    found = re.findall(r"^## +(.+?)\s*$", text, re.M)
    msgs = _heading_order_msgs(found, _dossier_headings(cfg))
    total = util.word_count(text)
    if total < cfg["total_words_min"]:
        msgs.append("total words %d < %d floor" % (total, cfg["total_words_min"]))
    return (not msgs), msgs


def _split_dossier_sections(text, cfg):
    """Map section id -> body text (unknown H2s stay inside the current
    section). Returns (bodies, found_headings_in_order)."""
    heading_to_id = dict((s["heading"], s["id"]) for s in cfg["sections"])
    bodies = {}
    found = []
    matches = list(re.finditer(r"^## +(.+?)\s*$", text, re.M))
    cur_id = None
    cur_start = None
    for m in matches:
        h = m.group(1).strip()
        if h not in heading_to_id:
            continue  # stray H2: treat as content of the current section
        if cur_id is not None:
            bodies[cur_id] = bodies.get(cur_id, "") + text[cur_start:m.start()]
        cur_id = heading_to_id[h]
        cur_start = m.end()
        found.append(h)
    if cur_id is not None:
        bodies[cur_id] = bodies.get(cur_id, "") + text[cur_start:]
    return bodies, found


_COVERS_LINE_RE = re.compile(r"^\s*_Covers\b.*$", re.M)
_COVERS_REF_RE = re.compile(r"_Covers\s*\[\s*((?:ch|fm|bm)\d{2})\b")


def _scan_anchors(body, skip_covers=False):
    """parse_anchors over a section body; optionally blank _Covers lines first."""
    if skip_covers:
        body = _COVERS_LINE_RE.sub("", body)
    return parse_anchors(body)


def _analyzable_heads(skeleton):
    """Analyzable chapter heads in book order (analyze:true, not a group member)."""
    heads = []
    for c in skeleton.get("chapters", []):
        if not c.get("analyze"):
            continue
        group = c.get("group")
        if group and group != c.get("id"):
            continue
        heads.append(c["id"])
    return heads


def _head_of_map(skeleton):
    """chapter id -> its packet head (itself unless a group member)."""
    out = {}
    for c in skeleton.get("chapters", []):
        cid = c.get("id")
        out[cid] = c.get("group") or cid
    return out


# ---------------------------------------------------------------- dossier: special checks

def _valid_anchors(body, book, skip_covers=False):
    out = []
    for a in _scan_anchors(body, skip_covers=skip_covers):
        if validate_anchor(a, book)["ok"]:
            out.append(a)
    return out


def _check_source_yaml(body, book, meta, failures):
    """§0: fenced YAML parses; sha + counts match book.json/meta.json."""
    m = re.search(r"```ya?ml[ \t]*\n(.*?)```", body, re.S)
    if not m:
        failures.append("§0: missing fenced ```yaml source block")
        return
    try:
        data = _yaml_load(m.group(1)) or {}
    except Exception as e:
        failures.append("§0: source YAML does not parse: %s" % e)
        return
    src = data.get("source", data) or {}
    want_sha = util.sha12(meta.get("book_json_sha256", "")) if meta else ""
    if want_sha and src.get("book_sha256_12") != want_sha:
        failures.append("§0: book_sha256_12 %r != %r from meta.json"
                        % (src.get("book_sha256_12"), want_sha))
    n_ch = len(book.chapter_ids)
    stats_ch = book.data.get("stats", {}).get("chapters")
    if src.get("chapters") not in (n_ch, stats_ch):
        failures.append("§0: chapters %r != book.json chapter count %d"
                        % (src.get("chapters"), n_ch))
    n_par = sum(book.para_count(c) for c in book.chapter_ids)
    stats_par = book.data.get("stats", {}).get("paragraphs")
    if src.get("paragraphs") not in (n_par, stats_par):
        failures.append("§0: paragraphs %r != book.json total %d"
                        % (src.get("paragraphs"), n_par))


def _table_rows(body):
    """Markdown table rows in a section body: (header_cells, [row_cells…])."""
    rows = []
    header = None
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue  # separator
        if header is None:
            header = cells
        else:
            rows.append(cells)
    return header, rows


def _check_structure_table(body, book, heads, head_of, failures):
    """§3: one row per analyzable chapter, keyed by its [chNN ¶1] anchor."""
    header, rows = _table_rows(body)
    if header is None:
        failures.append("§3: missing structure table")
        return
    seen = {}
    for i, cells in enumerate(rows):
        anchors = parse_anchors(" | ".join(cells))
        if not anchors:
            failures.append("§3: table row %d has no [chNN ¶1] anchor" % (i + 1))
            continue
        a = anchors[0]
        if not validate_anchor(a, book)["ok"]:
            failures.append("§3: table row %d anchor [%s] does not resolve"
                            % (i + 1, a["raw"]))
            continue
        head = head_of.get(a["chap"], a["chap"])
        seen[head] = seen.get(head, 0) + 1
    for h in heads:
        n = seen.get(h, 0)
        if n == 0:
            failures.append("§3: analyzable chapter %s missing from structure table" % h)
        elif n > 1:
            failures.append("§3: chapter %s appears %d times in structure table (need exactly once)"
                            % (h, n))


_TERM_FIELDS = ["Definition", "Intended meaning", "Role in system",
                "Adjacent concepts", "Example", "Misunderstanding to avoid"]


def _check_term_entries(body, book, n_heads, failures):
    """§4: >= max(15, chapters) entries, 6 '- Field:' lines each, Example anchored."""
    starts = list(re.finditer(r"^\*\*([^*]+)\*\*\s*\(introduced\b", body, re.M))
    need = max(15, n_heads)
    if len(starts) < need:
        failures.append("§4: %d term entries (need >= %d)" % (len(starts), need))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
        entry = body[m.start():end]
        term = m.group(1).strip()
        for field in _TERM_FIELDS:
            fm = re.search(r"^\s*-\s*%s\s*:(.*)$" % re.escape(field), entry,
                           re.M | re.I)
            if not fm:
                failures.append("§4 %r: missing '- %s:' field" % (term, field))
            elif field == "Example" and not _valid_anchors(fm.group(0), book):
                failures.append("§4 %r: Example line has no valid anchor" % term)
    return len(starts)


_STEP_RE = re.compile(r"^\s*(?:[-*]\s*)?\**([APMIC]\d+)\.\**")


def _check_argument_steps(body, book, failures, pool):
    """§6: every step line anchored; collect steps into the audit pool."""
    n_steps = 0
    seen_ids = {}
    for line in body.splitlines():
        m = _STEP_RE.match(line)
        if not m:
            continue
        n_steps += 1
        sid = m.group(1)
        seen_ids[sid] = seen_ids.get(sid, 0) + 1
        uid = "S6:%s" % sid if seen_ids[sid] == 1 else "S6:%s.%d" % (sid, seen_ids[sid])
        anchors = _valid_anchors(line, book)
        if not anchors:
            failures.append("§6: step %s has no valid anchor" % sid)
        pool.append({"id": uid, "section": 6, "text": line.strip(),
                     "anchor": anchors[0]["raw"] if anchors else None,
                     "_chap": anchors[0]["chap"] if anchors else None})
    if n_steps == 0:
        failures.append("§6: no argument steps found (A1./P1./M1./I1./C1. lines)")
    return n_steps


def _check_evidence_table(body, book, cfg, heads, head_of, members_of, failures,
                          pool, quote_records):
    """§7: 8-column table, enums, quote-bearing valid anchor per row,
    >= max(12, 1/chapter) rows, >=1 row per analyzable chapter."""
    header, rows = _table_rows(body)
    if header is None:
        failures.append("§7: missing evidence ledger table")
        return 0
    if len(header) != 8:
        failures.append("§7: table has %d columns (need 8)" % len(header))
    types = set(cfg["evidence_types"])
    weights = set(cfg["evidence_weights"])
    covered = set()
    for i, cells in enumerate(rows):
        rid = "row %d" % (i + 1)
        if len(cells) != 8:
            failures.append("§7 %s: %d cells (need 8)" % (rid, len(cells)))
            continue
        _, claim, item, etype, anchor_cell, quote_cell, weight, _ = cells
        if etype.strip().lower() not in types:
            failures.append("§7 %s: type %r not in %s"
                            % (rid, etype, "/".join(sorted(types))))
        if weight.strip().lower() not in weights:
            failures.append("§7 %s: weight %r not in %s"
                            % (rid, weight, "/".join(sorted(weights))))
        anchors = parse_anchors(anchor_cell)
        anchor = anchors[0] if anchors else None
        v = validate_anchor(anchor, book) if anchor else None
        if not anchor or not v["ok"]:
            failures.append("§7 %s: no valid anchor (%s)"
                            % (rid, v["reason"] if v else "none parsed"))
            pool.append({"id": "S7:row%02d" % (i + 1), "section": 7,
                         "text": "%s — %s" % (claim, item), "anchor": None,
                         "_chap": None})
            continue
        # quote: embedded in the anchor, else the Quote column
        frag = anchor.get("quote")
        status = v["quote_status"]
        if not frag:
            frag = quote_cell.strip().strip('"“”').strip()
            if frag in ("", "-", "—", "–"):
                frag = None
            elif util.word_count(frag) > QUOTE_MAX_WORDS:
                failures.append("§7 %s: quote longer than %d words" % (rid, QUOTE_MAX_WORDS))
                frag = None
            else:
                status = _quote_status(frag, book, anchor["chap"],
                                       anchor["start"], anchor["end"])
        if not frag:
            failures.append("§7 %s: no quote (rows must be quote-bearing)" % rid)
        else:
            quote_records.append({"where": "§7 %s" % rid, "status": status,
                                  "anchor": anchor["raw"], "quote": frag})
            if status == "unmatched":
                failures.append("§7 %s: quote %r does not match %s ¶%d–%d"
                                % (rid, frag, anchor["chap"], anchor["start"],
                                   anchor["end"]))
        covered.add(head_of.get(anchor["chap"], anchor["chap"]))
        pool.append({"id": "S7:row%02d" % (i + 1), "section": 7,
                     "text": "%s — %s" % (claim, item), "anchor": anchor["raw"],
                     "_chap": anchor["chap"]})
    need_rows = max(12, len(heads))
    if len(rows) < need_rows:
        failures.append("§7: %d rows (need >= %d)" % (len(rows), need_rows))
    for h in heads:
        if h not in covered and not (set(members_of.get(h, [h])) & covered):
            failures.append("§7: no evidence row anchored in chapter %s" % h)
    return len(rows)


def _check_misreading_pairs(body, book, failures):
    """§10: >=5 **Misreading:**/**Correction:** pairs, corrections anchored."""
    marks = list(re.finditer(r"\*\*Misreading:?\*\*", body))
    if len(marks) < 5:
        failures.append("§10: %d misreading pairs (need >= 5)" % len(marks))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        chunk = body[m.start():end]
        cm = re.search(r"\*\*Correction:?\*\*", chunk)
        if not cm:
            failures.append("§10 pair %d: missing **Correction:**" % (i + 1))
        elif not _valid_anchors(chunk[cm.end():], book):
            failures.append("§10 pair %d: correction has no valid anchor" % (i + 1))
    return len(marks)


_ITEM_START_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def _list_items(body):
    """Top-level list items (bullet or numbered) with wrapped lines attached."""
    items = []
    for line in body.splitlines():
        if _ITEM_START_RE.match(line):
            items.append(line)
        elif items and line.strip():
            items[-1] += "\n" + line
    return items


def _check_tension_items(body, book, failures):
    """§12: >=3 items, each citing >=2 anchors (the passages in tension)."""
    items = _list_items(body)
    if len(items) < 3:
        failures.append("§12: %d tension items (need >= 3 list items)" % len(items))
    for i, item in enumerate(items):
        n = len(_valid_anchors(item, book))
        if n < 2:
            failures.append("§12 item %d: %d valid anchors (need >= 2)" % (i + 1, n))
    return len(items)


_NO_EXTERNAL = "External research was not performed."


def _check_external_citations(body, failures):
    """§13: >=3 external citations OR the literal opt-out sentence."""
    links = re.findall(r"\[[^\]]+\]\([^)]+\)", body)
    exts = re.findall(r"\[ext:[^\]]+\]", body)
    n = len(links) + len(exts)
    if n < 3 and _NO_EXTERNAL not in body:
        failures.append("§13: %d external citations (need >= 3, or the literal "
                        "sentence %r)" % (n, _NO_EXTERNAL))
    return n


_QBANK_RE = re.compile(r"^\*\*Q(\d{1,3})\*\*\s*\(([^;()]+);([^)]*)\)\s*[—-]\s*(.+)$",
                       re.M)
_H3_RE = re.compile(r"^### ", re.M)


def _recall_blocks(body):
    """[(qid:int, difficulty, chapters, question, answer_text), …] from §14 or
    recall.md. Answer text runs to the next **Qnn** or H3 heading."""
    out = []
    marks = list(_QBANK_RE.finditer(body))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        h3 = _H3_RE.search(body, m.end(), end)
        if h3:
            end = h3.start()
        block = body[m.end():end]
        am = re.search(r"\*\*A\*\*\s*[—-]\s*", block)
        answer = block[am.end():] if am else None
        out.append((int(m.group(1)), m.group(2).strip().lower(),
                    m.group(3).strip(), m.group(4).strip(), answer))
    return out


def _norm_q(text):
    return " ".join(text.split())


def _check_recall_bank(body, book, book_dir, cfg, n_heads, failures):
    """§14: bank size, synthesis share, anchored answers, 20 anchored
    must-remember ideas, 1:1 parity with recall.md."""
    stats = {"bank_size": 0, "required": 0, "synthesis": 0, "parity_ok": False}
    blocks = _recall_blocks(body)
    stats["bank_size"] = len(blocks)
    need = max(cfg["recall"]["bank_size_min"],
               n_heads + int(cfg["recall"]["bank_size_formula"].split("+")[1]))
    stats["required"] = need
    if len(blocks) < need:
        failures.append("§14: recall bank has %d questions (need >= %d)"
                        % (len(blocks), need))
    n_syn = sum(1 for b in blocks if b[1] == "synthesis")
    stats["synthesis"] = n_syn
    if n_syn < cfg["recall"]["synthesis_min"]:
        failures.append("§14: %d synthesis questions (need >= %d)"
                        % (n_syn, cfg["recall"]["synthesis_min"]))
    seen_ids = set()
    for qid, _, _, _, answer in blocks:
        if qid in seen_ids:
            failures.append("§14: duplicate question id Q%02d" % qid)
        seen_ids.add(qid)
        if answer is None:
            failures.append("§14: Q%02d has no **A** — answer" % qid)
        elif not _valid_anchors(answer, book):
            failures.append("§14: Q%02d answer has no valid anchor" % qid)

    # -- 20 must-remember ideas, each anchored
    mm = re.search(r"^.*must.remember.*$", body, re.M | re.I)
    if not mm:
        failures.append("§14: missing must-remember ideas subsection")
    else:
        end = len(body)
        stop = re.search(r"^.*(memory hooks|question bank|self.test).*$|^### ",
                         body[mm.end():], re.M | re.I)
        if stop:
            end = mm.end() + stop.start()
        items = _list_items(body[mm.end():end])
        if len(items) < 20:
            failures.append("§14: %d must-remember ideas (need 20)" % len(items))
        for i, item in enumerate(items):
            if not _valid_anchors(item, book):
                failures.append("§14: must-remember idea %d has no valid anchor"
                                % (i + 1))

    # -- 1:1 parity with recall.md
    rpath = Path(book_dir) / "recall.md"
    if not rpath.exists():
        failures.append("§14: missing recall.md (bank must be exported 1:1)")
        return stats
    rblocks = _recall_blocks(rpath.read_text(encoding="utf-8"))
    bank = dict((b[0], _norm_q(b[3])) for b in blocks)
    rmap = dict((b[0], _norm_q(b[3])) for b in rblocks)
    if bank == rmap:
        stats["parity_ok"] = True
    else:
        for qid in sorted(set(bank) - set(rmap)):
            failures.append("§14: Q%02d missing from recall.md (parity)" % qid)
        for qid in sorted(set(rmap) - set(bank)):
            failures.append("§14: recall.md has extra Q%02d (parity)" % qid)
        for qid in sorted(set(bank) & set(rmap)):
            if bank[qid] != rmap[qid]:
                failures.append("§14: Q%02d text differs between dossier and "
                                "recall.md (parity)" % qid)
    return stats


# ---------------------------------------------------------------- audit sampling

def _sample_pool(pool, heads, seed, size):
    """Seeded stratified sample: >=1 item per analyzable chapter, remainder
    round-robin with 2x weight on the middle third of chapters."""
    if len(pool) <= size:
        return list(pool)
    rng = random.Random(seed)
    buckets = {}
    for item in pool:
        buckets.setdefault(item.get("_head"), []).append(item)
    sample = []

    def take(head):
        b = buckets.get(head)
        if not b:
            return False
        sample.append(b.pop(rng.randrange(len(b))))
        return True

    for head in heads:                      # stratified: one per chapter
        if len(sample) >= size:
            break
        take(head)
    lo = len(heads) // 3
    hi = len(heads) - lo
    order = []
    for i, head in enumerate(heads):        # 2x weight on the middle third
        order.append(head)
        if lo <= i < hi:
            order.append(head)
    order.append(None)                      # items with no resolvable chapter
    while len(sample) < size:
        progressed = False
        for head in order:
            if take(head):
                progressed = True
                if len(sample) >= size:
                    break
        if not progressed:
            break
    return sample


# ---------------------------------------------------------------- yaml emit + injection

def _emit_scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, float):
        return "%g" % round(v, 4)
    if isinstance(v, int):
        return "%d" % v
    s = str(v)
    if s == "" or re.search(r'[:#\[\]{},"\']|^\s|\s$', s):
        return '"%s"' % s.replace('"', '\\"')
    return s


def _emit_yaml(data, indent=0):
    lines = []
    pad = "  " * indent
    for key, val in data.items():
        if isinstance(val, dict):
            lines.append("%s%s:" % (pad, key))
            lines.extend(_emit_yaml(val, indent + 1))
        elif isinstance(val, list):
            lines.append("%s%s: [%s]" % (pad, key,
                                         ", ".join(_emit_scalar(v) for v in val)))
        else:
            lines.append("%s%s: %s" % (pad, key, _emit_scalar(val)))
    return lines


def _inject_block(text, block_yaml):
    """Place the machine block between the §16 markers (replace existing
    content, or create the markers at the end of the file)."""
    payload = "%s\n```yaml\n%s\n```\n%s" % (_VERIF_BEGIN, block_yaml, _VERIF_END)
    if _VERIF_BEGIN in text and _VERIF_END in text:
        return re.sub(re.escape(_VERIF_BEGIN) + r".*?" + re.escape(_VERIF_END),
                      lambda _m: payload, text, count=1, flags=re.S)
    if not text.endswith("\n"):
        text += "\n"
    return "%s\n%s\n" % (text, payload)


# ---------------------------------------------------------------- full verification

def _f_per_chapter(cfg5, n_heads):
    """§5 per-chapter word floor F(N)."""
    pc = cfg5["per_chapter"]
    if n_heads <= pc["scale_above_chapters"]:
        return pc["min_words"]
    return max(pc["scaled_floor"], pc["scaled_budget"] // n_heads)


def _packet_ranges(book_dir, heads):
    """chap -> [(start, end), …] from every packet file (provenance index)."""
    ranges = {}
    for head in heads:
        ppath = Path(book_dir) / "packets" / ("%s.md" % head)
        if not ppath.exists():
            continue
        text = ppath.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        body = m.group(2) if m else text
        for a in parse_anchors(body):
            ranges.setdefault(a["chap"], []).append((a["start"], a["end"]))
    return ranges


def verify_dossier(book_dir):
    """Stage 4a: deterministically verify dossier.md, write verification.json,
    inject the §16 machine block, return the results dict."""
    bd = Path(book_dir)
    cfg = util.sections_config()
    book = load_book(bd)
    try:
        meta = util.load_json(bd / "meta.json")
    except Exception:
        meta = {}
    try:
        skeleton = util.load_json(bd / "skeleton.json")
    except Exception:
        skeleton = {"chapters": []}
    heads = _analyzable_heads(skeleton)
    head_of = _head_of_map(skeleton)
    members_of = {}
    for cid, head in head_of.items():
        members_of.setdefault(head, []).append(cid)
    n_heads = len(heads)

    raw = (bd / "dossier.md").read_text(encoding="utf-8")
    pre_text = _canonical_pre_text(raw)
    pre_sha = util.sha256_text(pre_text)

    failures = []
    repair_list = []
    pool = []
    quote_records = []

    # -- (a) sections present, in order
    found = re.findall(r"^## +(.+?)\s*$", pre_text, re.M)
    order_msgs = _heading_order_msgs(found, _dossier_headings(cfg))
    failures.extend(order_msgs)
    bodies, _ = _split_dossier_sections(pre_text, cfg)
    sec_words = dict((sid, util.word_count(b)) for sid, b in bodies.items())
    total_words = util.word_count(pre_text)
    if total_words < cfg["total_words_min"]:
        failures.append("total words %d < %d floor" % (total_words, cfg["total_words_min"]))

    # -- (c) all anchors: validity, fatal ids, per-section minimums
    anchors_total = 0
    anchors_valid = 0
    fatal = 0
    valid_by_section = {}
    for scfg in cfg["sections"]:
        sid = scfg["id"]
        body = bodies.get(sid, "")
        n_ok = 0
        for a in _scan_anchors(body, skip_covers=(sid == 5)):
            anchors_total += 1
            v = validate_anchor(a, book)
            a["_section"] = sid
            a["_v"] = v
            valid_by_section.setdefault(sid, []).append(a)
            if v["ok"]:
                n_ok += 1
                if a.get("quote"):
                    quote_records.append({"where": "§%d" % sid,
                                          "status": v["quote_status"],
                                          "anchor": a["raw"], "quote": a["quote"]})
            else:
                if v["reason"].startswith("nonexistent chapter id"):
                    fatal += 1
                repair_list.append({"where": "§%d" % sid,
                                    "problem": "invalid anchor: %s" % v["reason"],
                                    "anchor": a["raw"]})
        anchors_valid += n_ok
        amin = scfg.get("anchor_min", 0)
        if amin and n_ok < amin:
            failures.append("§%d: %d valid anchors (need >= %d)" % (sid, n_ok, amin))
    validity_rate = (anchors_valid / anchors_total) if anchors_total else 0.0
    if validity_rate < cfg["gates"]["anchors_resolve_min"]:
        failures.append("anchor validity %.3f < %.2f gate"
                        % (validity_rate, cfg["gates"]["anchors_resolve_min"]))
    if fatal:
        failures.append("%d anchor(s) cite nonexistent chapter ids (zero tolerance)" % fatal)

    # anchor density over §2–§12
    dlo, dhi = cfg["anchor_density"]["sections"]
    d_words = sum(sec_words.get(s, 0) for s in range(dlo, dhi + 1))
    d_anchors = sum(1 for s in range(dlo, dhi + 1)
                    for a in valid_by_section.get(s, []) if a["_v"]["ok"])
    density = (d_anchors * 1000.0 / d_words) if d_words else 0.0
    if density < cfg["anchor_density"]["min_per_1000_words"]:
        failures.append("anchor density %.2f/1000 words over §%d–§%d < %.1f"
                        % (density, dlo, dhi,
                           cfg["anchor_density"]["min_per_1000_words"]))

    # provenance: every anchor must be copied from a packet (§3 ¶1 + §13 exempt)
    pranges = _packet_ranges(bd, heads)
    prov_violations = 0
    for sid, alist in valid_by_section.items():
        if sid == 13:
            continue
        for a in alist:
            if not a["_v"]["ok"]:
                continue
            if sid == 3 and a["start"] == 1 and a["end"] == 1:
                continue
            spans = pranges.get(a["chap"], [])
            if not any(s <= a["start"] <= e for s, e in spans):
                prov_violations += 1
                repair_list.append({"where": "§%d" % sid,
                                    "problem": "provenance: anchor not copied from "
                                               "any packet anchor range",
                                    "anchor": a["raw"]})
    if prov_violations > cfg["gates"]["provenance_violations_max"]:
        failures.append("%d provenance violation(s) — anchors must come from packets"
                        % prov_violations)

    # -- (b) §5 chapter entries, floors, back-half ratio
    floor5 = _f_per_chapter(cfg["sections"][5], n_heads) if n_heads else 0
    entries = []          # in appearance order: (head, words, n_anchors)
    entry_heads = set()
    body5 = bodies.get(5, "")
    h3s = list(re.finditer(r"^### +(.+?)\s*$", body5, re.M))
    for i, m in enumerate(h3s):
        end = h3s[i + 1].start() if i + 1 < len(h3s) else len(body5)
        etext = body5[m.end():end]
        cm = _COVERS_REF_RE.search(etext)
        if not cm:
            failures.append("§5 entry %r: missing _Covers [chNN ¶…]_ line" % m.group(1))
            continue
        head = head_of.get(cm.group(1), cm.group(1))
        entry_heads.add(head)
        ewords = util.word_count(etext)
        e_anchors = _valid_anchors(etext, book, skip_covers=True)
        entries.append((head, ewords, len(e_anchors)))
        if ewords < floor5:
            repair_list.append({"where": "§5 %s" % head,
                                "problem": "entry words %d < floor %d" % (ewords, floor5)})
        amin5 = cfg["sections"][5]["per_chapter"]["anchor_min"]
        if len(e_anchors) < amin5:
            failures.append("§5 %s: %d valid anchors (need >= %d)"
                            % (head, len(e_anchors), amin5))
        tm = re.search(r"^\s*\*\*Thesis:?\*\*:?\s*(.*)$", etext, re.M)
        if not tm:
            failures.append("§5 %s: missing **Thesis** line" % head)
        else:
            t_anchors = _valid_anchors(tm.group(0), book)
            if not t_anchors:
                failures.append("§5 %s: Thesis line has no valid anchor" % head)
            pool.append({"id": "S5:%s" % head, "section": 5,
                         "text": tm.group(1).strip(),
                         "anchor": t_anchors[0]["raw"] if t_anchors else None,
                         "_chap": head})
    for h in heads:
        if h not in entry_heads:
            failures.append("§5: missing chapter entry for %s" % h)
    k = max(1, math.ceil(len(entries) / 4.0)) if entries else 1
    back_half = 1.0
    if len(entries) >= 2:
        first = [w for _, w, _ in entries[:k]]
        last = [w for _, w, _ in entries[-k:]]
        mean_first = sum(first) / float(len(first))
        back_half = (sum(last) / float(len(last)) / mean_first) if mean_first else 1.0
    if back_half < cfg["gates"]["back_half_ratio_min"]:
        failures.append("§5 back-half ratio %.2f < %.2f (later chapters too thin)"
                        % (back_half, cfg["gates"]["back_half_ratio_min"]))

    # -- word floors (completeness)
    floors_met = 0
    floor_misses = []
    for scfg in cfg["sections"]:
        sid = scfg["id"]
        if sid not in bodies:
            floor_misses.append(sid)
            continue
        if sid == 5:
            ok5 = (len(entry_heads) >= n_heads
                   and all(w >= floor5 for _, w, _ in entries))
            met = bool(entries) and ok5
        else:
            met = sec_words.get(sid, 0) >= scfg.get("min_words", 0)
        if met:
            floors_met += 1
        else:
            floor_misses.append(sid)
            repair_list.append({"where": "§%d" % sid,
                                "problem": "words %d < floor %d"
                                           % (sec_words.get(sid, 0),
                                              scfg.get("min_words", 0))})
    if floors_met < cfg["gates"]["floors_met_min"]:
        failures.append("%d/17 section floors met (need >= %d)"
                        % (floors_met, cfg["gates"]["floors_met_min"]))
    hard_missed = [s for s in cfg["gates"]["mandatory_floor_sections"]
                   if s in floor_misses]
    if hard_missed:
        failures.append("mandatory section floors missed: %s"
                        % ", ".join("§%d" % s for s in hard_missed))

    # -- (d) special section checks
    _check_source_yaml(bodies.get(0, ""), book, meta, failures)
    _check_structure_table(bodies.get(3, ""), book, heads, head_of, failures)
    n_terms = _check_term_entries(bodies.get(4, ""), book, n_heads, failures)
    n_steps = _check_argument_steps(bodies.get(6, ""), book, failures, pool)
    n_rows = _check_evidence_table(bodies.get(7, ""), book, cfg, heads, head_of,
                                   members_of, failures, pool, quote_records)
    n_pairs = _check_misreading_pairs(bodies.get(10, ""), book, failures)
    n_tensions = _check_tension_items(bodies.get(12, ""), book, failures)
    n_ext = _check_external_citations(bodies.get(13, ""), failures)
    recall_stats = _check_recall_bank(bodies.get(14, ""), book, bd, cfg,
                                      n_heads, failures)

    # -- (e) quote statistics
    q_total = len(quote_records)
    q_exact = sum(1 for q in quote_records if q["status"] == "exact")
    q_fuzzy = sum(1 for q in quote_records if q["status"] == "fuzzy")
    q_unmatched = q_total - q_exact - q_fuzzy
    quote_rate = ((q_exact + q_fuzzy) / float(q_total)) if q_total else 1.0
    if quote_rate < cfg["gates"]["quote_match_min"]:
        failures.append("quote match rate %.2f < %.2f gate"
                        % (quote_rate, cfg["gates"]["quote_match_min"]))
    for q in quote_records:
        if q["status"] == "unmatched":
            repair_list.append({"where": q["where"],
                                "problem": "unmatched quote %r" % q["quote"],
                                "anchor": q["anchor"]})

    # -- coverage: packet AND §5 entry per analyzable chapter
    n_packets = sum(1 for h in heads if (bd / "packets" / ("%s.md" % h)).exists())
    covered = sum(1 for h in heads
                  if (bd / "packets" / ("%s.md" % h)).exists() and h in entry_heads)
    coverage = (covered / float(n_heads)) if n_heads else 0.0
    if coverage < 1.0:
        failures.append("chapter coverage %.0f%% < 100%% (packets ∧ §5 entries)"
                        % (coverage * 100))

    # -- (f) claim audit: seeded sample + audit.json fold-in
    for item in pool:
        item["_head"] = head_of.get(item.get("_chap"), item.get("_chap"))
    seed = int(pre_sha[:8], 16)
    sample = _sample_pool(pool, heads, seed, cfg["gates"]["audit_sample_size"])
    audit_sample = [{"id": it["id"], "section": it["section"],
                     "text": it["text"], "anchor": it["anchor"]} for it in sample]
    sample_ids = set(it["id"] for it in sample)
    audit_status = "pending"
    auditor = None
    claim_support = None
    apath = bd / "audit.json"
    if apath.exists():
        try:
            audit = util.load_json(apath)
        except Exception as e:
            audit = None
            failures.append("unparseable audit.json: %s" % e)
        if audit is not None:
            if audit.get("dossier_sha256") != pre_sha:
                audit_status = "stale"
                failures.append("audit.json is stale (dossier changed since audit) "
                                "— re-audit against sha %s" % util.sha12(pre_sha))
            else:
                audit_status = "ok"
                auditor = audit.get("auditor")
                verdicts = dict((r.get("id"), r.get("verdict"))
                                for r in audit.get("results", []))
                n_sup = sum(1 for i in sample_ids if verdicts.get(i) == "supported")
                n_par = sum(1 for i in sample_ids if verdicts.get(i) == "partial")
                claim_support = ((n_sup + 0.5 * n_par) / float(len(sample))
                                 if sample else 0.0)
                if claim_support < cfg["gates"]["claim_support_min"]:
                    failures.append("claim support %.2f < %.2f gate"
                                    % (claim_support, cfg["gates"]["claim_support_min"]))
                bad6 = sorted(i for i in sample_ids
                              if i.startswith("S6:")
                              and verdicts.get(i) == "unsupported")
                if bad6:
                    failures.append("unsupported §6 step(s): %s (zero tolerance)"
                                    % ", ".join(bad6))
    if audit_status == "pending":
        failures.append("claim audit pending — write audit.json for dossier sha %s "
                        "(see workflow/04-verify.md)" % util.sha12(pre_sha))

    # -- (g) score, pass, badge
    weights = cfg["score_weights"]
    completeness = floors_met / 17.0
    score = 100.0 * (weights["anchor_validity"] * validity_rate
                     + weights["claim_support"] * (claim_support or 0.0)
                     + weights["coverage"] * coverage
                     + weights["quote_match"] * quote_rate
                     + weights["completeness"] * completeness)
    score = round(score, 1)
    passed = not failures
    if passed:
        if score >= cfg["badges"]["verified_min_score"]:
            badge = "VERIFIED"
        elif score >= cfg["badges"]["warnings_min_score"]:
            badge = "VERIFIED-WITH-WARNINGS"
        else:
            badge = "FAILED"
            passed = False
    else:
        badge = "FAILED"

    # -- (h) results, §16 block injection, verification.json
    results = {
        "checker_version": CHECKER_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "book": {"slug": meta.get("slug", bd.name),
                 "chapters": len(book.chapter_ids),
                 "analyzable": n_heads,
                 "paragraphs": sum(book.para_count(c) for c in book.chapter_ids)},
        "sections": {"present": len([s for s in cfg["sections"] if s["id"] in bodies]),
                     "order_ok": not order_msgs,
                     "floors_met": floors_met,
                     "floor_misses": floor_misses},
        "words": {"total": total_words,
                  "per_section": dict(("%d" % k, v) for k, v in sorted(sec_words.items()))},
        "anchors": {"total": anchors_total, "valid": anchors_valid,
                    "validity_rate": round(validity_rate, 4),
                    "fatal_chapter_ids": fatal,
                    "density_per_1000": round(density, 2),
                    "provenance_violations": prov_violations},
        "quotes": {"total": q_total, "exact": q_exact, "fuzzy": q_fuzzy,
                   "unmatched": q_unmatched, "match_rate": round(quote_rate, 4)},
        "coverage": {"chapters": n_heads, "packets": n_packets,
                     "section5_entries": len(entry_heads),
                     "rate": round(coverage, 4),
                     "back_half_ratio": round(back_half, 3)},
        "counts": {"term_entries": n_terms, "argument_steps": n_steps,
                   "evidence_rows": n_rows, "misreading_pairs": n_pairs,
                   "tension_items": n_tensions, "external_citations": n_ext},
        "recall": recall_stats,
        "audit": {"status": audit_status, "auditor": auditor,
                  "sample_size": len(sample),
                  "claim_support": (round(claim_support, 4)
                                    if claim_support is not None else None)},
        "score": score,
        "badge": badge,
        "pass": passed,
        "failures": failures,
        "repair_list": repair_list,
        "audit_sample": audit_sample,
    }

    block = {
        "checker_version": CHECKER_VERSION,
        "checked_at": results["checked_at"],
        "book": results["book"],
        "coverage": {"packets": "%d/%d" % (n_packets, n_heads),
                     "section5": "%d/%d" % (len(entry_heads), n_heads),
                     "rate": round(coverage, 4),
                     "back_half_ratio": round(back_half, 3)},
        "words": {"total": total_words, "floors_met": "%d/17" % floors_met},
        "anchors": results["anchors"],
        "quotes": results["quotes"],
        "recall": recall_stats,
        "audit": {"status": audit_status, "sample_size": len(sample),
                  "claim_support": results["audit"]["claim_support"]},
        "score": score,
        "badge": badge,
        "pass": passed,
    }
    final_text = _inject_block(raw, "\n".join(_emit_yaml(block)))
    (bd / "dossier.md").write_text(final_text, encoding="utf-8")
    results["dossier_sha256"] = util.sha256_text(final_text)
    results["dossier_sha256_pre_injection"] = pre_sha
    util.save_json(bd / "verification.json", results)
    return results
