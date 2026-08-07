"""Run the reproducible compiler evaluation and optionally persist JSON evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from roboweaver.research.evaluation import run_research_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_research_evaluation().to_dict()
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
