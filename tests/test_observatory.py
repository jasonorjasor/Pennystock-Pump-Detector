"""Offline regression and workflow tests. No network or legacy writes."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
from pennystock.core import (normalize_bars, calculate_pump_score, explain,
                            outcome_from_bars, resolve_universe, metrics, score_bins)
from pennystock.calendar import sessions_between, completed_session, outcome_sessions
from pennystock.pipeline import scan, track, import_legacy, alerts_with_outcomes, demo
from pennystock.storage import read_csv, writer_lock, upsert_observations
from pennystock.history import analyze_episodes, backtest


def fixture():
    dates = sessions_between("2025-07-01", "2025-11-07")
    close = 10 + np.sin(np.arange(len(dates))) * .02
    volume = 10000 + np.arange(len(dates)) % 17 * 30
    close[-12], volume[-12] = 14, 1000000
    return pd.DataFrame({"Open": close, "High": close*1.01, "Low": close*.99,
                         "Close": close, "Volume": volume}, index=dates).rename_axis("Date")


class CoreTests(unittest.TestCase):
    def test_column_layouts(self):
        flat = fixture()
        for tuples in [[("ABC", c) for c in flat], [(c, "ABC") for c in flat]]:
            multi = flat.copy()
            multi.columns = pd.MultiIndex.from_tuples(tuples)
            pd.testing.assert_frame_equal(normalize_bars(multi, "ABC"), flat, check_freq=False)

    def test_missing_batch_ticker_rejected(self):
        a = fixture()
        batch = pd.concat({"ABC": a, "DEF": a}, axis=1)
        with self.assertRaises(ValueError):
            normalize_bars(batch, "MISSING")

    def test_duplicate_dates_rejected(self):
        with self.assertRaises(ValueError):
            normalize_bars(pd.concat([fixture(), fixture().iloc[:1]]))

    def test_explanation_and_historical_live_parity(self):
        import MAIN.pump_detector as historical
        import MAIN.tiered_scanner as live
        bars = fixture()
        a, b = historical.calculate_pump_score(bars), live.calculate_pump_score(bars)
        pd.testing.assert_frame_equal(a, b)
        row = a.iloc[-12]
        self.assertTrue(row.flag)
        self.assertEqual(sum(r["points"] for r in explain(row)), row.pump_score)
        self.assertLessEqual(row.pump_score, 130)

    def test_future_bars_do_not_change_earlier_features(self):
        bars = fixture()
        short = calculate_pump_score(bars.iloc[:-5])
        long = calculate_pump_score(bars)
        pd.testing.assert_frame_equal(short, long.iloc[:-5])

    def test_missing_volume_not_filled(self):
        bars = fixture()
        bars.iloc[-12, bars.columns.get_loc("Volume")] = np.nan
        scored = calculate_pump_score(bars)
        self.assertFalse(scored.iloc[-12].eligible)
        self.assertFalse(scored.iloc[-12].flag)

    def test_prior_baseline_excludes_current(self):
        bars = fixture()
        row = calculate_pump_score(bars).iloc[-12]
        self.assertAlmostEqual(row.vol_ratio, bars.iloc[-12].Volume / (bars.iloc[-32:-12].Volume.mean()+1e-9))

    def test_bounded_outcomes_and_consistent_entry(self):
        bars = fixture()
        day = bars.index[-12]
        expected = outcome_sessions(day)
        early = outcome_from_bars(bars.loc[:expected[-1]], day, expected, expected[-1])
        later = bars.copy()
        later.iloc[-1] = [1, 1, 1, 1, 100]
        late = outcome_from_bars(later, day, expected, later.index[-1])
        self.assertEqual(early, late)
        self.assertEqual(early["outcome"], "sharp_reversal")
        self.assertEqual(early["evaluation_entry_price"], 14)

    def test_day_five_is_provisional(self):
        bars = fixture()
        day = bars.index[-12]
        expected = outcome_sessions(day)
        result = outcome_from_bars(bars, day, expected, expected[5])
        self.assertEqual(result["state"], "provisional")
        self.assertIsNone(result["return_10d"])

    def test_missing_session_not_compressed(self):
        bars = fixture()
        day = bars.index[-12]
        expected = outcome_sessions(day)
        result = outcome_from_bars(bars.drop(expected[2]), day, expected, bars.index[-1])
        self.assertEqual(result["data_status"], "missing_or_invalid_session")
        self.assertNotEqual(result["state"], "final")

    def test_missing_entry_not_substituted(self):
        bars = fixture()
        day = bars.index[-12]
        result = outcome_from_bars(bars.drop(day), day, outcome_sessions(day), bars.index[-1])
        self.assertEqual(result["data_status"], "missing_entry")

    def test_universe_preserves_tiers_without_duplicates(self):
        tiers = {"tier1": ["A"], "tier2": ["B"], "tier3": []}
        monday = resolve_universe(tiers, ["A", "C"], "2025-11-10")
        self.assertEqual([r["ticker"] for r in monday], ["A", "B", "C"])
        self.assertEqual(monday[1]["tier"], "tier2")
        tuesday = resolve_universe(tiers, ["A"], "2025-11-11")
        self.assertEqual(len(tuesday), 1)
        self.assertEqual(len(resolve_universe(tiers, ["C"], "2025-11-10", "override")), 1)

    def test_metrics_and_open_score_bin(self):
        df = pd.DataFrame({"state": ["final", "final", "provisional"],
                           "outcome": ["sharp_reversal", "mixed", "pending"]})
        self.assertEqual(metrics(df)["rate"], 50)
        self.assertIsNone(metrics(df.iloc[2:])["rate"])
        self.assertEqual(str(score_bins(pd.Series([130])).iloc[0]), ">70")
        self.assertEqual(metrics(pd.DataFrame())["total"], 0)

    def test_holidays_and_early_close(self):
        with self.assertRaises(ValueError):
            completed_session("2025-12-25", now="2025-12-26T22:00:00Z")
        with self.assertRaises(ValueError):
            completed_session("2025-11-28", now="2025-11-28T18:15:00Z")
        self.assertEqual(str(completed_session("2025-11-28", now="2025-11-28T18:31:00Z").date()), "2025-11-28")

    def test_empty_episode_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = pd.DataFrame(columns=["ticker", "signal_date", "pump_score", "classification"])
            result = analyze_episodes(empty, tmp)
            self.assertTrue(result.empty)
            self.assertIn("coefficient_variation", pd.read_csv(Path(tmp)/"data/analysis/ticker_intervals.csv"))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        self.prices = self.base / "prices"
        self.prices.mkdir()
        self.bars = fixture()
        self.bars.reset_index().to_csv(self.prices / "ABC.csv", index=False)
        self.watch = self.base / "watchlist.txt"
        self.watch.write_text("ABC\n# comment\n")
        self.session = str(self.bars.index[-12].date())

    def tearDown(self):
        self.temp.cleanup()

    def scan(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return scan(self.workspace, self.session, watchlist=self.watch,
                        mode="override", prices_dir=self.prices)

    def test_scan_track_idempotence_and_freeze(self):
        self.assertEqual(self.scan()["state"], "complete")
        first = read_csv(self.workspace / "observations.csv")
        self.scan()
        pd.testing.assert_frame_equal(first, read_csv(self.workspace / "observations.csv"))
        self.assertEqual(len(first), 1)
        track(self.workspace, "2025-11-07", self.prices)
        alerts = alerts_with_outcomes(self.workspace)
        self.assertEqual(alerts.iloc[0].state, "final")
        saved = (self.workspace / "outcomes.csv").read_bytes()
        with patch("pennystock.pipeline.fetch_bars", side_effect=AssertionError("Final outcome must not fetch")):
            track(self.workspace, "2025-11-07", self.prices)
        self.assertEqual(saved, (self.workspace / "outcomes.csv").read_bytes())

    def test_failures_are_partial_and_do_not_erase_prior_outcomes(self):
        self.scan()
        dates = outcome_sessions(self.session)
        track(self.workspace, str(dates[5].date()), self.prices)
        before = read_csv(self.workspace / "outcomes.csv")
        with patch("pennystock.pipeline.fetch_bars", side_effect=ValueError("offline")):
            result = track(self.workspace, "2025-11-07", self.prices)
        self.assertEqual(result["state"], "partial")
        pd.testing.assert_frame_equal(before, read_csv(self.workspace / "outcomes.csv"))
        self.watch.write_text("ABC\nMISSING\n")
        self.assertEqual(self.scan()["state"], "partial")
        self.assertIn("fetch_failed", read_csv(self.workspace / "observations.csv").scan_status.values)

    def test_empty_workspace_tracker_report(self):
        track(self.workspace, "2025-11-07", self.prices)
        self.assertEqual(json.loads((self.workspace / "summary.json").read_text())["total"], 0)

    def test_demo_works_without_local_market_archive(self):
        with patch("pennystock.pipeline.ROOT", self.base), contextlib.redirect_stdout(io.StringIO()):
            result = demo(self.workspace)
        self.assertEqual(result["state"], "complete")
        metadata = json.loads((self.workspace / "workspace.json").read_text())
        self.assertEqual(metadata["demo_source"], "synthetic fictional data")
        alerts = alerts_with_outcomes(self.workspace)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts.iloc[0].state, "final")

    def test_backtest_shares_live_outcomes(self):
        with patch("pennystock.history.ROOT", self.base), contextlib.redirect_stdout(io.StringIO()):
            result = backtest("2025-07-01", "2025-11-07", ["ABC"], self.prices, "history")
        self.assertEqual(result["state"], "complete")
        master = pd.read_csv(self.base / "runs/history/data/signals_csv/MASTER_OUTCOMES.csv")
        signal = master[master.signal_date.eq(self.session)].iloc[0]
        self.assertEqual(signal.classification, "sharp_reversal")
        self.scan()
        track(self.workspace, "2025-11-07", self.prices)
        live = alerts_with_outcomes(self.workspace).iloc[0]
        self.assertEqual(signal.pump_score, live.pump_score)
        self.assertAlmostEqual(signal.return_10d, live.return_10d)

    def test_live_and_offline_cohorts_cannot_mix(self):
        self.scan()
        with self.assertRaisesRegex(ValueError, "separate workspaces"):
            scan(self.workspace, self.session, watchlist=self.watch, mode="override")

    def test_legacy_import_is_separate_and_outcomes_reset(self):
        legacy = self.base / "legacy.csv"
        pd.DataFrame([{"ticker": "ABC", "alert_date": self.session, "pump_score": 55,
                       "alert_price": 14, "outcome": "confirmed_pump"}]).to_csv(legacy, index=False)
        before = hashlib.sha256(legacy.read_bytes()).hexdigest()
        self.assertEqual(import_legacy(legacy, self.workspace), 1)
        self.assertEqual(alerts_with_outcomes(self.workspace).iloc[0].outcome, "pending")
        self.assertEqual(before, hashlib.sha256(legacy.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            import_legacy(legacy, self.workspace)

    def test_legacy_workspace_write_rejected_and_lock(self):
        (self.workspace / "data").mkdir(parents=True)
        with self.assertRaises(ValueError):
            with writer_lock(self.workspace):
                pass
        alternate = self.base / "other"
        with writer_lock(alternate):
            with self.assertRaises(RuntimeError):
                with writer_lock(alternate):
                    pass

    def test_dashboard_queue_metrics_and_notes(self):
        from streamlit.testing.v1 import AppTest
        self.scan()
        track(self.workspace, "2025-11-07", self.prices)
        with patch("pennystock.storage.ROOT", self.base), patch("pennystock.storage.DEFAULT_WORKSPACE", self.workspace):
            app = AppTest.from_file(str(ROOT / "dashboard/dashboard.py"), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "1")
            app.multiselect[0].set_value([]).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "1", "Queue filters must not change evaluation cohort")
            app.text_area[0].set_value("Observed volume anomaly; catalyst unknown.")
            app.text_input[0].set_value("https://www.sec.gov/")
            next(b for b in app.button if b.label == "Save note").click().run()
            self.assertFalse(app.exception)
            notes = json.loads((self.workspace / "notes.json").read_text())
            self.assertIn(f"ABC:{self.session}", notes)


if __name__ == "__main__":
    unittest.main()
