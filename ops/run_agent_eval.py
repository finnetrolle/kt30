"""
CLI for deterministic offline evaluation of agent-generated WBS results.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent_eval import (
    attach_llm_judge_results,
    evaluate_case,
    load_analysis_runs,
    load_cases_file,
    summarize_evaluations,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline evaluation for agent-generated WBS results.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--cases", help="Path to golden cases JSON file.")
    source_group.add_argument("--analysis-runs", help="Path to analysis_runs directory with final_result.json artifacts.")
    parser.add_argument("--output", help="Optional path to write the JSON report.")
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Run an additional LLM judge over trace artifacts when available.",
    )
    parser.add_argument("--judge-model", help="Optional model override for the LLM judge.")
    parser.add_argument("--judge-base-url", help="Optional base URL override for the LLM judge.")
    parser.add_argument("--judge-api-key", help="Optional API key override for the LLM judge.")
    parser.add_argument(
        "--max-judge-cases",
        type=int,
        default=None,
        help="Optional cap on the number of cases sent to the LLM judge.",
    )
    parser.add_argument(
        "--fail-on-failing-cases",
        action="store_true",
        help="Exit with code 1 if at least one case fails the rubric.",
    )
    args = parser.parse_args()

    entries = load_cases_file(args.cases) if args.cases else load_analysis_runs(args.analysis_runs)
    evaluations = [
        evaluate_case(
            entry["payload"],
            case_id=entry["case_id"],
            source=entry["source"],
            expected=entry.get("expected"),
        )
        for entry in entries
    ]
    if args.llm_judge:
        evaluations = attach_llm_judge_results(
            evaluations,
            entries,
            model=args.judge_model,
            base_url=args.judge_base_url,
            api_key=args.judge_api_key,
            max_cases=args.max_judge_cases,
        )
    summary = summarize_evaluations(evaluations)
    report = {
        "summary": summary,
        "evaluations": evaluations,
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)

    print(
        f"Cases: {summary['cases']}, passed: {summary['passed']}, "
        f"failed: {summary['failed']}, average_score: {summary['average_score']}, "
        f"average_combined_score: {summary.get('average_combined_score', summary['average_score'])}, "
        f"judged_cases: {summary.get('judged_cases', 0)}"
    )
    for evaluation in evaluations:
        status = "PASS" if evaluation["passed"] else "FAIL"
        score_text = f"score={evaluation['score']}"
        if "combined_score" in evaluation:
            score_text += f" combined={evaluation['combined_score']}"
        if evaluation.get("llm_judge", {}).get("success"):
            score_text += f" judge={evaluation['llm_judge']['score']}"
        elif evaluation.get("llm_judge", {}).get("skipped"):
            score_text += f" judge=skipped({evaluation['llm_judge'].get('reason', 'unknown')})"
        print(f"[{status}] {evaluation['case_id']}: {score_text} source={evaluation['source']}")

    if args.fail_on_failing_cases and summary["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
