import tempfile
import unittest

from rate_limiter import get_rate_limiter


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.limiter = get_rate_limiter(f"{self.temp_dir.name}/rate_limits.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_blocks_after_limit_is_reached(self):
        first = self.limiter.check("login", "127.0.0.1", limit=2, window_seconds=60)
        second = self.limiter.check("login", "127.0.0.1", limit=2, window_seconds=60)
        third = self.limiter.check("login", "127.0.0.1", limit=2, window_seconds=60)

        self.assertTrue(first["allowed"])
        self.assertTrue(second["allowed"])
        self.assertFalse(third["allowed"])


if __name__ == "__main__":
    unittest.main()
