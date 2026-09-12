import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
from pennystock.cli import daily
from pennystock.discovery import (ACTIVE_LIMIT, change_candidate, discovery_features,
    discover, initialize_registry, parse_directory, read_registry)
from pennystock.study import record_baselines, study_report, track_baselines
from pennystock.pipeline import scan


def bars(last_volume=1000000, last_close=4.0):
    dates = pd.bdate_range("2025-07-01", periods=70)
    close = np.full(len(dates), 2.0)
    volume = np.full(len(dates), 100000)
    close[-1], volume[-1] = last_close, last_volume
    return pd.DataFrame({"Date": dates, "Open": close, "High": close * 1.02,
        "Low": close * .98, "Close": close, "Volume": volume})


NASDAQ = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAA|Alpha Common Stock|Q|N|N|100|N|N\nWRTW|Wrt Warrants|Q|N|N|100|N|N\nTEST|Test Common|Q|Y|N|100|N|N\nFile Creation Time: 1|||||||\n"
OTHER = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\nBBB|Beta ADS|N|BBB|N|100|N|BBB\nFUND|Some Fund|A|FUND|N|100|N|FUND\nFile Creation Time: 1|||||||\n"


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.prices = self.root / "prices"
        self.symbols = self.root / "symbols"
        self.prices.mkdir(); self.symbols.mkdir()
        (self.symbols / "nasdaq.txt").write_text(NASDAQ)
        (self.symbols / "other.txt").write_text(OTHER)
        bars().to_csv(self.prices / "AAA.csv", index=False)
        bars(200000, 2.2).to_csv(self.prices / "BBB.csv", index=False)
        self.session = str(bars().Date.iloc[-1].date())
        self.watch = self.root / "watchlist.txt"
        self.watch.write_text("AAA\n")

    @staticmethod
    def review():
        return {"identity_checked": True, "liquidity_checked": True,
                "catalyst_category": "none_found", "corporate_action": "none_found",
                "data_quality": "complete", "evidence_url": "https://www.sec.gov/edgar/search/"}

    def test_directory_excludes_non_equity_products(self):
        rows = parse_directory(NASDAQ, "fixture") + parse_directory(OTHER, "fixture")
        self.assertEqual({r["symbol"] for r in rows}, {"AAA", "BBB"})
        self.assertEqual(next(r for r in rows if r["symbol"] == "BBB")["security_type"], "ADR/ADS")

    def test_features_do_not_use_future_bars(self):
        frame = bars().set_index("Date")
        day = frame.index[-2]
        first = discovery_features(frame.loc[:day], day)
        changed = frame.copy(); changed.iloc[-1, changed.columns.get_loc("Volume")] = 99999999
        self.assertEqual(first, discovery_features(changed, day))

    def test_discover_is_deterministic_and_requires_review(self):
        first = discover(self.workspace, self.session, symbols_dir=self.symbols, prices_dir=self.prices)
        second = discover(self.workspace, self.session, symbols_dir=self.symbols, prices_dir=self.prices)
        self.assertEqual(first["nominated_candidates"], second["nominated_candidates"])
        self.assertTrue(second["cached"])
        state = read_registry(self.workspace)
        self.assertEqual(next(r for r in state["candidates"] if r["ticker"] == "AAA")["state"], "needs_review")
        self.assertFalse((self.workspace / "approved_watchlist.txt").read_text())
        change_candidate(self.workspace, "AAA", "approved", "Reviewed identity and price chart", review=self.review())
        self.assertEqual((self.workspace / "approved_watchlist.txt").read_text(), "AAA\n")

    def test_session_snapshot_is_stable(self):
        initialize_registry(self.workspace, self.watch)
        with contextlib.redirect_stdout(io.StringIO()):
            scan(self.workspace, self.session, watchlist=self.watch, prices_dir=self.prices)
        state = read_registry(self.workspace)
        state["candidates"].append({"ticker": "BBB", "state": "needs_review", "updated_at": "x",
            "reason": "x", "reviewer": "x", "first_seen_at": "x", "quiet_comparison": False})
        from pennystock.storage import save_json
        save_json(self.workspace / "candidates.json", state)
        change_candidate(self.workspace, "BBB", "approved", "Reviewed identity, liquidity, and chart", review=self.review())
        with contextlib.redirect_stdout(io.StringIO()):
            result = scan(self.workspace, self.session, watchlist=self.watch, prices_dir=self.prices)
        self.assertEqual([r["ticker"] for r in result["universe"]], ["AAA"])

    def test_capacity_preserves_history(self):
        initialize_registry(self.workspace, self.watch)
        from pennystock.discovery import _transition
        state = read_registry(self.workspace)
        for n in range(1, ACTIVE_LIMIT):
            _transition(state, f"X{n}", "approved", "fixture", "test")
        _transition(state, "OVER", "needs_review", "fixture", "test")
        from pennystock.storage import save_json
        save_json(self.workspace / "candidates.json", state)
        with self.assertRaisesRegex(ValueError, "capacity"):
            change_candidate(self.workspace, "OVER", "approved", "reviewed", review=self.review())
        self.assertEqual(read_registry(self.workspace)["candidates"][-1]["state"], "needs_review")

    def test_daily_is_idempotent(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(daily(self.workspace, self.session, self.prices, self.watch)["state"], "complete")
            self.assertEqual(daily(self.workspace, self.session, self.prices, self.watch)["state"], "complete")
        observations = pd.read_csv(self.workspace / "observations.csv")
        self.assertEqual(len(observations), 1)
        baselines = pd.read_csv(self.workspace / "baseline_outcomes.csv")
        self.assertEqual(len(baselines), 2)
        self.assertEqual(study_report(self.workspace, self.session)["completed_sessions"], 1)

    def test_structured_review_is_required_and_preserved(self):
        discover(self.workspace, self.session, symbols_dir=self.symbols, prices_dir=self.prices)
        with self.assertRaisesRegex(ValueError, "Structured review"):
            change_candidate(self.workspace, "AAA", "approved", "Too vague")
        change_candidate(self.workspace, "AAA", "approved", "Identity and liquidity verified", review=self.review())
        transition = read_registry(self.workspace)["transitions"][-1]
        self.assertEqual(transition["review"]["data_quality"], "complete")

    def test_dashboard_candidate_approval(self):
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        from pennystock import storage
        discover(self.workspace, self.session, symbols_dir=self.symbols, prices_dir=self.prices)
        dashboard = Path(__file__).resolve().parents[1] / "dashboard/dashboard.py"
        with patch.object(storage, "ROOT", self.root), patch.object(storage, "DEFAULT_WORKSPACE", self.workspace):
            app = AppTest.from_file(str(dashboard)).run(timeout=20)
            self.assertFalse(app.exception)
            next(x for x in app.text_input if x.label == "Candidate review reason").set_value("Reviewed fixture identity and chart")
            next(x for x in app.checkbox if x.label == "Identity and listing checked").check()
            next(x for x in app.checkbox if x.label == "Liquidity and chart checked").check()
            next(x for x in app.selectbox if x.label == "Recent catalyst").select("none_found")
            next(x for x in app.selectbox if x.label == "Corporate action").select("none_found")
            next(x for x in app.selectbox if x.label == "Data quality").select("complete")
            next(x for x in app.button if x.label == "Approve candidate").click().run(timeout=20)
            self.assertFalse(app.exception)
            self.assertIn("AAA", (self.workspace / "approved_watchlist.txt").read_text())


if __name__ == "__main__":
    unittest.main()
