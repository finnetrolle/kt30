import unittest

from agent_eval import evaluate_case, load_cases_file, summarize_evaluations


class StarterEvalDatasetTests(unittest.TestCase):
    def test_starter_dataset_passes_deterministic_eval(self):
        entries = load_cases_file("evals/golden_cases.starter.json")

        evaluations = [
            evaluate_case(
                entry["payload"],
                case_id=entry["case_id"],
                source=entry["source"],
                expected=entry.get("expected"),
            )
            for entry in entries
        ]
        summary = summarize_evaluations(evaluations)

        self.assertGreaterEqual(len(entries), 4)
        self.assertEqual(summary["failed"], 0)
        self.assertIn("ai-kb-chatbot-rfp-real", {entry["case_id"] for entry in entries})


if __name__ == "__main__":
    unittest.main()
