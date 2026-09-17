from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from defect_triage import DefectTriageService
from defect_triage.reminders import PROFILES
from defect_triage.triage import STORY_POINT_SCALE

st.set_page_config(
    page_title="Defect Triage Assistant",
    page_icon="🛠️",
    layout="wide",
)


@st.cache_resource
def get_service() -> DefectTriageService:
    return DefectTriageService()


def display_time(value: str | None) -> str:
    if not value:
        return "—"
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def percent(value: float) -> str:
    return f"{value:.0%}"


def show_triage(detail: dict[str, Any]) -> None:
    defect = detail["defect"]
    triage = detail["triage"]
    if not triage:
        st.warning("No triage result is stored for this defect.")
        return

    st.subheader(f"Triage result for {defect['defect_key']}")
    metric_columns = st.columns(4)
    metric_columns[0].metric("Known-error assessment", triage["duplicate_classification"])
    metric_columns[1].metric(
        "Recommended team",
        triage.get("recommended_team_name") or "Needs manual triage",
        percent(triage["team_confidence"]),
    )
    metric_columns[2].metric(
        "Recommended points",
        str(triage["recommended_story_points"]),
        percent(triage["story_point_confidence"]),
    )
    metric_columns[3].metric("Current status", defect["status"])

    explanations = triage["explanation"]
    st.markdown(
        f"**Why:** {explanations['match']} {explanations['team']} {explanations['story_points']}"
    )

    known_tab, history_tab = st.tabs(["Known-error matches", "Historical matches"])
    with known_tab:
        rows = [
            {
                "Key": match["key"],
                "Title": match["title"],
                "Similarity": percent(match["score"]),
                "Strength": match["match_level"],
                "Owner": match["team_name"],
                "Workaround": match["workaround"],
            }
            for match in triage["known_matches"]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    with history_tab:
        rows = [
            {
                "Key": match["key"],
                "Title": match["title"],
                "Similarity": percent(match["score"]),
                "Owner": match["team_name"],
                "Points": match["story_points"],
                "Resolution": match["resolution"],
            }
            for match in triage["historical_matches"]
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def show_agent_activity(
    detail: dict[str, Any],
    schedules: list[dict[str, Any]],
    reminder_events: list[dict[str, Any]],
) -> None:
    defect = detail["defect"]
    triage = detail["triage"]
    if not triage:
        st.warning("No agent activity is available for this defect.")
        return

    schedule = next(
        (item for item in schedules if item["defect_id"] == defect["id"]), None
    )
    events = [item for item in reminder_events if item["defect_id"] == defect["id"]]
    top_known = triage["known_matches"][0] if triage["known_matches"] else None
    top_history = (
        triage["historical_matches"][0] if triage["historical_matches"] else None
    )

    stages = [
        {
            "name": "Intake agent",
            "state": "Complete",
            "task": "Validate and structure the incoming production defect.",
            "evidence": (
                f"{defect['component']} · {defect['environment']} · "
                f"{defect['severity']} severity · {len(defect['tags'])} tag(s)"
            ),
            "output": f"Created {defect['defect_key']} with status {defect['status']}.",
        },
        {
            "name": "Similarity agent",
            "state": "Complete",
            "task": "Compare the defect with known errors and closed historical tickets.",
            "evidence": (
                f"Top known error: {top_known['key']} ({percent(top_known['score'])}); "
                f"top closed defect: {top_history['key']} ({percent(top_history['score'])})."
                if top_known and top_history
                else "The available local corpus was searched."
            ),
            "output": triage["duplicate_classification"],
        },
        {
            "name": "Ownership agent",
            "state": "Complete",
            "task": "Infer the owning team from similar work and component history.",
            "evidence": triage["explanation"]["team"],
            "output": (
                f"Recommend {triage.get('recommended_team_name') or 'manual triage'} "
                f"with {percent(triage['team_confidence'])} confidence."
            ),
        },
        {
            "name": "Estimation agent",
            "state": "Complete",
            "task": "Estimate effort using story points from comparable closed tickets.",
            "evidence": triage["explanation"]["story_points"],
            "output": (
                f"Recommend {triage['recommended_story_points']} story points "
                f"with {percent(triage['story_point_confidence'])} confidence."
            ),
        },
        {
            "name": "Reminder agent",
            "state": "Monitoring" if schedule and schedule["active"] else "Stopped",
            "task": "Schedule follow-ups while the defect remains open.",
            "evidence": (
                f"Profile: {schedule['profile']}; generated reminder events: {len(events)}."
                if schedule
                else "No reminder schedule is available."
            ),
            "output": (
                f"Next follow-up: {display_time(schedule['next_due_at'])}."
                if schedule and schedule["active"]
                else "Future reminders are cancelled."
            ),
        },
        {
            "name": "Lifecycle agent",
            "state": "Closed" if defect["status"] == "Closed" else "Tracking",
            "task": "Track status changes and stop follow-ups when work is closed.",
            "evidence": f"{len(detail['status_history'])} lifecycle event(s) recorded.",
            "output": f"Current lifecycle status: {defect['status']}.",
        },
    ]

    for step, stage in enumerate(stages, start=1):
        with st.container(border=True):
            heading, state = st.columns([4, 1])
            heading.markdown(f"#### {step}. {stage['name']}")
            state.markdown(f"**{stage['state']}**")
            st.caption(stage["task"])
            evidence, output = st.columns(2)
            evidence.markdown(f"**Evidence**  \n{stage['evidence']}")
            output.markdown(f"**Output**  \n{stage['output']}")


service = get_service()
service.process_due_reminders()
defects = service.list_defects()

st.title("Defect Triage Assistant Agent")
st.caption(
    "Local, explainable defect matching, ownership and sizing recommendations, "
    "plus lifecycle-aware reminders."
)
if flash_message := st.session_state.pop("flash_message", None):
    st.success(flash_message)

with st.sidebar:
    st.header("MVP status")
    st.metric("Tracked defects", len(defects))
    st.metric("Open defects", sum(item["status"] != "Closed" for item in defects))
    due_count = sum(event["state"] == "Due" for event in service.list_reminder_events())
    st.metric("Due reminders", due_count)
    st.caption("All application data is synthetic and stored locally in SQLite.")

new_tab, agent_tab, tracker_tab, reminder_tab, knowledge_tab = st.tabs(
    ["New defect", "Agent activity", "Defect tracker", "Reminders", "Knowledge base"]
)

with new_tab:
    st.subheader("Analyze a production defect")
    if st.button("Load demo defect", type="secondary"):
        st.session_state.update(
            {
                "new_title": "Checkout times out after gateway authorization",
                "new_description": (
                    "Customers see a spinner and then a timeout during card payment. "
                    "The external gateway response is successful, but the order is not confirmed."
                ),
                "new_component": "Checkout",
                "new_environment": "Production",
                "new_severity": "High",
                "new_tags": "payment, timeout, gateway, spinner",
            }
        )
        st.rerun()

    with st.form("new_defect_form"):
        title = st.text_input("Title", key="new_title")
        description = st.text_area("Description", height=130, key="new_description")
        field_columns = st.columns(3)
        component = field_columns[0].selectbox(
            "Component", service.list_components(), key="new_component"
        )
        environment = field_columns[1].selectbox(
            "Environment", ["Production", "Staging", "Test"], key="new_environment"
        )
        severity = field_columns[2].selectbox(
            "Severity", ["Critical", "High", "Medium", "Low"], key="new_severity"
        )
        tags_text = st.text_input(
            "Tags (comma-separated)",
            placeholder="payment, timeout, gateway",
            key="new_tags",
        )
        profile = st.selectbox(
            "Reminder profile",
            list(PROFILES),
            index=0,
            help="Demo uses seconds; Standard uses 1 day, 3 days, then weekly.",
        )
        submitted = st.form_submit_button("Analyze and create defect", type="primary")

    if submitted:
        try:
            defect_id = service.create_defect(
                {
                    "title": title.strip(),
                    "description": description.strip(),
                    "component": component,
                    "environment": environment,
                    "severity": severity,
                    "tags": [tag.strip() for tag in tags_text.split(",") if tag.strip()],
                },
                reminder_profile=profile,
            )
            st.session_state["latest_defect_id"] = defect_id
            st.session_state["flash_message"] = "Defect created and triaged."
            st.rerun()
        except ValueError as error:
            st.error(str(error))

    latest_id = st.session_state.get("latest_defect_id")
    if latest_id:
        latest_detail = service.get_defect_detail(latest_id)
        if latest_detail:
            show_triage(latest_detail)

with agent_tab:
    st.subheader("Agent activity")
    st.caption(
        "These are logical specialist roles orchestrated inside one local process. "
        "They are transparent workflow stages, not separate hosted AI services."
    )
    agent_defects = service.list_defects()
    if not agent_defects:
        st.info("Create a defect to see each agent's evidence and output.")
    else:
        agent_defect_id = st.selectbox(
            "Inspect agent work for",
            [item["id"] for item in agent_defects],
            format_func=lambda value: next(
                f"{item['defect_key']} — {item['title']}"
                for item in agent_defects
                if item["id"] == value
            ),
            key="agent-defect-selector",
        )
        agent_detail = service.get_defect_detail(agent_defect_id)
        if agent_detail:
            show_agent_activity(
                agent_detail,
                service.list_reminder_schedules(),
                service.list_reminder_events(),
            )

with tracker_tab:
    defects = service.list_defects()
    st.subheader("Tracked defects")
    if not defects:
        st.info("Create a defect to begin tracking its lifecycle.")
    else:
        st.dataframe(
            [
                {
                    "Key": item["defect_key"],
                    "Title": item["title"],
                    "Status": item["status"],
                    "Severity": item["severity"],
                    "Team": item.get("assigned_team_name") or "Unassigned",
                    "Points": item.get("accepted_story_points"),
                    "Updated": display_time(item["updated_at"]),
                }
                for item in defects
            ],
            use_container_width=True,
            hide_index=True,
        )
        selected_id = st.selectbox(
            "Select defect",
            [item["id"] for item in defects],
            format_func=lambda value: next(
                f"{item['defect_key']} — {item['title']}" for item in defects if item["id"] == value
            ),
        )
        detail = service.get_defect_detail(selected_id)
        if detail:
            defect = detail["defect"]
            action_columns = st.columns(2)
            with action_columns[0]:
                transitions = service.available_statuses(defect["status"])
                if transitions:
                    target_status = st.selectbox("Next status", transitions)
                    if st.button("Update status", type="primary"):
                        service.change_status(selected_id, target_status)
                        st.success(f"Status updated to {target_status}.")
                        st.rerun()
            with action_columns[1]:
                teams = service.list_teams()
                team_ids = [team["id"] for team in teams]
                current_team_index = (
                    team_ids.index(defect["assigned_team_id"])
                    if defect["assigned_team_id"] in team_ids
                    else 0
                )
                selected_team = st.selectbox(
                    "Assigned team",
                    team_ids,
                    index=current_team_index,
                    format_func=lambda value: next(
                        team["name"] for team in teams if team["id"] == value
                    ),
                )
                current_points = defect["accepted_story_points"] or 3
                selected_points = st.selectbox(
                    "Accepted story points",
                    STORY_POINT_SCALE,
                    index=STORY_POINT_SCALE.index(current_points),
                )
                if st.button("Save assignment and estimate"):
                    service.update_assignment(selected_id, selected_team, selected_points)
                    st.success("Assignment and estimate saved.")
                    st.rerun()

            with st.expander("Status history"):
                st.dataframe(
                    [
                        {
                            "From": event["from_status"] or "Created",
                            "To": event["to_status"],
                            "Changed": display_time(event["changed_at"]),
                        }
                        for event in detail["status_history"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            show_triage(detail)

with reminder_tab:
    st.subheader("Follow-up reminders")
    control_columns = st.columns(2)
    if control_columns[0].button("Check for due reminders"):
        count = service.process_due_reminders()
        st.success(f"Reminder check completed; {count} reminder(s) became due.")
        st.rerun()

    open_defects = [item for item in service.list_defects() if item["status"] != "Closed"]
    if open_defects:
        demo_id = control_columns[1].selectbox(
            "Demo reminder for",
            [item["id"] for item in open_defects],
            format_func=lambda value: next(
                item["defect_key"] for item in open_defects if item["id"] == value
            ),
        )
        if control_columns[1].button("Make next reminder due now"):
            service.force_reminder_due(demo_id)
            st.success("The next reminder was triggered for the demo.")
            st.rerun()

    schedules = service.list_reminder_schedules()
    if schedules:
        st.markdown("#### Schedules")
        st.dataframe(
            [
                {
                    "Defect": row["defect_key"],
                    "Status": row["defect_status"],
                    "Profile": row["profile"],
                    "Schedule": "Active" if row["active"] else "Cancelled",
                    "Next due": display_time(row["next_due_at"]),
                    "Cancelled": display_time(row["cancelled_at"]),
                }
                for row in schedules
            ],
            use_container_width=True,
            hide_index=True,
        )

    events = service.list_reminder_events()
    st.markdown("#### Reminder history")
    if not events:
        st.info("No reminders have become due yet.")
    else:
        for event in events:
            event_columns = st.columns([2, 5, 2, 2])
            event_columns[0].write(event["defect_key"])
            event_columns[1].write(event["title"])
            event_columns[2].write(f"{event['state']} · {display_time(event['due_at'])}")
            if event["state"] == "Due" and event_columns[3].button(
                "Acknowledge", key=f"ack-{event['id']}"
            ):
                service.acknowledge_reminder(event["id"])
                st.rerun()

with knowledge_tab:
    known_subtab, history_subtab = st.tabs(["Known errors", "Closed defects"])
    with known_subtab:
        st.dataframe(
            [
                {
                    "Key": item["error_key"],
                    "Title": item["title"],
                    "Component": item["component"],
                    "Owner": item["team_name"],
                    "Workaround": item["workaround"],
                }
                for item in service.list_known_errors()
            ],
            use_container_width=True,
            hide_index=True,
        )
    with history_subtab:
        st.dataframe(
            [
                {
                    "Key": item["defect_key"],
                    "Title": item["title"],
                    "Component": item["component"],
                    "Owner": item["team_name"],
                    "Points": item["story_points"],
                    "Resolution": item["resolution"],
                }
                for item in service.list_historical_defects()
            ],
            use_container_width=True,
            hide_index=True,
        )
