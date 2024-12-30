from __future__ import annotations

import pathlib
import json
import sys
from typing import Any


def check_reports(reports: list[dict[str, Any]]) -> list[str]:
    if not reports:
        return []
    errors = []

    all_group_counts = sorted({r["total_groups"] for r in reports})
    if len(all_group_counts) != 1:
        errors.append(
            f"Different amount of groups specified between runs: {', '.join(map(str, all_group_counts))}"
        )

    if not all(r["collected"] == reports[0]["collected"] for r in reports):
        errors.append("Collected different items between runs")
    else:
        all_selected = [item for report in reports for item in report["selected"]]
        if all_selected != reports[0]["collected"]:
            errors.append("Items missing during collection")

    return errors


def check(report_dir: pathlib.Path) -> list[str]:
    reports: list[dict[str, Any]] = [
        json.loads(f.read_bytes())
        for f in report_dir.glob("pytest_cdist_report_*.json")
    ]
    return check_reports(reports)


def main() -> None:
    errors = check(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    if errors:
        print("Errors during pytest-cdist check")
        for error in errors:
            print(error)
        quit(1)
    else:
        print("Pytest-cdist check found no issues")
