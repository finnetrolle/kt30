import tempfile
import unittest
from pathlib import Path

from progress_tracker import ProgressTracker


class ProgressTrackerPersistenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
