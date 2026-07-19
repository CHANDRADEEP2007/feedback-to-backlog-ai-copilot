from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_sortables import sort_items

from src.architecture import ARCHITECTURE_VIEWS, render_architecture
from src.config import Settings
from src.database import BacklogDatabase
from src.evaluation import load_results, run_evaluation, save_results
from src.jira_client import JiraClient, sync_reviewed_items
from src.pipeline import process_batch
from src.priority_delta import build_priority_delta_frame
from src.scoring import RiceScore, confidence_after_move


st.set_page_config(page_title="SignalStack · Feedback Copilot", page_icon="◈", layout="wide")

st.markdown(
    """
    <style>
    .stApp {background: #f6f7fb; color: #182230;}
    [data-testid="stSidebar"] {background: #111827;}
    [data-testid="stSidebar"] * {color: #f9fafb;}
    [data-testid="stSidebar"] [data-testid="stPopoverButton"] p {color: #111827 !important;}
    [data-testid="stMetric"] {background: white; border: 1px solid #e5e7eb; border-radius: 14px; padding: 18px;}
    [data-testid="stSidebar"] [data-testid="stMetric"] {background:#1f2937;border-color:#374151;}
    [data-testid="stSidebar"] [data-testid="stMetric"] * {color:#f9fafb !important;}
    .hero {background: linear-gradient(120deg,#172554,#312e81); color:white; padding:28px 32px; border-radius:18px; margin-bottom:20px;}
    .hero h1 {font-size:2.2rem; margin:0 0 6px 0;}
    .hero p {margin:0; color:#c7d2fe;}
    .badge {display:inline-block;padding:4px 10px;border-radius:99px;background:#dcfce7;color:#166534;font-size:12px;font-weight:700;}
    div[data-testid="stExpander"] {background:white;border-radius:12px;}
    .architecture-visual {background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:18px;margin:8px 0 24px;}
    .arch-summary {display:flex;align-items:center;gap:10px;color:#475569;font-size:14px;margin-bottom:16px;}
    .arch-view-label {background:#e0e7ff;color:#3730a3;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700;white-space:nowrap;}
    .arch-flow {display:grid;grid-template-columns:minmax(0,1fr) 30px minmax(0,1.25fr) 30px minmax(0,1fr) 30px minmax(0,1fr);align-items:stretch;gap:6px;}
    .arch-stage {background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:14px;min-width:0;}
    .arch-stage-number {color:#6366f1;font-size:11px;font-weight:800;letter-spacing:.12em;}
    .arch-stage-title {color:#0f172a;font-size:14px;font-weight:800;margin:3px 0 10px;}
    .arch-node-list {display:flex;flex-direction:column;gap:8px;}
    .arch-node {border-radius:10px;padding:10px;background:#fff;}
    .arch-built {border:1px solid #86efac;box-shadow:inset 3px 0 0 #22c55e;}
    .arch-planned {border:1px dashed #a5b4fc;background:#f5f3ff;}
    .arch-node-heading {display:flex;align-items:flex-start;justify-content:space-between;gap:8px;}
    .arch-node-name {color:#172033;font-size:12px;font-weight:700;line-height:1.3;}
    .arch-node-detail {color:#64748b;font-size:11px;line-height:1.35;margin-top:4px;}
    .arch-status {border-radius:999px;padding:2px 6px;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;}
    .arch-built .arch-status {background:#dcfce7;color:#166534;}
    .arch-planned .arch-status {background:#ede9fe;color:#5b21b6;}
    .arch-arrow {display:flex;align-items:center;justify-content:center;color:#6366f1;font-size:24px;font-weight:800;}
    .arch-legend {display:flex;gap:18px;flex-wrap:wrap;color:#64748b;font-size:11px;margin-top:14px;}
    .arch-legend span {display:flex;align-items:center;gap:6px;}
    .arch-dot {display:inline-block;width:9px;height:9px;border-radius:50%;}
    .arch-dot-built {background:#22c55e;}
    .arch-dot-planned {background:#8b5cf6;}
    @media (max-width: 1000px) {
      .arch-flow {grid-template-columns:1fr;}
      .arch-arrow {height:20px;}
      .arch-arrow span {transform:rotate(90deg);}
      .arch-summary {align-items:flex-start;flex-direction:column;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_csv(path_or_file) -> pd.DataFrame:
    return pd.read_csv(path_or_file, encoding="utf-8", on_bad_lines="skip")


def frame(rows) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows])


settings = Settings()
db = BacklogDatabase(settings.database_path)

st.sidebar.markdown("## ◈ SignalStack")
st.sidebar.caption("Feedback-to-Backlog AI Copilot")
st.sidebar.markdown("---")
st.sidebar.markdown("**Integration status**")
st.sidebar.markdown(f"{'🟢' if settings.gemini_enabled else '⚪'} Gemini extraction")
st.sidebar.markdown(f"{'🟢' if settings.jira_enabled else '⚪'} Jira sync")
st.sidebar.markdown(f"{'🟢' if settings.semantic_dedup_active else '⚪'} Semantic dedup")
st.sidebar.caption("Missing credentials activate safe demo mode.")
with st.sidebar.popover("Connections · Coming soon", width="stretch"):
    st.caption("Roadmap previews only. No source is enabled without a real integration.")
    for connector in ("Outlook", "Teams", "Zoom", "Slack", "Intercom", "Zendesk"):
        st.button(
            connector,
            key=f"connection_{connector.lower()}",
            disabled=True,
            help="Coming soon",
            width="stretch",
        )
st.sidebar.markdown("---")
st.sidebar.metric("Dedup threshold", f"{settings.dedup_threshold:.0f}%")

st.markdown(
    """
    <div class="hero">
      <span class="badge">MVP · PHASE 2</span>
      <h1>Turn customer noise into a ranked backlog.</h1>
      <p>Extract signals, merge repeats, explain priority, and sync reviewed work to Jira.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

overview_tab, ingest_tab, backlog_tab, quality_tab, architecture_tab = st.tabs(
    [
        "Overview",
        "Process feedback",
        "Backlog review",
        "Quality & guardrails",
        "System architecture",
    ]
)

with overview_tab:
    backlog = frame(db.backlog_rows())
    sources = frame(db.source_rows())
    errors = frame(db.error_rows())
    total_sources = len(sources)
    duplicate_signals = max(total_sources - len(backlog), 0)
    duplicate_rate = duplicate_signals / total_sources if total_sources else 0

    columns = st.columns(5)
    columns[0].metric("Backlog items", f"{len(backlog):,}")
    columns[1].metric("Feedback signals", f"{total_sources:,}")
    columns[2].metric("Signals merged", f"{duplicate_signals:,}")
    columns[3].metric("Merge rate", f"{duplicate_rate:.1%}")
    columns[4].metric("Guardrail errors", f"{len(errors):,}")

    st.caption(
        "**System architecture** · See the dedicated tab for current-state and "
        "target-state architecture."
    )

    if backlog.empty:
        st.info("No backlog yet. Open **Process feedback** and run a batch to create the first prioritized items.")
    else:
        left, right = st.columns((1.6, 1))
        with left:
            top = backlog.nlargest(12, "rice_score").sort_values("rice_score")
            chart = px.bar(
                top,
                x="rice_score",
                y="issue",
                orientation="h",
                color="rice_score",
                color_continuous_scale=["#c7d2fe", "#4f46e5"],
                labels={"rice_score": "RICE score", "issue": ""},
                title="Highest-priority customer issues",
            )
            chart.update_layout(height=440, coloraxis_showscale=False, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(chart, width="stretch")
        with right:
            category = backlog.groupby("category", as_index=False).agg(items=("id", "count"), signals=("occurrence_count", "sum"))
            category = category.nlargest(8, "signals")
            chart = px.bar(
                category,
                x="category",
                y="signals",
                color="items",
                color_continuous_scale=["#99f6e4", "#0f766e"],
                title="Signal volume by category",
                labels={"category": "", "signals": "Feedback signals", "items": "Backlog items"},
            )
            chart.update_layout(height=440, coloraxis_showscale=False, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(chart, width="stretch")

        st.subheader("Priority queue")
        display = backlog[["issue", "category", "rice_score", "occurrence_count", "manually_adjusted", "status", "jira_url"]].copy()
        display["manually_adjusted"] = display["manually_adjusted"].map(
            {1: "🟠 Manually adjusted", 0: "AI baseline"}
        )
        display.columns = ["Issue", "Category", "RICE", "Signals", "Priority source", "Status", "Jira"]
        st.dataframe(display.head(20), width="stretch", hide_index=True)

        st.subheader("What changed in prioritization")
        st.caption(
            "Compares each reviewed item's latest RICE score against its previous score snapshot."
        )
        history = frame(db.score_history_rows())
        priority_delta = build_priority_delta_frame(backlog, history)
        if priority_delta.empty:
            st.info(
                "No score changes yet. This chart appears after duplicate merges or manual "
                "review create a second score snapshot."
            )
        else:
            delta_chart_data = priority_delta.copy()
            delta_chart_data["axis_issue"] = delta_chart_data["issue"].map(
                lambda issue: issue if len(issue) <= 58 else f"{issue[:57]}…"
            )
            duplicate_labels = delta_chart_data["axis_issue"].duplicated(keep=False)
            delta_chart_data.loc[duplicate_labels, "axis_issue"] += (
                " · #" + delta_chart_data.loc[duplicate_labels, "backlog_id"].astype(str)
            )
            delta_chart_data["delta_label"] = delta_chart_data["delta"].map(
                lambda value: f"{value:+.2f}"
            )
            delta_chart = px.bar(
                delta_chart_data,
                x="delta",
                y="axis_issue",
                orientation="h",
                color="direction",
                color_discrete_map={"up": "#16a34a", "flat": "#9ca3af", "down": "#dc2626"},
                text="delta_label",
                custom_data=[
                    "issue",
                    "previous_score",
                    "current_score",
                    "delta_label",
                    "reason",
                ],
                labels={"delta": "RICE score change", "axis_issue": ""},
            )
            delta_chart.update_traces(
                textposition="outside",
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Previous score: %{customdata[1]:.2f}<br>"
                    "Current score: %{customdata[2]:.2f}<br>"
                    "Change: %{customdata[3]}<br>"
                    "Reason: %{customdata[4]}<extra></extra>"
                ),
            )
            flat_changes = delta_chart_data[delta_chart_data["direction"] == "flat"]
            if not flat_changes.empty:
                delta_chart.add_scatter(
                    x=[0.0] * len(flat_changes),
                    y=flat_changes["axis_issue"],
                    mode="markers",
                    marker={"color": "#9ca3af", "size": 10, "symbol": "diamond"},
                    customdata=flat_changes[
                        ["issue", "previous_score", "current_score", "delta_label", "reason"]
                    ],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Previous score: %{customdata[1]:.2f}<br>"
                        "Current score: %{customdata[2]:.2f}<br>"
                        "Change: %{customdata[3]}<br>"
                        "Reason: %{customdata[4]}<extra></extra>"
                    ),
                    showlegend=False,
                )
            delta_chart.update_layout(
                height=max(260, 70 * len(delta_chart_data) + 90),
                showlegend=False,
                margin=dict(l=10, r=45, t=20, b=10),
                bargap=0.35,
            )
            delta_span = max(float(delta_chart_data["delta"].abs().max()), 0.5)
            delta_chart.update_xaxes(
                range=[-delta_span * 1.25, delta_span * 1.25],
                zeroline=True,
                zerolinecolor="#64748b",
                gridcolor="#e5e7eb",
            )
            delta_chart.update_yaxes(
                categoryorder="array",
                categoryarray=delta_chart_data["axis_issue"].tolist()[::-1],
                automargin=True,
            )
            st.plotly_chart(delta_chart, width="stretch")
            st.caption("Green increases · gray unchanged · red decreases")

            delta_table = priority_delta[
                ["issue", "previous_score", "current_score", "delta", "reason"]
            ].copy()
            delta_table["previous_score"] = delta_table["previous_score"].map(lambda value: f"{value:.2f}")
            delta_table["current_score"] = delta_table["current_score"].map(lambda value: f"{value:.2f}")
            delta_table["delta"] = delta_table["delta"].map(lambda value: f"{value:+.2f}")
            delta_table.columns = ["Issue", "Previous score", "Current score", "Delta", "Reason"]
            st.dataframe(delta_table, width="stretch", hide_index=True)
            st.caption(
                "Latest score changes are shown only for items with at least one earlier score snapshot."
            )

with ingest_tab:
    st.subheader("Process a feedback batch")
    st.caption("The source file is read only when you run a batch. Broken AI output is logged and never sent to Jira.")
    if st.session_state.get("batch_message"):
        st.success(st.session_state["batch_message"])
    upload = st.file_uploader("Upload a compatible CSV", type=["csv"])
    source_path = settings.dataset_path
    source_label = str(source_path)
    try:
        data = load_csv(upload if upload is not None else source_path)
        if upload is not None:
            source_label = upload.name
        required = {"subject", "body", "type", "queue", "priority", "language"}
        missing = required - set(data.columns)
        if missing:
            st.error(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        else:
            st.success(f"Ready: {len(data):,} rows from {source_label}")
            preview_columns = [column for column in ["subject", "type", "queue", "priority", "language"] if column in data]
            st.dataframe(data[preview_columns].head(8), width="stretch", hide_index=True)
            batch_size = st.slider("Batch size", min_value=1, max_value=50, value=20)
            start_row = st.number_input("Start row", min_value=0, max_value=max(len(data) - 1, 0), value=0, step=1)
            if st.button("Run extraction pipeline", type="primary", width="stretch"):
                batch = data.iloc[int(start_row) : int(start_row) + batch_size].fillna("").to_dict("records")
                progress_bar = st.progress(0, text="Starting…")
                result = process_batch(batch, db, settings, progress_bar.progress)
                progress_bar.empty()
                st.session_state["batch_message"] = (
                    f"Processed {result.processed}: {result.created} created, "
                    f"{result.duplicates} merged, {result.skipped} already seen, {result.errors} guarded errors."
                )
                st.rerun()
    except FileNotFoundError:
        st.warning(f"Dataset not found at {source_path}. Upload the Kaggle CSV or set DATASET_PATH.")
    except Exception as error:
        st.error(f"Could not read the dataset: {error}")

with backlog_tab:
    backlog = frame(db.backlog_rows())
    if backlog.empty:
        st.info("Process a batch first; backlog review will appear here.")
    else:
        filter_a, filter_b, filter_c = st.columns((1.3, 1, 1))
        query = filter_a.text_input("Search issues", placeholder="account outage, billing, security…")
        categories = sorted(backlog["category"].dropna().unique().tolist())
        selected_categories = filter_b.multiselect("Category", categories)
        statuses = sorted(backlog["status"].dropna().unique().tolist())
        selected_statuses = filter_c.multiselect("Status", statuses)
        filtered = backlog.copy()
        if query:
            mask = filtered["issue"].str.contains(query, case=False, na=False) | filtered["category"].str.contains(query, case=False, na=False)
            filtered = filtered[mask]
        if selected_categories:
            filtered = filtered[filtered["category"].isin(selected_categories)]
        if selected_statuses:
            filtered = filtered[filtered["status"].isin(selected_statuses)]
        filtered = filtered.copy()
        filtered["priority_source"] = filtered["manually_adjusted"].map(
            {1: "🟠 Manually adjusted", 0: "AI baseline"}
        )
        review_display = filtered[["id", "issue", "category", "rice_score", "occurrence_count", "priority_source", "status", "jira_url"]].rename(
            columns={
                "id": "ID", "issue": "Issue", "category": "Category", "rice_score": "RICE",
                "occurrence_count": "Signals", "priority_source": "Priority source",
                "status": "Status", "jira_url": "Jira",
            }
        )
        st.dataframe(
            review_display,
            width="stretch",
            hide_index=True,
            column_config={"Jira": st.column_config.LinkColumn("Jira")},
        )

        st.markdown("#### Explainable manual re-rank")
        st.caption(
            "Drag an item, then apply the preview. Each position moved changes Confidence by "
            "5 percentage points (bounded from 0% to 100%); Reach, Impact, and Effort never move."
        )
        reviewer_name = st.text_input(
            "Reviewer name",
            value=st.session_state.get("reviewer_name", "Product manager"),
            key="reviewer_name",
            help="Stored with every manual score adjustment.",
        )
        ordered_backlog = backlog.sort_values(["rice_score", "id"], ascending=[False, True])
        rank_labels = []
        label_to_id = {}
        for row in ordered_backlog.itertuples():
            badge = " · MANUALLY ADJUSTED" if int(row.manually_adjusted) else ""
            label = f"#{int(row.id)} · {row.issue} · RICE {float(row.rice_score):.2f}{badge}"
            rank_labels.append(label)
            label_to_id[label] = int(row.id)
        reranked_labels = sort_items(
            rank_labels,
            custom_style="""
                .sortable-component {padding: 0.25rem;}
                .sortable-item {
                    background: #ffffff;
                    border: 1px solid #dbe3ef;
                    border-radius: 10px;
                    color: #182230;
                    margin: 0.35rem 0;
                    padding: 0.7rem;
                }
            """,
        )
        requested_ids = [label_to_id[label] for label in reranked_labels]
        current_ids = ordered_backlog["id"].astype(int).tolist()
        rank_changed = requested_ids != current_ids
        preview_rows = []
        rerank_message = st.session_state.pop("rerank_message", None)
        if rerank_message:
            st.success(rerank_message)
        if rank_changed:
            positions = {item_id: position for position, item_id in enumerate(current_ids)}
            backlog_by_id = {int(row.id): row for row in backlog.itertuples()}
            projected_scores = {}
            for new_position, item_id in enumerate(requested_ids):
                row = backlog_by_id[item_id]
                confidence = confidence_after_move(
                    float(row.confidence), positions[item_id], new_position
                )
                rice = RiceScore(
                    float(row.reach), float(row.impact), confidence, float(row.effort)
                )
                projected_scores[item_id] = rice.score
                preview_rows.append(
                    {
                        "Requested rank": new_position + 1,
                        "Issue": row.issue,
                        "Confidence": f"{confidence:.0%}",
                        "RICE": f"{rice.score:.2f}",
                        "Explanation": rice.explanation,
                    }
                )
            score_order = sorted(
                requested_ids,
                key=lambda item_id: (-projected_scores[item_id], item_id),
            )
            representable = score_order == requested_ids
            st.dataframe(preview_rows, width="stretch", hide_index=True)
            if not representable:
                st.warning(
                    "This drag cannot be represented by the fixed Confidence adjustment. "
                    "Nothing will be saved because the displayed rank must always match RICE."
                )
            if st.button(
                "Apply formula-backed order",
                type="primary",
                disabled=not representable,
                width="stretch",
            ):
                result = db.apply_manual_reorder(requested_ids, reviewer_name)
                st.session_state["rerank_message"] = (
                    f"Updated {result['changed']} item(s) with a traceable Confidence change."
                )
                st.rerun()
        else:
            st.caption("Drag an item to preview the exact Confidence and RICE changes.")

        st.subheader("Review and adjust")
        labels = {
            int(row.id): (
                f"#{int(row.id)} · {row.issue}"
                + (" · MANUALLY ADJUSTED" if int(row.manually_adjusted) else "")
            )
            for row in backlog.itertuples()
        }
        selected_id = st.selectbox("Backlog item", labels, format_func=labels.get)
        item = backlog[backlog["id"] == selected_id].iloc[0]
        sources_for_item = frame(db.source_rows(int(selected_id)))
        with st.form("score_form"):
            score_columns = st.columns(4)
            reach = score_columns[0].number_input("Reach", min_value=0.0, value=float(item["reach"]), step=1.0)
            impact = score_columns[1].number_input("Impact", min_value=0.0, value=float(item["impact"]), step=0.5)
            confidence = score_columns[2].slider("Confidence", min_value=0.0, max_value=1.0, value=float(item["confidence"]), step=0.05)
            effort = score_columns[3].number_input("Effort", min_value=0.1, value=float(item["effort"]), step=0.5)
            preview_score = RiceScore(reach, impact, confidence, effort)
            st.info(f"New score: **{preview_score.score:.2f}** · {preview_score.explanation}")
            save = st.form_submit_button("Save reviewed score", type="primary")
            if save:
                db.update_score(int(selected_id), preview_score, reviewer_name)
                st.success("Score updated with a traceable formula.")
                st.rerun()

        if int(item["manually_adjusted"]):
            st.warning("🟠 Manually adjusted from the deterministic AI baseline.")
            if st.button("Reset to AI score", width="stretch"):
                db.reset_to_ai_score(int(selected_id), reviewer_name)
                st.success("Original deterministic RICE inputs restored.")
                st.rerun()

        adjustment_history = frame(db.priority_adjustment_rows(int(selected_id)))
        with st.expander(f"Adjustment audit trail ({len(adjustment_history)})"):
            if adjustment_history.empty:
                st.caption("No manual priority adjustments recorded for this item.")
            else:
                audit_display = adjustment_history[
                    [
                        "actor", "action", "from_position", "to_position",
                        "old_confidence", "new_confidence", "old_rice_score",
                        "new_rice_score", "created_at",
                    ]
                ].copy()
                audit_display.columns = [
                    "Who", "Action", "From rank", "To rank", "Old confidence",
                    "New confidence", "Old RICE", "New RICE", "When",
                ]
                st.dataframe(audit_display, width="stretch", hide_index=True)

        sync_col, status_col = st.columns((1, 2))
        with sync_col:
            if st.button("Sync this item to Jira", disabled=not settings.jira_enabled, width="stretch"):
                try:
                    refreshed = dict(next(row for row in db.backlog_rows() if int(row["id"]) == int(selected_id)))
                    result = JiraClient(settings).sync(refreshed)
                    db.update_jira(int(selected_id), result.key, result.url, "Synced to Jira")
                    st.success(f"Synced {result.key}")
                    st.rerun()
                except Exception as error:
                    st.error(f"Jira sync failed safely: {error}")
        with status_col:
            if not settings.jira_enabled:
                st.caption("Add Jira credentials in `.env` or Streamlit secrets to enable sync.")

        reviewed_count = int((backlog["status"] == "Reviewed").sum())
        st.markdown("#### Bulk Jira sync")
        st.caption(f"{reviewed_count} reviewed item(s) are ready. A failure never blocks the remaining items.")
        if st.session_state.get("bulk_sync_message"):
            st.success(st.session_state["bulk_sync_message"])
        if st.button(
            "Sync all reviewed items",
            disabled=not settings.jira_enabled or reviewed_count == 0,
            width="stretch",
        ):
            bulk_progress = st.progress(0, text="Preparing Jira batch…")
            bulk = sync_reviewed_items(db, settings, bulk_progress.progress)
            bulk_progress.empty()
            bulk_rate = bulk.succeeded / bulk.attempted if bulk.attempted else 0
            st.session_state["bulk_sync_message"] = (
                f"Bulk sync complete: {bulk.succeeded}/{bulk.attempted} succeeded "
                f"({bulk_rate:.1%}); {bulk.failed} failed without blocking the batch."
            )
            st.rerun()

        with st.expander(f"Source feedback ({len(sources_for_item)})", expanded=True):
            for source in sources_for_item.itertuples():
                st.markdown(f"**{source.subject}** · {source.language.upper()} · {source.priority}")
                if source.match_method and source.match_similarity is not None:
                    st.caption(
                        f"Matched at {float(source.match_similarity):.1f}% similarity "
                        f"via {str(source.match_method).title()}"
                    )
                st.write(source.body)
                st.divider()

with quality_tab:
    errors = frame(db.error_rows())
    backlog = frame(db.backlog_rows())
    total = len(db.source_rows()) + len(errors)
    success_rate = (total - len(errors)) / total if total else 0
    sync_history = frame(db.jira_sync_rows())
    measured_sync_rate = (
        sync_history["success"].astype(bool).mean() if not sync_history.empty else None
    )
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Pipeline success", f"{success_rate:.1%}")
    q2.metric("Semantic layer", "Active" if settings.semantic_dedup_active else "Fallback")
    q3.metric(
        "Bulk Jira success",
        f"{measured_sync_rate:.1%}" if measured_sync_rate is not None else "Not measured",
    )
    q4.metric("Batch speed target", "< 2 min / 50")

    st.markdown("#### Measured vs. target")
    evaluation = load_results()
    eval_options = st.columns((1, 2))
    use_gemini_eval = eval_options[0].checkbox(
        "Evaluate Gemini extraction", value=False, disabled=not settings.gemini_enabled
    )
    if eval_options[1].button("Run gold-set evaluation", width="stretch"):
        with st.spinner("Evaluating the labeled validation set…"):
            evaluation = run_evaluation(settings, use_gemini=use_gemini_eval)
            save_results(evaluation)
        st.success("Evaluation complete. These metrics come from the labeled gold set.")

    if evaluation:
        extraction = float(evaluation["extraction_accuracy"])
        dedup_precision = float(evaluation["hybrid_dedup"]["precision"])
        dedup_recall = float(evaluation["hybrid_dedup"]["recall"])
        metric_columns = st.columns(3)
        metric_columns[0].metric(
            "Extraction accuracy",
            f"{extraction:.1%}",
            delta=f"{(extraction - 0.85):+.1%} vs 85% target",
            delta_color="normal",
        )
        metric_columns[1].metric(
            "Dedup precision",
            f"{dedup_precision:.1%}",
            delta=f"{(dedup_precision - 0.80):+.1%} vs 80% target",
            delta_color="normal",
        )
        metric_columns[2].metric("Dedup recall", f"{dedup_recall:.1%}")
        recall_delta = evaluation.get("semantic_recall_delta")
        if recall_delta is None:
            st.info(
                "Semantic recall delta is not measured because semantic dedup is inactive. "
                "Set SEMANTIC_DEDUP_ENABLED=true and provide GEMINI_API_KEY, then rerun."
            )
        else:
            st.metric("Semantic recall improvement", f"{float(recall_delta):+.1%}")
        st.caption(
            f"Gold set: {evaluation['gold_set_size']} tickets · "
            f"Extraction: {evaluation['extraction_method']} · "
            f"Evaluated {evaluation['evaluated_at']}"
        )
    else:
        st.warning("No measured results yet. Run the gold-set evaluation to replace static targets.")

    st.markdown("#### Guardrails in this build")
    st.markdown(
        "- Gemini must return valid structured output; failures are logged and skipped.\n"
        "- Duplicate matching uses RapidFuzz first and optional Gemini embeddings second.\n"
        "- RICE is deterministic: `(Reach × Impact × Confidence) ÷ Effort`.\n"
        "- Manual re-ranks change Confidence only and are rejected unless recalculated RICE matches the requested order.\n"
        "- Jira sync is disabled until all credentials are configured.\n"
        "- Every backlog item retains its original source feedback."
    )
    with st.expander("Known limitations", expanded=True):
        st.markdown(
            "- The included 40-ticket gold set is curated and small; expand it before production claims.\n"
            "- Semantic matching incurs Gemini API usage and is inactive without credentials.\n"
            "- RapidFuzz can still miss paraphrases when semantic matching is off.\n"
            "- RICE inputs are deterministic heuristics until a product manager reviews them.\n"
            "- Local SQLite is suitable for the demo, but Community Cloud storage is ephemeral.\n"
            "- Jira field requirements vary by project and may need additional mapping."
        )
    if not errors.empty:
        st.subheader("Processing errors")
        st.dataframe(errors[["subject", "error", "created_at"]], width="stretch", hide_index=True)
    else:
        st.success("No processing errors logged.")

with architecture_tab:
    st.subheader("System architecture")
    st.caption(
        "See how the current MVP works today and how the target system expands it over time."
    )
    architecture_view = st.radio(
        "Architecture view",
        ARCHITECTURE_VIEWS,
        index=0,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown(render_architecture(architecture_view), unsafe_allow_html=True)
