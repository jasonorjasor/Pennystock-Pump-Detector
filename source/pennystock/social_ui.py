"""Optional Streamlit view of the shared local social evidence service."""
import pandas as pd
import streamlit as st

from .social import (WINDOWS, features, import_payload, parse_import, preview_import,
                     read_state, social_features, timeline)
from .research import attention_queue, readiness, review_evaluation


def render_import(workspace):
    with st.expander("Import social evidence"):
        st.caption("Upload a permitted JSON export, inspect the validation summary, then save. The original upload is not written to disk. Maximum 10 MB.")
        upload = st.file_uploader("Social evidence JSON", type=["json"], max_upload_size=10,
                                  key=f"social_upload:{workspace}")
        if upload is None:
            return
        try:
            if upload.size > 10_000_000:
                raise ValueError("Import exceeds 10 MB; split it into smaller batches")
            payload = parse_import(upload.getvalue())
            preview = preview_import(workspace, payload)
            st.write(f'Validated {preview["data_kind"]} import: {preview["added"]["posts"]} new posts, {preview["added"]["coverage"]} new coverage records.')
            st.json(preview)
            if st.button("Save validated import", key=f"social_import_save:{workspace}",
                         disabled=not any(preview["added"].values())):
                result = import_payload(workspace, payload)
                st.session_state[f"social_notice:{workspace}"] = f'Saved {result["added"]["posts"]} new posts and {result["added"]["coverage"]} coverage records.'
                st.rerun()
        except (ValueError, OSError, RuntimeError) as exc:
            st.error(f"Import rejected: {exc}")


def render_workbench(workspace, state):
    with st.expander("Research readiness", expanded=True):
        report = readiness(state)
        st.write(f'{report["research_candidates"]} research candidates; {report["candidates_needing_listing_review"]} need listing review.')
        st.caption(f'Coverage checked through {report["as_of"]}. Listing assertions are user-recorded; the 30-day reminder is a project review policy. This report does not verify listings or establish predictive readiness.')
        if report["rows"]:
            frame = pd.DataFrame(report["rows"])
            frame["next_actions"] = frame.next_actions.map("; ".join)
            st.dataframe(frame, hide_index=True)
    with st.expander("Attention review queue", expanded=True):
        st.caption("Latest recorded evaluation per ticker/source/query/window/score version. A newer normal or insufficient-data evaluation replaces an older concern. Historical imports are never live warnings.")
        include = st.checkbox("Include reviewed attention evaluations", key=f"social_include_reviewed:{workspace}")
        queue = attention_queue(state, include_reviewed=include)
        if not queue:
            st.info("No recorded elevated-attention evaluations awaiting review. This does not establish quiet activity or complete coverage.")
        else:
            st.dataframe(pd.DataFrame(queue), hide_index=True)
            if any(r["new_evidence_since_evaluation"] for r in queue):
                st.info("Some evaluations have newer relevant evidence. Inspect the ticker and record a new evaluation to include it; old scores stay preserved.")
            labels = {r["id"]: f'{r["ticker"]} / {r["source"]} / {r["window"]} / {r["end"]} / {r["score_version"]}' for r in queue}
            selected = st.selectbox("Attention evaluation to review", list(labels), format_func=labels.get,
                                    key=f"social_review_choice:{workspace}")
            with st.form(f"social_review_form:{workspace}"):
                note = st.text_input("What did you find in the evidence?", key=f"social_review_note:{workspace}")
                submit = st.form_submit_button("Mark evaluation reviewed")
            if submit:
                try:
                    review_evaluation(workspace, selected, note)
                    st.session_state[f"social_notice:{workspace}"] = "Review saved; the recorded score was preserved."
                    st.rerun()
                except (ValueError, OSError, RuntimeError) as exc:
                    st.error(str(exc))


def render(workspace):
    state = read_state(workspace)
    st.subheader("Social evidence research")
    notice = st.session_state.pop(f"social_notice:{workspace}", None)
    if notice:
        st.success(notice)
    st.caption("Imported evidence is retrospective. Attention points are experimental; they do not establish manipulation or predictive accuracy.")
    if state["data_kind"] == "synthetic":
        st.warning("SYNTHETIC DEMONSTRATION: all social posts and coverage in this workspace are fictional.")
    render_workbench(workspace, state)
    if not state["universe"]:
        st.info("Initialize your research candidates: python observatory.py universe-init")
        st.code("python observatory.py social-demo")
        return
    st.dataframe(pd.DataFrame(state["universe"]), hide_index=True)
    render_import(workspace)
    ticker = st.selectbox("Social research ticker", sorted(r["ticker"] for r in state["universe"]))
    coverage = [r for r in state["coverage"] if r["ticker"] == ticker]
    if not coverage:
        st.info("Not collected: no source coverage has been recorded for this ticker. This does not mean zero mentions.")
    else:
        source = st.selectbox("Social source", sorted({r["source"] for r in coverage}))
        scopes = sorted({r["query_scope"] for r in coverage if r["source"] == source})
        scope = st.selectbox("Collection query", scopes)
        window = st.selectbox("Social window", list(WINDOWS), index=2)
        latest = max(r["end"] for r in coverage if r["source"] == source and r["query_scope"] == scope)
        end = st.text_input("Social window end (ISO timestamp with timezone)", value=latest)
        try:
            result = features(state, ticker, source, end, window, scope)
            st.write(f'{result["label"]} · Score: {result["social_attention_score"] if result["social_attention_score"] is not None else "unavailable"}')
            st.write(f'Observed mentions: {result["mention_count_observed"]} · Known unique authors: {result["unique_authors_observed"]}')
            st.caption(f'Coverage: {result["coverage_status"]} · Baseline: {result["baseline_status"]}. Window: {result["start"]} to {result["end"]} (end exclusive).')
            with st.expander("Attention score explanation"):
                st.json(result)
            if st.button("Record this evaluation", key=f"social_record:{workspace}"):
                social_features(ticker, source, end, workspace, window, scope)
                st.session_state[f"social_notice:{workspace}"] = "Retrospective evaluation recorded at the actual generation time."
                st.rerun()
        except (ValueError, OSError, RuntimeError) as exc:
            st.error(str(exc))
        st.caption("A complete record means the declared source query completed, not that every social platform was observed.")
        st.dataframe(pd.DataFrame(coverage), hide_index=True)
    joined = timeline(workspace, ticker)
    if joined["events"]:
        st.subheader("Evidence chronology")
        st.caption("Post rows use publication time and retain collection/import times. Market rows use scan capture time. Evaluation rows use actual generation time, with the historical window end separate.")
        st.dataframe(pd.DataFrame(joined["events"]), hide_index=True,
                     column_config={"url": st.column_config.LinkColumn("Evidence source")})
    unresolved = sum(p["resolved_ticker"] is None for p in state["posts"])
    st.caption(f"Unresolved posts across this workspace: {unresolved}; excluded from ticker scores.")
