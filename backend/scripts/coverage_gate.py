"""NFR-MAINT-001 in CI (Phase 9b): line coverage of policies and services, and overall.

The PRD asks for ≥ 90% (policies, services) and ≥ 80% (overall). The floors here sit just
under what the suite measured on 2026-11-12 (policies 100%, services 97.6%, overall 98.3%),
so a drop is noticed long before the PRD minimum. Raise them as coverage grows; lowering one
needs a reason in the PR. Reads the data the test steps wrote (`.coverage`).
"""

import json
import sys
import tempfile
from pathlib import Path

from coverage import Coverage

FLOORS = {"app/policies/": 98.0, "app/services/": 95.0, "": 95.0}  # "" is everything
NFR_MINIMUMS = {"app/policies/": 90.0, "app/services/": 90.0, "": 80.0}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "coverage.json"
        data = Coverage()
        data.load()
        data.json_report(outfile=str(report))
        files = json.loads(report.read_text())["files"]
    failed = False
    for prefix, floor in FLOORS.items():
        if floor < NFR_MINIMUMS[prefix]:
            raise SystemExit(f"{prefix or 'overall'}: a floor can't sit under the PRD minimum")
        chosen = [v["summary"] for f, v in files.items() if f.startswith(prefix)]
        statements = sum(s["num_statements"] for s in chosen)
        covered = sum(s["covered_lines"] for s in chosen)
        percent = 100 * covered / statements if statements else 0.0
        label = prefix or "overall"
        status = "ok" if percent >= floor else "BELOW FLOOR"
        minimum = NFR_MINIMUMS[prefix]
        print(f"{label:15} {percent:6.2f}%  (floor {floor}%, PRD {minimum}%)  {status}")
        failed |= percent < floor
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
