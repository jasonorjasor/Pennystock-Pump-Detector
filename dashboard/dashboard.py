"""Microcap Observatory: daily briefing, explanations, outcomes, and research notes."""
from pathlib import Path
import json
import sys
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
from pennystock.core import metrics, score_bins
from pennystock.pipeline import alerts_with_outcomes, utcnow
from pennystock.storage import ROOT, DEFAULT_WORKSPACE, read_csv, save_json, writer_lock

st.set_page_config(page_title="Microcap Observatory", page_icon="🔎", layout="wide")
st.title("Microcap Observatory")
st.caption("Unusual activity · Dated observations · Measured outcomes")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def show_metrics(frame, legacy=False):
    m = metrics(frame, legacy)
    cols = st.columns(4)
    cols[0].metric("Alerts", m["total"])
    cols[1].metric("Classified" if legacy else "Final outcomes", m["final"])
    cols[2].metric("Pending", m["pending"])
    cols[3].metric("Legacy positive-label share" if legacy else "Sharp reversal share",
                   "N/A" if m["rate"] is None else f'{m["rate"]:.1f}%')
    st.caption(f'Outcome completion: {m["completion"]:.1f}%. '
               "Reversal share uses final outcomes only; ambiguous outcomes remain in the denominator.")
    if m["ci_low"] is not None:
        st.caption(f'Wilson interval: {m["ci_low"]:.1f}–{m["ci_high"]:.1f}%. '
                   "This descriptive interval does not account for dependence between repeated ticker events.")
    return m


def main():
    workspaces = sorted([p.parent for p in (ROOT / "runs").glob("*/workspace.json")], reverse=True)
    if DEFAULT_WORKSPACE not in workspaces:
        workspaces.insert(0, DEFAULT_WORKSPACE)
    else:
        workspaces.remove(DEFAULT_WORKSPACE)
        workspaces.insert(0, DEFAULT_WORKSPACE)
    legacy_paths = sorted((ROOT / "runs").glob("*/data/alerts/alerts_history.csv"), reverse=True)
    choices = {f"Observatory / {p.name}": (p, False) for p in workspaces}
    choices.update({f"Legacy / {p.parents[2].name}": (p.parents[2], True) for p in legacy_paths})
    selected = st.sidebar.selectbox("Dataset", list(choices))
    workspace, legacy = choices[selected]
    if st.sidebar.button("Refresh"):
        st.rerun()
    if legacy:
        st.warning("Legacy research: unbounded outcome windows and unversioned rules. "
                   "These labels are preserved for reference and do not establish manipulation.")
        alerts = read_csv(workspace / "data/alerts/alerts_history.csv")
        alerts["session"] = pd.to_datetime(alerts.alert_date).dt.strftime("%Y-%m-%d")
        obs, manifest = pd.DataFrame(), {}
    else:
        alerts = alerts_with_outcomes(workspace)
        obs = read_csv(workspace / "observations.csv")
        manifest = read_json(workspace / "latest_scan.json")
        meta = read_json(workspace / "workspace.json")
        if meta.get("kind") == "legacy-reconstruction":
            st.warning("Reconstructed legacy cohort. Scores were not recreated as known at the time. "
                       "Outcome prices may differ from the original source observations.")
        if meta.get("kind") == "offline-demo":
            st.info(f"Offline demonstration using {meta.get('demo_source', 'local archived bars')}. This is not a current scan.")
    if manifest:
        st.subheader(f'Session briefing · {manifest["session"]}')
        expected = len(manifest["universe"])
        counts = manifest.get("counts", {})
        healthy = counts.get("alert", 0) + counts.get("no_signal", 0)
        st.write(f'{healthy}/{expected} tickers successfully checked · {manifest["state"]}')
        st.caption(f'Finished: {manifest.get("finished_at", "running")} · Source: {manifest["provider"]}')
        age = (pd.Timestamp.today().normalize() - pd.Timestamp(manifest["session"])).days
        if age > 4:
            st.warning(f"The latest recorded scan is {age} calendar days old.")
        if manifest["state"] != "complete":
            st.warning("Coverage is incomplete. Missing/failed tickers must not be treated as no-signal results.")
        with st.expander("Scan health and coverage"):
            st.json(counts)
            attempts = read_csv(workspace / "attempts" / manifest["attempt_id"] / "observations.csv")
            if not attempts.empty:
                st.dataframe(attempts[[c for c in ["ticker", "tier", "watchlist", "scan_status", "error"] if c in attempts]], hide_index=True)
    elif not legacy:
        st.info("No daily scan recorded in this workspace. Run: python observatory.py scan")
    if not alerts.empty:
        st.caption(f'Recorded alert sessions: {alerts.session.min()} to {alerts.session.max()}')
    if not legacy:
        tracking = read_json(workspace / "latest_tracking.json")
        if tracking:
            st.caption(f'Outcome update through {tracking["as_of"]}: {tracking["state"]}')
            if tracking["state"] == "partial":
                st.warning("Some outcomes could not be refreshed; prior valid values were retained.")

    briefing, performance, detail, candidates, study_tab, social = st.tabs(["Research queue", "Evaluation", "Ticker notebook", "New candidates", "Study progress", "Social evidence"])
    with briefing:
        if alerts.empty:
            st.info("No alerts recorded. A healthy scan can finish with zero alerts.")
        else:
            sessions = sorted(alerts.session.unique(), reverse=True)
            selected_session = st.selectbox("Alert session", ["All sessions"] + sessions)
            queue = alerts if selected_session == "All sessions" else alerts[alerts.session.eq(selected_session)]
            outcomes = sorted(queue.outcome.dropna().unique())
            selected_outcomes = st.multiselect("Queue outcomes", outcomes, default=outcomes)
            queue = queue[queue.outcome.isin(selected_outcomes)]
            queue = queue.sort_values(["session", "pump_score"], ascending=[False, False])
            st.dataframe(queue[[c for c in ["session", "ticker", "tier", "pump_score", "alert_price", "outcome", "state", "daily_return"] if c in queue]], hide_index=True)
            st.download_button("Download entire filtered queue", queue.to_csv(index=False).encode("utf-8"),
                               "research_queue.csv", "text/csv")
            st.caption("Scores are activity points, not probabilities. Price outcomes do not establish manipulation.")

    with performance:
        st.write("Performance uses the full selected dataset and is independent of queue outcome filters.")
        show_metrics(alerts, legacy)
        if not alerts.empty:
            mature = alerts[alerts.outcome.isin(["confirmed_pump", "likely_pump", "false_positive", "uncertain"])] if legacy else alerts[alerts.state.eq("final")]
            if not mature.empty:
                st.subheader("Final outcomes by score")
                bins = mature.assign(score_bin=score_bins(pd.to_numeric(mature.pump_score)))
                rows = []
                for label, group in bins.groupby("score_bin", observed=True):
                    m = metrics(group, legacy)
                    rows.append({"Score range": str(label), "Final outcomes": m["final"], "Positive share (%)": m["rate"]})
                st.dataframe(pd.DataFrame(rows), hide_index=True)
            st.subheader("By ticker")
            groups = []
            for ticker, group in alerts.groupby("ticker"):
                m = metrics(group, legacy)
                groups.append({"Ticker": ticker, "Alerts": m["total"], "Final": m["final"], "Pending": m["pending"], "Positive share (%)": m["rate"]})
            st.dataframe(pd.DataFrame(groups), hide_index=True)
            st.bar_chart(alerts.outcome.value_counts())
        st.info("No claim of predictive advantage: matched baselines, event labels, and chronological evaluation are still needed.")

    with detail:
        if alerts.empty:
            st.info("Ticker explanations and research notes appear after the first alert.")
        else:
            ticker = st.selectbox("Ticker", sorted(alerts.ticker.unique()))
            history = alerts[alerts.ticker.eq(ticker)].sort_values("session")
            # Episode start date is stable when future observations are appended.
            dates = pd.to_datetime(history.session)
            starts = dates.where(dates.diff().dt.days.gt(7) | dates.diff().isna()).ffill()
            history = history.assign(event_start=starts.dt.strftime("%Y-%m-%d").values)
            st.dataframe(history[[c for c in ["session", "event_start", "pump_score", "outcome", "return_1d", "return_5d", "return_10d", "worst_return_10d"] if c in history]], hide_index=True)
            st.caption("Events group signals separated by at most seven calendar days. They are activity clusters, not evidence of coordination.")
            session = st.selectbox("Observation to inspect", list(reversed(history.session.unique())))
            row = history[history.session.eq(session)].iloc[0]
            explanation = row.get("explanation")
            if isinstance(explanation, str):
                st.subheader("Why this triggered")
                reasons = pd.DataFrame(json.loads(explanation))
                st.dataframe(reasons, hide_index=True)
                st.caption(f'Rule contributions total: {int(reasons.points.sum())} points. '
                           "Baseline: previous 20 sessions; current session excluded.")
            else:
                st.caption("Full rule contributions were not archived for this legacy observation.")
            attempt_id = row.get("attempt_id")
            if isinstance(attempt_id, str):
                path = workspace / "attempts" / attempt_id / "bars" / f"{ticker}.csv"
                if path.exists():
                    bars = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
                    st.line_chart(bars[["Close"]])
                    st.bar_chart(bars[["Volume"]])
                    st.caption("Archived bars from this observation. Provider adjustment basis is recorded in the scan manifest.")
            if not legacy:
                key = f'{ticker}:{row["session"]}'
                notes_path = workspace / "notes.json"
                notes = read_json(notes_path)
                note = notes.get(key, {})
                with st.form("research_note"):
                    text = st.text_area("Research note", value=note.get("text", ""))
                    url = st.text_input("Evidence URL", value=note.get("url", ""))
                    source_time = st.text_input("Source publication time (if known)", value=note.get("source_time", ""))
                    reviewed = st.checkbox("Reviewed", value=note.get("reviewed", False))
                    submitted = st.form_submit_button("Save note")
                if submitted:
                    if url and not url.startswith(("https://", "http://")):
                        st.error("Use an http or https evidence URL.")
                    else:
                        with writer_lock(workspace):
                            notes = read_json(notes_path)
                            notes[key] = {"text": text, "url": url, "source_time": source_time,
                                          "reviewed": reviewed, "updated_at": utcnow()}
                            save_json(notes_path, notes)
                        st.success("Note saved.")
                st.caption("Notes attach to this observation's date. Separate observed facts from interpretations.")


    with candidates:
        if legacy:
            st.info("Select an Observatory workspace to review candidates.")
        else:
            from pennystock.discovery import change_candidate, list_candidates, read_registry
            rows = list_candidates(workspace)
            pending = [r for r in rows if r["state"] == "needs_review"]
            legacy_reviews = [r for r in rows if r["state"] == "approved" and not r.get("latest_review")]
            if legacy_reviews:
                st.warning(f"{len(legacy_reviews)} approved candidates still need the new structured review. They remain approved, but should be documented during this study.")
            if not pending:
                st.info("No candidates need review. Run: python observatory.py discover")
            else:
                ticker = st.selectbox("Candidate", [r["ticker"] for r in pending])
                candidate = next(r for r in pending if r["ticker"] == ticker)
                observation = candidate.get("latest_observation") or {}
                registry = read_registry(workspace)
                identity = max((r for r in registry["identities"] if r["symbol"] == ticker),
                               key=lambda r: r["retrieved_at"], default={})
                st.write({"state": candidate["state"], "quiet_comparison": candidate["quiet_comparison"],
                          "issuer": identity.get("issuer"), "venue": identity.get("venue"),
                          "score_version": observation.get("score_version"), "discovery_score": observation.get("discovery_score"),
                          "coverage_status": observation.get("coverage_status"), "latest_price": observation.get("latest_price"),
                          "volume_ratio": observation.get("volume_ratio"), "volume_z": observation.get("volume_z"),
                          "return_1d": observation.get("return_1d"), "listing_deficiency": observation.get("listing_deficiency")})
                st.caption("Discovery ranks research candidates. It is separate from market alerts and social evidence.")
                st.link_button("Search SEC EDGAR", f"https://www.sec.gov/edgar/search/#/q={ticker}")
                reason = st.text_input("Candidate review reason", key="candidate_reason")
                identity_checked = st.checkbox("Identity and listing checked")
                liquidity_checked = st.checkbox("Liquidity and chart checked")
                catalyst = st.selectbox("Recent catalyst", ["unknown", "none_found", "company_news", "sec_filing", "analyst_or_media"])
                corporate_action = st.selectbox("Corporate action", ["unknown", "none_found", "split", "offering", "symbol_change", "other"])
                data_quality = st.selectbox("Data quality", ["unknown", "complete", "partial", "failed"])
                evidence_url = st.text_input("Review evidence URL")
                review = {"identity_checked": identity_checked, "liquidity_checked": liquidity_checked,
                          "catalyst_category": catalyst, "corporate_action": corporate_action,
                          "data_quality": data_quality, "evidence_url": evidence_url}
                left, right = st.columns(2)
                if left.button("Approve candidate"):
                    try:
                        change_candidate(workspace, ticker, "approved", reason, review=review)
                        st.success(f"{ticker} approved for the next uncaptured session.")
                        st.rerun()
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
                if right.button("Reject candidate"):
                    try:
                        change_candidate(workspace, ticker, "rejected", reason, review=review)
                        st.success(f"{ticker} rejected; its history was retained.")
                        st.rerun()
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
            if legacy_reviews:
                with st.expander("Document an existing approved candidate"):
                    old_ticker = st.selectbox("Approved candidate", [r["ticker"] for r in legacy_reviews])
                    old_reason = st.text_input("Existing-candidate review reason")
                    old_identity = st.checkbox("Existing identity and listing checked")
                    old_liquidity = st.checkbox("Existing liquidity and chart checked")
                    old_catalyst = st.selectbox("Existing recent catalyst", ["unknown", "none_found", "company_news", "sec_filing", "analyst_or_media"])
                    old_action = st.selectbox("Existing corporate action", ["unknown", "none_found", "split", "offering", "symbol_change", "other"])
                    old_quality = st.selectbox("Existing data quality", ["unknown", "complete", "partial", "failed"])
                    old_url = st.text_input("Existing review evidence URL")
                    if st.button("Save existing structured review"):
                        try:
                            change_candidate(workspace, old_ticker, "approved", old_reason, review={
                                "identity_checked": old_identity, "liquidity_checked": old_liquidity,
                                "catalyst_category": old_catalyst, "corporate_action": old_action,
                                "data_quality": old_quality, "evidence_url": old_url})
                            st.success(f"Structured review saved for {old_ticker}.")
                            st.rerun()
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
    with study_tab:
        if legacy:
            st.info("Select an Observatory workspace to inspect the prospective study.")
        else:
            from pennystock.study import study_report
            study = study_report(workspace)
            if not study["registered"]:
                st.info("The prospective study begins with the next daily run.")
            else:
                st.metric("Completed sessions", f'{study["completed_sessions"]}/{study["target_sessions"]}')
                st.progress(min(study["completed_sessions"] / study["target_sessions"], 1.0))
                st.write({"study_version": study["study_version"], "started_session": study["started_session"],
                          "coverage": study["coverage"], "next_gate": study["next_gate"]})
                st.dataframe(pd.DataFrame(study["cohorts"]), hide_index=True)
                if not study["machine_learning_eligible"]:
                    st.info("Machine learning remains gated until at least 100 reviewed, finalized observations exist.")
                st.caption("Score rules remain frozen for this workspace. Baselines are selected prospectively from the same scanned universe.")

    with social:
        if legacy:
            st.info("Select an Observatory workspace to inspect social evidence.")
        else:
            from pennystock.social_ui import render
            render(workspace)


try:
    main()
except (ValueError, OSError, KeyError) as exc:
    st.error(f"Could not load this research workspace: {exc}")
