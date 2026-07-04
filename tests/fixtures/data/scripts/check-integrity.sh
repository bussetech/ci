#!/usr/bin/env bash
# Referential integrity for the data fixture: every widget's owner must appear
# in owners.csv. This is the class of check schemas can't express and that
# catches the most common agent-written-data bug — dangling references.
set -euo pipefail

python3 - <<'PY'
import csv, glob, json, sys, pathlib

owners = set()
with open("data/owners.csv", newline="") as fh:
    for row in csv.DictReader(fh):
        owners.add(row["owner_id"])

dangling = []
for f in sorted(glob.glob("data/widgets/*.json")):
    w = json.loads(pathlib.Path(f).read_text())
    if w.get("owner") not in owners:
        dangling.append(f"{f}: owner '{w.get('owner')}' is not in owners.csv")

for d in dangling:
    print(f"::error::integrity: {d}")
if dangling:
    print(f"Referential integrity FAILED: {len(dangling)} dangling owner reference(s).")
    sys.exit(1)
print(f"Referential integrity OK: {len(owners)} owners, all widget owners resolve.")
PY
