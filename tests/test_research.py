import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
from pennystock.research import (attention_queue, readiness, research_readiness,
                                 review_evaluation, combined_classification)
from pennystock.social import (import_payload, parse_import, preview_import, read_state,
                               social_demo, timestamp)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "demo"
        social_demo(self.workspace)
        self.state = read_state(self.workspace)
        self.payload = json.loads((self.workspace / "example_import.json").read_text())
        self.end = "2025-11-07T18:00:00+00:00"

    def test_preview_does_not_write_and_matches_commit(self):
        before = (self.workspace / "social.json").read_bytes()
        preview = preview_import(self.workspace, self.payload)
        self.assertEqual(before, (self.workspace / "social.json").read_bytes())
        self.assertEqual(preview, import_payload(self.workspace, self.payload))
        self.assertNotIn("author_salt", preview)

    def test_preview_does_not_create_destination(self):
        dest = Path(self.temp.name) / "absent"
        preview_import(dest, {"schema_version": 1, "data_kind": "research", "observations": [], "coverage": []})
        self.assertFalse(dest.exists())

    def test_default_workspace_cannot_become_synthetic(self):
        from pennystock import social
        with patch.object(social, "DEFAULT_WORKSPACE", self.workspace):
            with self.assertRaisesRegex(ValueError, "default research"):
                preview_import(self.workspace, self.payload)
            with self.assertRaisesRegex(ValueError, "default research"):
                import_payload(self.workspace, self.payload)

    def test_queue_flags_new_evidence_without_changing_score(self):
        payload = copy.deepcopy(self.payload)
        payload["observations"][-1]["source_post_id"] = "arrived-later"
        import_payload(self.workspace, payload)
        row = attention_queue(read_state(self.workspace))[0]
        self.assertTrue(row["new_evidence_since_evaluation"])
        self.assertEqual(row["social_attention_score"], self.state["evaluations"][0]["social_attention_score"])

    def test_commit_revalidates_after_concurrent_change(self):
        payload = copy.deepcopy(self.payload)
        row = payload["observations"][-1]
        row["source_post_id"] = "new-post"
        payload["observations"] = [row]
        self.assertEqual(preview_import(self.workspace, payload)["added"]["posts"], 1)
        changed = copy.deepcopy(payload)
        changed["observations"][0]["text"] = "$DEMO different content from another import"
        import_payload(self.workspace, changed)
        before = (self.workspace / "social.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            import_payload(self.workspace, payload)
        self.assertEqual(before, (self.workspace / "social.json").read_bytes())

    def test_upload_parser_rejects_bad_encoding_and_nonfinite_json(self):
        for content in (b"\xff", b'{"value": NaN}', b"not json"):
            with self.assertRaises(ValueError):
                parse_import(content)
        self.assertEqual(parse_import(b'\xef\xbb\xbf{"schema_version": 1}'), {"schema_version": 1})

    def test_malformed_schema_and_coverage_return_validation_errors(self):
        payload = copy.deepcopy(self.payload)
        payload["schema_version"] = True
        with self.assertRaises(ValueError):
            preview_import(self.workspace, payload)
        payload["schema_version"] = 1
        payload["coverage"][0]["status"] = []
        with self.assertRaisesRegex(ValueError, "coverage status"):
            preview_import(self.workspace, payload)

    def test_readiness_explains_missing_data_without_writes(self):
        before = (self.workspace / "social.json").read_bytes()
        result = research_readiness(self.workspace, as_of="2025-12-01T18:00:00Z")
        row = result["rows"][0]
        self.assertEqual(row["coverage_status"], "not_collected")
        self.assertEqual(row["listing_review"], "unverified")
        self.assertGreaterEqual(len(row["next_actions"]), 2)
        self.assertEqual(before, (self.workspace / "social.json").read_bytes())

    def test_coverage_and_listing_readiness_are_independent(self):
        report = readiness(self.state, self.end)
        self.assertEqual(report["rows"][0]["feature_status"], "Elevated attention")
        self.assertEqual(report["rows"][0]["listing_review"], "unverified")
        candidate = self.state["universe"][0]
        candidate.update(security_status="active", issuer="Fictional", venue="SIMULATED",
                         validated_at="2025-11-07T17:00:00Z", validation_source="fictional fixture")
        self.assertEqual(readiness(self.state, self.end)["rows"][0]["listing_review"], "recorded_active")
        candidate["validated_at"] = "2025-09-01T17:00:00Z"
        self.assertEqual(readiness(self.state, self.end)["rows"][0]["listing_review"], "review_due")

    def test_readiness_includes_never_collected_candidates(self):
        self.state["posts"] = []
        self.state["coverage"] = []
        report = readiness(self.state, self.end)
        self.assertEqual(report["research_candidates"], 1)
        self.assertIsNone(report["rows"][0]["source"])
        self.assertEqual(report["rows"][0]["coverage_status"], "not_collected")

    def test_newer_non_alert_supersedes_old_concern(self):
        newest = copy.deepcopy(self.state["evaluations"][0])
        newest.update(id="newer", end="2025-11-08T18:00:00Z", label="Insufficient coverage", social_attention_score=None)
        self.state["evaluations"].append(newest)
        self.assertEqual(attention_queue(self.state), [])

    def test_older_window_rerun_does_not_supersede_newer_window(self):
        older = copy.deepcopy(self.state["evaluations"][0])
        older.update(id="older-rerun", end="2025-11-06T18:00:00Z", label="Normal", social_attention_score=0)
        self.state["evaluations"].append(older)
        queue = attention_queue(self.state)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["end"], self.end)
        self.assertEqual(queue[0]["age_status"], "historical_window")

    def test_queue_does_not_backdate_imported_evaluations(self):
        self.assertEqual(attention_queue(self.state, as_of=self.end), [])

    def test_reviews_preserve_evaluation_and_do_not_reveal_older_alert(self):
        original = copy.deepcopy(self.state["evaluations"])
        row = original[0]
        review_evaluation(self.workspace, row["id"], "Fictional test reviewed")
        state = read_state(self.workspace)
        self.assertEqual(state["evaluations"], original)
        self.assertEqual(attention_queue(state), [])
        self.assertEqual(attention_queue(state, include_reviewed=True)[0]["review_status"], "reviewed")
        with self.assertRaisesRegex(ValueError, "Unknown evaluation"):
            review_evaluation(self.workspace, "missing", "review")

    def test_archived_candidates_leave_queue(self):
        self.state["universe"][0]["membership"] = "archived"
        self.assertEqual(attention_queue(self.state), [])
        self.assertEqual(readiness(self.state)["research_candidates"], 0)

    def test_combined_labels_require_independent_complete_coverage(self):
        social = {"coverage_status": "complete", "label": "Elevated attention"}
        self.assertEqual(combined_classification("alert", social), "Combined concern")
        self.assertEqual(combined_classification("no_signal", social), "Elevated social attention")
        self.assertEqual(combined_classification("alert", {"coverage_status": "failed"}), "Insufficient coverage")
        self.assertEqual(combined_classification("alert", {"coverage_status": "complete", "label": "Normal"}), "Market anomaly")

    def test_dashboard_import_and_review(self):
        from streamlit.testing.v1 import AppTest
        from pennystock import storage
        from pennystock import social_ui
        payload = copy.deepcopy(self.payload)
        payload["observations"] = [copy.deepcopy(payload["observations"][-1])]
        payload["observations"][0]["source_post_id"] = "ui-import-new"
        content = json.dumps(payload).encode()
        upload = io.BytesIO(content)
        upload.size = len(content)
        dashboard = Path(__file__).resolve().parents[1] / "dashboard/dashboard.py"
        with patch.object(storage, "ROOT", Path(self.temp.name)), patch.object(storage, "DEFAULT_WORKSPACE", self.workspace), patch.object(social_ui.st, "file_uploader", return_value=upload):
            app = AppTest.from_file(str(dashboard)).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(read_state(self.workspace)["posts"]), 47)
            next(b for b in app.button if b.label == "Save validated import").click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(read_state(self.workspace)["posts"]), 48)
            next(t for t in app.text_input if t.label == "What did you find in the evidence?").set_value("Checked the fictional source links")
            next(b for b in app.button if b.label == "Mark evaluation reviewed").click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(read_state(self.workspace)["social_reviews"]), 1)

    def test_dashboard_record_handles_busy_writer_and_then_succeeds(self):
        from streamlit.testing.v1 import AppTest
        from pennystock import storage
        dashboard = Path(__file__).resolve().parents[1] / "dashboard/dashboard.py"
        with patch.object(storage, "ROOT", Path(self.temp.name)), patch.object(storage, "DEFAULT_WORKSPACE", self.workspace):
            app = AppTest.from_file(str(dashboard)).run(timeout=20)
            with storage.writer_lock(self.workspace):
                next(b for b in app.button if b.label == "Record this evaluation").click().run(timeout=20)
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(any("Another writer" in e.value for e in app.error))
                self.assertEqual(len(read_state(self.workspace)["evaluations"]), 1)
            next(b for b in app.button if b.label == "Record this evaluation").click().run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(read_state(self.workspace)["evaluations"]), 2)


if __name__ == "__main__":
    unittest.main()
