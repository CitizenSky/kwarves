import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from refresh_exofop_catalog import compare_period, fetch_matches, refresh_catalog, tic_number


class CatalogTests(unittest.TestCase):
    def test_tic(self):
        self.assertEqual(tic_number("TIC 75878355"), 75878355)
        self.assertIsNone(tic_number("not-a-tic"))

    def test_period_statuses(self):
        rows = [{"source": "CONFIRMED", "name": "planet b", "periodDays": 9.229198}]
        self.assertEqual(compare_period(9.2293, rows), "PERIOD_MATCH_REVIEW_REQUIRED")
        self.assertEqual(compare_period(18, rows), "DIFFERENT_PERIOD_REVIEW_REQUIRED")
        self.assertEqual(compare_period(None, rows), "PERIOD_NOT_AVAILABLE")
        self.assertEqual(compare_period(10, []), "NO_HOST_MATCH")

    def test_multiple_planets_and_all_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = {"candidates": [{"tic": 11}, {"tic": 22}, {"tic": 33}]}
            for tic, period in [(11, 9.2293), (22, 20), (33, 5)]:
                (root / f"TIC_{tic}.json").write_text(json.dumps({
                    "tic": tic, "period": period,
                    "astroMonitor": {"exoFopMatch": False}
                }))
            matches = {
                11: [{"source": "TOI", "name": "1.01", "periodDays": 2},
                     {"source": "CONFIRMED", "name": "planet b", "periodDays": 9.229198}],
                22: [{"source": "CONFIRMED", "name": "planet c", "periodDays": 3}],
            }
            with patch("refresh_exofop_catalog.fetch_matches", return_value=matches):
                self.assertEqual(refresh_catalog(summary, root, "2026-11-16T00:00:00Z"), 3)
                self.assertEqual(refresh_catalog(summary, root, "2026-11-16T00:00:00Z"), 0)
            a = json.loads((root / "TIC_11.json").read_text())["astroMonitor"]
            b = json.loads((root / "TIC_22.json").read_text())["astroMonitor"]
            c = json.loads((root / "TIC_33.json").read_text())["astroMonitor"]
            self.assertTrue(a["exoFopMatch"])
            self.assertEqual(a["exoFopPeriodStatus"], "PERIOD_MATCH_REVIEW_REQUIRED")
            self.assertEqual(b["exoFopPeriodStatus"], "DIFFERENT_PERIOD_REVIEW_REQUIRED")
            self.assertFalse(c["exoFopMatch"])

    def test_failed_catalog_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "TIC_11.json"
            original = '{"tic":11,"astroMonitor":{"exoFopMatch":true}}'
            path.write_text(original)
            with patch("refresh_exofop_catalog.fetch_matches", side_effect=OSError("offline")):
                with self.assertRaises(OSError):
                    refresh_catalog({"candidates": [{"tic": 11}]}, root, "today")
            self.assertEqual(path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
