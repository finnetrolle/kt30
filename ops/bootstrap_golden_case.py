"""
CLI for bootstrapping golden cases from saved analysis results.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent_eval import (  # noqa: E402
    build_golden_case_from_payload,
    load_result_payload_from_source,
    upsert_golden_case_file,
)


def _default_case_id(source_path: str) -> str:
    path = Path(source_path)
    if path.is_dir():
        return path.name
    if path.name == "final_result.json":
        return path.parent.name
    return path.stem


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or append one golden case from analysis result artifacts.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to analysis_runs/<run> directory or a final_result.json file.",
    )
    parser.add_argument(
        "--cases-file",
        required=True,
        help="Target golden cases JSON file.",
    )
    parser.add_argument(
        "--case-id",
        help="Optional stable case identifier. Defaults to the source run directory name.",
    )
    parser.add_argument(
        "--total-hours-tolerance",
        type=float,
        default=0.15,
        help="Tolerance used to seed total_hours_range around the observed total hours.",
    )
    parser.add_argument(
        "--max-requirements",
        type=int,
        default=12,
        help="Maximum number of requirement_ids to include in expected.required_requirement_ids.",
    )
    parser.add_argument(
        "--min-total-score",
        type=float,
        default=75.0,
        help="Minimum total deterministic score required for the case to pass.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace an existing case with the same case_id.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the generated case JSON after writing it to the target file.",
    )
    args = parser.parse_args()

    loaded = load_result_payload_from_source(args.source)
    case_id = args.case_id or _default_case_id(args.source)
    case = build_golden_case_from_payload(
        loaded["payload"],
        case_id=case_id,
        source=loaded["source"],
        trace_dir=loaded["trace_dir"],
        total_hours_tolerance=args.total_hours_tolerance,
        max_requirements=args.max_requirements,
        min_total_score=args.min_total_score,
    )
    result = upsert_golden_case_file(
        args.cases_file,
        case,
        replace_existing=args.replace_existing,
    )

    print(
        f"{result['action']}: case_id={result['case_id']} "
        f"cases_file={result['cases_file']} cases_count={result['cases_count']}"
    )
    if args.stdout:
        print(json.dumps(case, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
