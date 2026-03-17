import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from progress_tracker import ProgressTracker, ProgressTrackerStore


class ProgressTrackerPersistenceTests(unittest.TestCase):
    def tearDown(self):
        ProgressTrackerStore._instance = None

    def test_persisted_events_can_be_read_from_another_tracker_instance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task-1"
            tracker = ProgressTracker("task-1", storage_dir=task_dir)

            tracker.stage("stage one")
            tracker.info("still working")
            tracker.complete("/results/abc", "abc")

            mirror = ProgressTracker.from_existing("task-1", task_dir)
            events, _ = mirror.read_events_since(0)

            self.assertEqual(
                [event["type"] for event in events],
                ["stage", "info", "complete"]
            )

            mirror.refresh_state()
            self.assertTrue(mirror.is_finished)

    def test_restores_stage_usage_and_request_counters_from_meta(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task-2"
            tracker = ProgressTracker("task-2", storage_dir=task_dir)

            tracker.stage("stage one")
            tracker.usage("planner", {"prompt_tokens": 11, "completion_tokens": 4})

            mirror = ProgressTracker.from_existing("task-2", task_dir)
            summary = mirror.get_usage_summary()

            self.assertEqual(summary["totals"]["total_tokens"], 15)
            self.assertEqual(summary["request_count"], 1)
            self.assertEqual(summary["stages"][0]["stage_id"], 1)
            self.assertEqual(summary["stages"][0]["request_count"], 1)
            self.assertEqual(summary["stages"][0]["usage"]["prompt_tokens"], 11)

            mirror.stage("stage two")
            next_summary = mirror.get_usage_summary()

            self.assertEqual([stage["stage_id"] for stage in next_summary["stages"]], [1, 2])
            self.assertEqual(next_summary["stages"][1]["message"], "stage two")

    def test_tracker_recreates_storage_dir_if_removed_mid_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task-3"
            tracker = ProgressTracker("task-3", storage_dir=task_dir)

            shutil.rmtree(task_dir)
            tracker.info("recovered after missing directory")

            self.assertTrue(task_dir.exists())
            self.assertTrue((task_dir / ProgressTracker.EVENTS_FILENAME).exists())

    def test_llm_request_and_response_events_include_previews(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            task_dir = Path(temp_dir) / "task-llm"
            tracker = ProgressTracker("task-llm", storage_dir=task_dir)

            tracker.llm_request(
                "planner",
                "gpt-test",
                "Сформируй подробный план проекта " * 20,
                system_prompt="Ты старший планировщик ИСР",
                data={"attempt": 1}
            )
            tracker.llm_response(
                "planner",
                "gpt-test",
                "Готово, сформировал каркас WBS " * 20,
                elapsed_seconds=4.25,
                usage={"prompt_tokens": 123, "completion_tokens": 45},
                data={"attempt": 1}
            )

            mirror = ProgressTracker.from_existing("task-llm", task_dir)
            events, _ = mirror.read_events_since(0)

            self.assertEqual([event["type"] for event in events], ["agent", "agent"])
            self.assertEqual(events[0]["data"]["llm_event"], "request_started")
            self.assertEqual(events[1]["data"]["llm_event"], "response_received")
            self.assertLessEqual(len(events[0]["data"]["prompt_preview"]), 480)
            self.assertEqual(events[1]["data"]["usage"]["total_tokens"], 168)

    def test_cleanup_skips_unfinished_trackers_even_if_they_are_old(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProgressTrackerStore(storage_root=temp_dir, ttl_seconds=60)
            tracker = store.create("task-4")
            tracker.stage("still running")

            task_dir = Path(temp_dir) / "task-4"
            meta_path = task_dir / ProgressTracker.META_FILENAME
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)

            old_timestamp = time.time() - 24 * 60 * 60
            meta["created_at"] = old_timestamp
            meta["updated_at"] = old_timestamp
            with open(meta_path, "w", encoding="utf-8") as handle:
                json.dump(meta, handle, ensure_ascii=False, indent=2)

            store.cleanup(max_age_seconds=60)

            self.assertTrue(task_dir.exists())

    def test_cleanup_removes_finished_trackers_after_retention_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ProgressTrackerStore(storage_root=temp_dir, ttl_seconds=60)
            tracker = store.create("task-5")
            tracker.complete("/results/task-5", "task-5")

            task_dir = Path(temp_dir) / "task-5"
            meta_path = task_dir / ProgressTracker.META_FILENAME
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)

            old_timestamp = time.time() - 24 * 60 * 60
            meta["created_at"] = old_timestamp
            meta["updated_at"] = old_timestamp
            with open(meta_path, "w", encoding="utf-8") as handle:
                json.dump(meta, handle, ensure_ascii=False, indent=2)

            store.cleanup(max_age_seconds=60)

            self.assertFalse(task_dir.exists())


if __name__ == "__main__":
    unittest.main()
