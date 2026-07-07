#!/usr/bin/env python3
"""Self-test for scripts/style_lint.py — stdlib only, exit 0 = pass.

Proves: every rule fires on bad.md; good.md is clean; strict vs report
exit semantics; acks unblock without hiding; hard fails ignore acks'
absence of scope creep (an ack names its rule and path)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "style_lint.py"
FIX = ROOT / "tests" / "fixtures" / "style"

failures = []


def run(*args):
    return subprocess.run([sys.executable, str(LINT), *args],
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    print(f"{'ok' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# 1. Every rule fires on bad.md (strict → blocking, exit 1).
r = run("--mode", "strict", str(FIX / "bad.md"))
check("bad.md blocks in strict mode", r.returncode == 1, r.stdout + r.stderr)
expected_rules = [
    "receipted", "blacklist-word", "frame-abstract", "receipt-count",
    "emdash-paragraph", "emdash-flourish", "contrast-negation",
    "rhetorical-question", "anaphora-run", "filler-idiom",
    "mid-sentence-bold", "colon-openers",
]
for rule in expected_rules:
    check(f"rule fires: {rule}", rule in r.stdout, r.stdout)

# 2. good.md is clean.
r = run("--mode", "strict", str(FIX / "good.md"))
check("good.md passes strict", r.returncode == 0, r.stdout)
check("good.md has zero findings", "0 finding(s)" in r.stdout, r.stdout)

# 3. Report mode never blocks, still annotates.
r = run("--mode", "report", str(FIX / "bad.md"))
check("report mode exits 0 on bad.md", r.returncode == 0, r.stdout)
check("report mode still prints findings", "receipted" in r.stdout)

# 4. Acks unblock the acked rules but nothing else; findings stay visible.
r = run("--mode", "strict", "--config", str(FIX / ".style-lint.json"),
        str(FIX / "acked.md"))
check("acked.md passes strict via acks", r.returncode == 0,
      r.stdout + r.stderr)
check("acked findings remain visible", "[acked]" in r.stdout, r.stdout)

# 5. The same file without acks blocks (proves the acks did the work).
r = run("--mode", "strict", "--config", str(FIX / "no-acks.json"),
        str(FIX / "acked.md"))
check("acked.md blocks without its acks", r.returncode == 1, r.stdout)

# 6. Counts mode emits the tic table.
r = run("--counts", str(FIX / "bad.md"))
check("counts mode exits 0", r.returncode == 0, r.stderr)
check("counts mode emits TSV header", r.stdout.startswith("file\t"), r.stdout)

print()
if failures:
    print(f"self-test FAILED: {len(failures)} check(s): {failures}")
    sys.exit(1)
print("style-lint self-test passed.")
