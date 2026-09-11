import copy
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
from pennystock.social import (coverage_status, features, import_payload, read_state,
                               resolve, social_demo, social_features, timestamp,
                               timeline, universe_init, universe_update)
from pennystock.storage import save_csv
import pandas as pd


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "demo"
        social_demo(self.workspace)
        self.state = read_state(self.workspace)
        self.end = "2025-11-07T18:00:00+00:00"
        self.payload = json.loads((self.workspace / "example_import.json").read_text())

    def result(self, state=None, **kwargs):
        return features(state or self.state, "DEMO", "fixture", self.end, **kwargs)

    def test_demo_score_is_explained_and_independent_of_market(self):
        result = self.result()
        self.assertEqual(result["mention_count_observed"], 12)
        self.assertEqual(result["unique_authors_observed"], 12)
        self.assertEqual(result["label"], "Elevated attention")
        self.assertEqual(result["social_attention_score"], sum(r["points"] for r in result["components"]))
        self.assertFalse((self.workspace / "observations.csv").exists())
        self.assertEqual(result["analysis_mode"], "retrospective_import")
        self.assertEqual(result["data_kind"], "synthetic")

    def test_idempotent_import_preserves_capture_times_and_hashes(self):
        before = (self.workspace / "social.json").read_bytes()
        result = import_payload(self.workspace, self.payload)
        self.assertEqual(result["added"], {"posts": 0, "coverage": 0})
        self.assertEqual(before, (self.workspace / "social.json").read_bytes())
        self.assertNotIn("author_id", self.state["posts"][0])

    def test_conflicting_duplicate_is_atomic(self):
        before = (self.workspace / "social.json").read_bytes()
        self.payload["observations"][-1]["text"] = "$DEMO changed evidence"
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            import_payload(self.workspace, self.payload)
        self.assertEqual(before, (self.workspace / "social.json").read_bytes())

    def test_invalid_batch_does_not_partially_import(self):
        before = (self.workspace / "social.json").read_bytes()
        self.payload["observations"][0]["published_at"] = "2025-01-01T12:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            import_payload(self.workspace, self.payload)
        self.assertEqual(before, (self.workspace / "social.json").read_bytes())

    def test_missing_is_not_zero(self):
        self.state["posts"] = []
        self.state["coverage"] = []
        result = self.result()
        self.assertEqual(result["coverage_status"], "not_collected")
        self.assertFalse(result["confirmed_zero"])
        self.assertIsNone(result["social_attention_score"])

    def test_complete_zero_is_distinct_from_zero_baseline(self):
        self.state["posts"] = []
        result = self.result()
        self.assertTrue(result["confirmed_zero"])
        self.assertEqual(result["baseline_status"], "zero_baseline")
        self.assertIsNone(result["social_attention_score"])

    def test_outage_does_not_become_normal(self):
        for status in ("failed", "unavailable"):
            self.state["coverage"][0]["status"] = status
            result = self.result()
            self.assertEqual(result["coverage_status"], status)
            self.assertEqual(result["label"], "Insufficient coverage")

    def test_partial_interval_is_incomplete(self):
        self.state["coverage"][0]["start"] = "2025-11-07T17:00:00+00:00"
        self.assertEqual(self.result()["coverage_status"], "not_collected")

    def test_adjacent_intervals_cover_window(self):
        a = copy.deepcopy(self.state["coverage"][0])
        b = copy.deepcopy(a)
        a["end"] = "2025-11-07T12:00:00+00:00"
        b["start"] = a["end"]
        self.state["coverage"] = [a, b]
        self.assertEqual(self.result()["coverage_status"], "complete")

    def test_insufficient_history_does_not_invent_growth(self):
        self.state["coverage"][0]["start"] = "2025-11-06T18:00:00+00:00"
        result = self.result()
        self.assertEqual(result["baseline_status"], "insufficient_baseline")
        self.assertIsNone(result["values"]["mention_growth"])
        self.assertIsNone(result["social_attention_score"])

    def test_collection_cutoff_prevents_using_later_arrivals(self):
        result = self.result(known_at="2025-11-07T18:00:00+00:00")
        self.assertEqual(result["mention_count_observed"], 12)
        self.state["posts"][-1]["collected_at"] = "2025-11-08T18:00:00+00:00"
        self.assertEqual(self.result(known_at=self.end)["mention_count_observed"], 11)

    def test_timezone_equivalence(self):
        a = self.result()
        b = features(self.state, "DEMO", "fixture", "2025-11-07T10:00:00-08:00")
        self.assertEqual(a["start"], b["start"])
        self.assertEqual(a["values"], b["values"])

    def test_ambiguous_and_multiple_symbols_are_not_counted(self):
        universe = [{"ticker": "CAN", "issuer": None}, {"ticker": "FEMY", "issuer": None}]
        self.assertIsNone(resolve("CAN this work?", universe)[0])
        self.assertEqual(resolve("$CAN activity", universe)[0], "CAN")
        self.assertIsNone(resolve("$CAN and $FEMY", universe)[0])
        self.assertIsNone(resolve("$CANDY", universe)[0])
        self.assertEqual(resolve("FEMY activity", universe)[0], "FEMY")

    def test_query_scopes_do_not_mix(self):
        other = copy.deepcopy(self.state["coverage"][0])
        other["query_scope"] = "different-query"
        self.state["coverage"].append(other)
        with self.assertRaisesRegex(ValueError, "Multiple query"):
            self.result()
        result = self.result(query_scope="different-query")
        self.assertEqual(result["mention_count_observed"], 0)

    def test_unknown_authors_cannot_invent_author_growth(self):
        self.state["posts"][-1]["author_hash"] = None
        result = self.result()
        self.assertIsNone(result["values"]["author_growth"])
        self.assertIsNone(result["social_attention_score"])

    def test_cannot_mix_synthetic_with_research(self):
        self.payload["data_kind"] = "research"
        with self.assertRaisesRegex(ValueError, "separate|cannot share"):
            import_payload(self.workspace, self.payload)

    def test_universe_transition_preserves_versions(self):
        result = universe_update(self.workspace, "DEMO", "Retired test candidate", membership="archived")
        self.assertEqual(result["version"], 2)
        self.assertIsNotNone(result["removed_at"])
        result = universe_update(self.workspace, "DEMO", "Revisit candidate")
        self.assertIsNone(result["removed_at"])
        self.assertEqual(len(read_state(self.workspace)["universe_history"]), 3)
        with self.assertRaisesRegex(ValueError, "validation source"):
            universe_update(self.workspace, "DEMO", "Guess", security_status="active")

    def test_watchlist_snapshot_is_immutable(self):
        watchlist = Path(self.temp.name) / "watchlist.txt"
        watchlist.write_text("FEMY\nCAN\n", encoding="utf-8")
        universe_init(self.workspace, watchlist)
        watchlist.write_text("OTHER\n", encoding="utf-8")
        universe_init(self.workspace, watchlist)
        state = read_state(self.workspace)
        self.assertEqual(state["watchlist_snapshot"]["tickers"], ["CAN", "FEMY"])
        self.assertTrue(all(r["security_status"] == "unverified" for r in state["universe"]))

    def test_timeline_preserves_actual_evaluation_time(self):
        save_csv(self.workspace / "observations.csv", pd.DataFrame([{
            "ticker": "DEMO", "observed_at": "2025-11-07T20:00:00+00:00",
            "session": "2025-11-07", "scan_status": "no_signal", "pump_score": 10,
            "score_version": "activity-v2", "volume": 1000, "alert_price": 2}]))
        result = timeline(self.workspace, "DEMO")
        times = [timestamp(r["event_at"]) for r in result["events"]]
        self.assertEqual(times, sorted(times))
        evaluation = next(r for r in result["events"] if r["type"] == "social_evaluation")
        self.assertGreater(timestamp(evaluation["event_at"]), timestamp(evaluation["window_end"]))
        self.assertEqual(sum(r["type"] == "market_observation" for r in result["events"]), 1)

    def test_every_supported_window_is_finite_json(self):
        for window in ("1h", "6h", "24h", "7d"):
            json.dumps(self.result(window=window), allow_nan=False)

    def test_social_dashboard_without_market_alerts(self):
        from streamlit.testing.v1 import AppTest
        from pennystock import storage
        dashboard = Path(__file__).resolve().parents[1] / "dashboard/dashboard.py"
        with patch.object(storage, "ROOT", Path(self.temp.name)), patch.object(storage, "DEFAULT_WORKSPACE", self.workspace):
            app = AppTest.from_file(str(dashboard)).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("SYNTHETIC" in r.value for r in app.warning))
            self.assertTrue(any("Elevated attention" in r.value for r in app.markdown))

    def test_import_first_workspace_accepts_market_scan(self):
        from pennystock.pipeline import scan
        workspace = Path(self.temp.name) / "research"
        watchlist = Path(self.temp.name) / "watchlist.txt"
        watchlist.write_text("DEMO\n", encoding="utf-8")
        universe_init(workspace, watchlist)
        payload = copy.deepcopy(self.payload)
        payload["data_kind"] = "research"
        import_payload(workspace, payload)
        with patch("pennystock.pipeline.fetch_bars", side_effect=ValueError("Deliberate offline test failure")):
            result = scan(workspace, session="2025-11-07", watchlist=watchlist, mode="override")
        self.assertEqual(result["state"], "partial")
        self.assertEqual(read_state(workspace)["data_kind"], "research")

    def test_synthetic_workspace_rejects_market_scan_before_download(self):
        from pennystock.pipeline import scan
        watchlist = Path(self.temp.name) / "watchlist.txt"
        watchlist.write_text("DEMO\n", encoding="utf-8")
        with patch("pennystock.pipeline.fetch_bars") as fetch:
            with self.assertRaisesRegex(ValueError, "score version"):
                scan(self.workspace, session="2025-11-07", watchlist=watchlist, mode="override")
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
