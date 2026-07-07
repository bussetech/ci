#!/usr/bin/env python3
"""style-lint — deterministic external-prose lint for the studio's style
doctrine (platform docs/gtm/style.md, External Style Guide v1).

Zero tokens, stdlib only (ci repo rule: self-contained checkers). Lints
Markdown/HTML *source* so findings carry real line numbers.

Rules (RULES_VERSION tracks the guide; the blacklist is versioned because
machine tells drift with model generations):

  Hard fails (block whenever mode=strict):
    receipted        "receipt" as a verb, banned outright
    blacklist-word   the §2.5 word blacklist
    frame-abstract   frame/framing as abstract noun (allowlist for
                     picture/house/technical senses)

  Warnings (block only on files matching a "strict" glob, unless acked):
    receipt-count      "receipt(s)" more than once per page
    emdash-paragraph   more than one emdash in a paragraph
    emdash-flourish    the "X — not Y" flourish more than once per page
    contrast-negation  "It's not X. It's Y." and cousins
    rhetorical-question  "The result?" and kin
    anaphora-run       3+ consecutive sentences opening with the same word
    filler-idiom       "here's the thing", "simply put", ...
    mid-sentence-bold  bold for emphasis inside body prose (md only)
    colon-openers      3+ "Term: ..." paragraph openers on one page

Config: .style-lint.json in the lint root (all keys optional):
  {
    "exclude":  ["sites/**", "_posts/**"],       # never scanned
    "strict":   ["**"],                          # warnings block here
    "ack": [                                     # sysop-reviewed waivers
      {"path": "how-it-works/index.md", "rule": "receipt-count",
       "reason": "the page is about the ledger"}
    ]
  }
"ack" entries silence *blocking* (finding still prints). "journey" inside
the Client Desk's lifecycle vocabulary is the canonical ack use-case.

Exit: 0 clean or nothing blocks; 1 blocking findings; 2 usage error.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

RULES_VERSION = "1.0"  # tracks docs/gtm/style.md v1 (STEERCO 2026-07-06)

HARD = ("receipted", "blacklist-word", "frame-abstract")

RX_RECEIPTED = re.compile(r"\breceipted\b", re.I)
RX_BLACKLIST = re.compile(
    r"\b(delv(?:e|es|ed|ing)|robust(?:ly|ness)?|seamless(?:ly)?"
    r"|leverag(?:e|es|ed|ing)|unlock(?:s|ed|ing)?|elevat(?:e|es|ed|ing)"
    r"|supercharg(?:e|es|ed|ing)|landscapes?|journey(?:s|ing)?"
    r"|empower(?:s|ed|ing|ment)?|holistic(?:ally)?|best[- ]in[- ]class)\b",
    re.I,
)
RX_FRAME = re.compile(r"\b(?:re)?fram(?:e|es|ing)\b", re.I)
# Literal/technical senses stay legal when named nearby (±60 chars).
RX_FRAME_ALLOW = re.compile(
    r"picture|photo|paint|window|door|wall|hous(?:e|ing)|timber|lumber|stud"
    r"|bed|bike|bicycle|glasses|A-frame|frame\s*rate|per\s+frame|frames?\s+per",
    re.I,
)
RX_RECEIPT = re.compile(r"\breceipts?\b", re.I)
RX_FLOURISH = re.compile(r"—\s*not\b", re.I)
RX_CONTRAST = [
    re.compile(r"\b(?:is|are)n'?t\s+just\b", re.I),
    re.compile(r"\bnot\s+just\b[^.!?\n]{0,80}[,;—–-][^.!?\n]{0,40}"
               r"\b(?:it'?s|it\s+is|but)\b", re.I),
    re.compile(r"(?:\bis|\bare|'s|\bwas)\s+not\s+[^.!?\n]{0,60}[.!?]\s+"
               r"(?:It|This|That|They)(?:'s|'re|\s+is|\s+are)\b"),
    re.compile(r"(?:\bis|'s)\s+not\b[^.!?\n]{0,60}—\s*(?:it|this|that|they)\b",
               re.I),
]
RX_RHETQ = re.compile(
    r"\b[Tt]he\s+(?:result|catch|kicker|upshot|difference|answer|problem"
    r"|best\s+part|payoff|point|goal|trade|lesson)\?")
RX_FILLER = re.compile(
    r"here'?s\s+the\s+thing|let'?s\s+be\s+clear|simply\s+put"
    r"|at\s+the\s+end\s+of\s+the\s+day", re.I)
RX_COLON_OPEN = re.compile(
    r"^\s*(?:[-*+]\s+|\d+\.\s+)?\*{0,2}[A-Z][A-Za-z0-9 '&/-]{1,30}\*{0,2}:\s")
RX_WORD = re.compile(r"\b[\w'’]+\b")

ALL_RULES = HARD + (
    "receipt-count", "emdash-paragraph", "emdash-flourish",
    "contrast-negation", "rhetorical-question", "anaphora-run",
    "filler-idiom", "mid-sentence-bold", "colon-openers",
)

DEFAULT_EXCLUDE = [
    "_site/**", "node_modules/**", "vendor/**", ".git/**", ".github/**",
    "**/.venv/**", "CLAUDE.md", "**/CLAUDE.md", "LICENSE*",
    ".style-lint-tools/**",
]


def blank(text, start, end, keep_quoted=False):
    """Replace text[start:end] with spaces, preserving newlines (and,
    optionally, quoted string contents — copy riding in Liquid params)."""
    seg = text[start:end]
    if keep_quoted:
        out = []
        for m in re.finditer(r"[\"']([^\"'\n]*)[\"']|(.)", seg, re.S):
            if m.group(1) is not None:
                q = m.group(0)
                out.append(" " + m.group(1) + " ")
                assert len(out[-1]) == len(q)
            else:
                out.append(m.group(2) if m.group(2) == "\n" else " ")
        seg = "".join(out)
    else:
        seg = re.sub(r"[^\n]", " ", seg)
    return text[:start] + seg + text[end:]


def clean(raw, is_html):
    """Strip non-prose regions offset-preservingly. Returns (text, fm_end)
    where fm_end is the char offset where YAML front matter ends (0 if none).
    Front matter itself is scanned (descriptions and FAQ copy live there) but
    layout-only rules skip it."""
    text = raw
    fm_end = 0
    m = re.match(r"---\n.*?\n---\n", raw, re.S)
    if m:
        fm_end = m.end()

    def blank_all(pattern, keep_quoted=False, flags=re.S):
        nonlocal text
        for mm in reversed(list(re.finditer(pattern, text, flags))):
            text = blank(text, mm.start(), mm.end(), keep_quoted)

    blank_all(r"```.*?(?:```|\Z)")                       # fenced code
    blank_all(r"{%-?\s*comment\s*-?%}.*?{%-?\s*endcomment\s*-?%}")
    blank_all(r"<!--.*?(?:-->|\Z)")                      # HTML comments
    blank_all(r"{%.*?%}", keep_quoted=True)              # Liquid tags
    blank_all(r"{{.*?}}")                                # Liquid output
    if is_html:
        # scripts are code — except JSON-LD, whose strings are page copy
        for mm in reversed(list(re.finditer(
                r"<script(?![^>]*application/ld\+json).*?</script>",
                text, re.S | re.I))):
            text = blank(text, mm.start(), mm.end())
        blank_all(r"<style.*?</style>", flags=re.S | re.I)
        blank_all(r"<[^>]*>")                            # tags
    blank_all(r"`[^`\n]+`", flags=0)                     # inline code
    blank_all(r"\]\([^)\n]+\)", flags=0)                 # md link targets
    blank_all(r"^\[[^\]\n]+\]:.*$", flags=re.M)          # reference targets
    return text, fm_end


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def paragraphs(text):
    """Yield (start_offset, paragraph_text) for blank-line-separated blocks."""
    pos = 0
    for block in re.split(r"\n\s*\n", text):
        idx = text.index(block, pos) if block else pos
        if block.strip():
            yield idx, block
        pos = idx + len(block)


def sentences(par):
    return [s for s in re.split(r"(?<=[.!?])\s+", par) if s.strip()]


class Finding:
    def __init__(self, path, line, rule, msg):
        self.path, self.line, self.rule, self.msg = path, line, rule, msg
        self.hard = rule in HARD
        self.blocking = False  # set during evaluation

    def __str__(self):
        sev = "FAIL" if self.hard else ("WARN*" if self.blocking else "WARN")
        return f"{self.path}:{self.line}: [{sev}] {self.rule}: {self.msg}"


def lint_file(path, rel):
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    is_html = str(path).endswith((".html", ".htm"))
    text, fm_end = clean(raw, is_html)
    f = []

    for m in RX_RECEIPTED.finditer(text):
        f.append(Finding(rel, line_of(text, m.start()), "receipted",
                         '"receipted" — receipt is a concept, not a verb'))
    for m in RX_BLACKLIST.finditer(text):
        f.append(Finding(rel, line_of(text, m.start()), "blacklist-word",
                         f'"{m.group(0)}"'))
    for m in RX_FRAME.finditer(text):
        ctx = text[max(0, m.start() - 60):m.end() + 60]
        if not RX_FRAME_ALLOW.search(ctx):
            f.append(Finding(rel, line_of(text, m.start()), "frame-abstract",
                             f'"{m.group(0)}" as abstract noun'))

    hits = list(RX_RECEIPT.finditer(text))
    if len(hits) > 1:
        f.append(Finding(rel, line_of(text, hits[1].start()), "receipt-count",
                         f'"receipt" ×{len(hits)} — budget is one per page'))

    flourishes = list(RX_FLOURISH.finditer(text))
    if len(flourishes) > 1:
        f.append(Finding(rel, line_of(text, flourishes[1].start()),
                         "emdash-flourish",
                         f'"X — not Y" ×{len(flourishes)} — at most once per page'))

    for rx in RX_CONTRAST:
        for m in rx.finditer(text):
            f.append(Finding(rel, line_of(text, m.start()), "contrast-negation",
                             f'"{" ".join(m.group(0).split())[:60]}"'))
    for m in RX_RHETQ.finditer(text):
        f.append(Finding(rel, line_of(text, m.start()), "rhetorical-question",
                         f'"{m.group(0)}"'))
    for m in RX_FILLER.finditer(text):
        f.append(Finding(rel, line_of(text, m.start()), "filler-idiom",
                         f'"{m.group(0)}"'))

    for off, par in paragraphs(text):
        n_em = par.count("—") + len(re.findall(r"\s–\s", par))
        if n_em > 1:
            f.append(Finding(rel, line_of(text, off), "emdash-paragraph",
                             f"{n_em} emdashes in one paragraph — budget is one"))
        sents = sentences(par)
        firsts = []
        for s in sents:
            w = RX_WORD.search(s)
            firsts.append(w.group(0).lower() if w else "")
        run, prev = 1, None
        for i, w in enumerate(firsts):
            if w and w == prev:
                run += 1
            else:
                if run >= 3:
                    f.append(Finding(rel, line_of(text, off), "anaphora-run",
                                     f'{run} sentences opening with "{prev}"'))
                run = 1
            prev = w
        if run >= 3:
            f.append(Finding(rel, line_of(text, off), "anaphora-run",
                             f'{run} sentences opening with "{prev}"'))

    if not is_html:
        fm_last_line = line_of(text, fm_end - 1) if fm_end else 0
        colon_lines = []
        for i, ln in enumerate(text.splitlines(), 1):
            if i <= fm_last_line:  # front matter: keys, not prose layout
                continue
            if RX_COLON_OPEN.match(ln):
                colon_lines.append(i)
            lm = re.match(r"\s*(?:[-*+]|\d+\.)\s+(.*)", ln)
            body = lm.group(1) if lm else ln
            pos = body.find("**")
            if pos > 15 and re.search(r"\*\*[^*\n]+\*\*", body[pos:]):
                f.append(Finding(rel, i, "mid-sentence-bold",
                                 "bold for emphasis inside body prose"))
        if len(colon_lines) >= 3:
            f.append(Finding(rel, colon_lines[2], "colon-openers",
                             f'{len(colon_lines)} "Term:" openers on one page'))

    counts = {r: 0 for r in ALL_RULES}
    for x in f:
        counts[x.rule] += 1
    counts["emdash-total"] = text.count("—")
    counts["words"] = len(RX_WORD.findall(text))
    return f, counts


def globmatch(rel, patterns):
    rp = rel.replace(os.sep, "/")
    for p in patterns:
        if fnmatch.fnmatch(rp, p) or fnmatch.fnmatch(os.path.basename(rp), p):
            return True
    return False


def load_config(root):
    cfg = {"exclude": [], "strict": ["**"], "ack": []}
    p = Path(root) / ".style-lint.json"
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text()))
        except json.JSONDecodeError as e:
            print(f"::error::style-lint: bad .style-lint.json: {e}")
            sys.exit(2)
    return cfg


def acked(finding, acks):
    for a in acks:
        if a.get("rule") != finding.rule:
            continue
        if not globmatch(finding.path, [a.get("path", "**")]):
            continue
        word = a.get("word")
        if word and word.lower() not in finding.msg.lower():
            continue
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--mode", choices=("strict", "report"), default="report",
                    help="strict: hard fails + strict-glob warnings block; "
                         "report: annotate only, always exit 0")
    ap.add_argument("--config", default=None,
                    help="explicit .style-lint.json (default: lint root)")
    ap.add_argument("--counts", action="store_true",
                    help="emit per-file tic counts (TSV) instead of findings")
    args = ap.parse_args()

    root = Path(args.paths[0])
    root = root if root.is_dir() else root.parent
    cfg = load_config(Path(args.config).parent if args.config else root)
    if args.config:
        cfg = {"exclude": [], "strict": ["**"], "ack": []}
        cfg.update(json.loads(Path(args.config).read_text()))

    files = []
    for p in args.paths:
        pp = Path(p)
        if pp.is_dir():
            files += sorted(pp.rglob("*.md")) + sorted(pp.rglob("*.html"))
        elif pp.exists():
            files.append(pp)
        else:
            print(f"style-lint: no such path: {p}", file=sys.stderr)
            return 2
    findings, table = [], []
    for fp in files:
        try:
            rel = str(fp.relative_to(root))
        except ValueError:
            rel = str(fp)
        if globmatch(rel, DEFAULT_EXCLUDE + cfg["exclude"]):
            continue
        fs, counts = lint_file(fp, rel)
        strict_here = args.mode == "strict" and globmatch(rel, cfg["strict"])
        for x in fs:
            if acked(x, cfg["ack"]):
                x.msg += "  [acked]"
            elif x.hard:
                x.blocking = args.mode == "strict"
            else:
                x.blocking = strict_here
        findings += fs
        table.append((rel, counts))

    if args.counts:
        cols = list(ALL_RULES) + ["emdash-total", "words"]
        print("file\t" + "\t".join(cols))
        for rel, c in table:
            print(rel + "\t" + "\t".join(str(c[k]) for k in cols))
        return 0

    blocking = [x for x in findings if x.blocking]
    for x in findings:
        print(x)
        if os.environ.get("GITHUB_ACTIONS"):
            kind = "error" if x.blocking else "warning"
            print(f"::{kind} file={x.path},line={x.line}::"
                  f"style-lint/{x.rule}: {x.msg}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and findings:
        with open(summary, "a") as fh:
            fh.write(f"\n### style-lint v{RULES_VERSION} — "
                     f"{len(findings)} finding(s), {len(blocking)} blocking\n\n"
                     "| file | line | rule | detail |\n|---|---|---|---|\n")
            for x in findings:
                fh.write(f"| {x.path} | {x.line} | {x.rule} | {x.msg} |\n")
    print(f"style-lint v{RULES_VERSION}: {len(files)} file(s), "
          f"{len(findings)} finding(s), {len(blocking)} blocking "
          f"(mode={args.mode}).")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
