#!/usr/bin/env python3
"""
Verify *majority* (quorum) consistency of Raft log dumps.

A log index is considered **consistent** when at least ⌈N / 2⌉ files
agree on exactly the same `(term, command)` *or* at least ⌈N / 2⌉ files
agree that the entry is **missing**.

For the usual 5‑node cluster the quorum is 3.
"""
import re
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# 1.  Configure the filenames you want to check
# ---------------------------------------------------------------------------
ip_parts   = [2, 3, 4, 5, 6]         # 127.0.0.{part}
filenames  = [f"raftlog_dump_127.0.0.{p}.log" for p in ip_parts]
N_NODES    = len(filenames)
QUORUM     = N_NODES // 2 + 1        # e.g. 3 for 5 nodes

# ---------------------------------------------------------------------------
# 2.  Parse every file into {index: (term, command)} maps
# ---------------------------------------------------------------------------
LINE_RE = re.compile(
    r"Index:\s*(\d+),\s*Term:\s*(\d+),\s*Command:\s*([^,]+)"
)

logs: dict[str, dict[int, tuple[int, str]]] = {}

for fname in filenames:
    path = Path(fname)
    entries: dict[int, tuple[int, str]] = {}
    if not path.is_file():
        print(f"[Warning] File not found: {fname}")
        logs[fname] = entries
        continue

    with path.open() as fh:
        for ln, line in enumerate(fh, 1):
            m = LINE_RE.search(line)
            if not m:
                continue
            idx   = int(m.group(1))
            term  = int(m.group(2))
            cmd   = m.group(3).strip()
            if idx in entries:
                print(f"[Warn] duplicate index {idx} in {fname}@{ln} – "
                      "overwriting previous value")
            entries[idx] = (term, cmd)
    logs[fname] = entries

# ---------------------------------------------------------------------------
# 3.  Majority‑based consistency check
# ---------------------------------------------------------------------------
def majority_consistent(all_logs: dict[str, dict[int, tuple[int, str]]]) -> bool:
    """Return True if every index has a quorum‑agreed value (or quorum‑agreed missing)."""
    all_indices = set().union(*(d.keys() for d in all_logs.values()))
    overall_ok  = True

    for idx in sorted(all_indices):
        # Build a multiset of values; use sentinel for "missing"
        PRESENT  = lambda t_c: f"{t_c[0]}|{t_c[1]}"
        MISSING  = "<MISSING>"
        counter  = Counter()

        for ent in all_logs.values():
            counter[MISSING if idx not in ent else PRESENT(ent[idx])] += 1

        # find dominant opinion
        value, votes = counter.most_common(1)[0]
        if votes >= QUORUM:
            continue      # quorum reached ⇒ this index is fine

        overall_ok = False
        print(f"Inconsistency @Index {idx}: no value reaches quorum "
              f"(counts: {dict(counter)})")

    return overall_ok


# ---------------------------------------------------------------------------
# 4.  Run the check & report
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ok = majority_consistent(logs)
    if ok:
        print(f"✅  Logs are majority‑consistent across {N_NODES} nodes (quorum={QUORUM}).")
    else:
        print(f"❌  Detected indices without a quorum agreement (quorum={QUORUM}).")
