"""Elevator Service Dashboard — Streamlit UI connected to the FastAPI backend."""

import os
from datetime import datetime, date
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ── Configuration ──────────────────────────────────────────────────────────────
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Elevator Service Dashboard",
    page_icon="🛗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def api(method: str, path: str, token: Optional[str] = None, **kwargs):
    """Thin wrapper around requests with optional Bearer auth."""
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.request(
            method, f"{API_BASE}{path}", headers=headers, timeout=10, **kwargs
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to API — make sure the backend is running on port 8000.")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            st.session_state.token = None
            st.warning("Session expired — please log in again.")
        else:
            st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
        return None


def status_badge(status: str) -> str:
    colors = {
        "ACTIVE": "🟢", "INACTIVE": "🔴", "UNDER_REPAIR": "🟡",
        "OPEN": "🔵", "ASSIGNED": "🟡", "IN_PROGRESS": "🟠",
        "RESOLVED": "🟢", "CLOSED": "⚫",
        "SCHEDULED": "🔵", "COMPLETED": "🟢", "OVERDUE": "🔴", "CANCELLED": "⚫",
    }
    return f"{colors.get(status, '⚪')} {status}"


def risk_color(score: float) -> str:
    if score >= 70:
        return "🔴"
    if score >= 40:
        return "🟡"
    return "🟢"


# ── Session state ──────────────────────────────────────────────────────────────
if "token" not in st.session_state:
    st.session_state.token = None
if "page" not in st.session_state:
    st.session_state.page = "elevators"

# ── Login screen ───────────────────────────────────────────────────────────────
if not st.session_state.token:
    st.markdown(
        "<h1 style='text-align:center;margin-top:80px'>🛗 Elevator Service</h1>",
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.form("login"):
            st.subheader("Login")
            email = st.text_input("Email", value="admin@example.com")
            password = st.text_input("Password", type="password", value="admin1234")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
        if submitted:
            result = api(
                "POST", "/auth/login",
                data={"username": email, "password": password},
            )
            if result and "access_token" in result:
                st.session_state.token = result["access_token"]
                st.success("Logged in!")
                st.rerun()
    st.stop()

TOKEN = st.session_state.token

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛗 Elevator Service")
    st.divider()
    pages = {
        "elevators":   "🏢  Elevators",
        "calls":       "📞  Service Calls",
        "technicians": "👷  Technicians",
        "maintenance": "🔧  Maintenance",
        "analytics":   "📊  Analytics",
    }
    for key, label in pages.items():
        if st.button(label, use_container_width=True,
                     type="primary" if st.session_state.page == key else "secondary"):
            st.session_state.page = key
            st.rerun()
    st.divider()
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.token = None
        st.rerun()

page = st.session_state.page

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ELEVATORS
# ══════════════════════════════════════════════════════════════════════════════
if page == "elevators":
    st.title("🏢 Elevators")

    # ── Filters ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        city_filter = st.text_input("Filter by city", placeholder="Tel Aviv…")
    with col2:
        status_filter = st.selectbox("Status", ["All", "ACTIVE", "INACTIVE", "UNDER_REPAIR"])
    with col3:
        min_risk = st.slider("Min risk score", 0, 100, 0)
    with col4:
        st.write("")
        st.write("")
        refresh = st.button("🔄 Refresh", use_container_width=True)

    params: dict = {"limit": 200}
    if city_filter:
        params["city"] = city_filter
    if status_filter != "All":
        params["status"] = status_filter
    if min_risk > 0:
        params["min_risk"] = min_risk

    elevators = api("GET", "/elevators", token=TOKEN, params=params) or []

    if not elevators:
        st.info("No elevators found.")
        st.stop()

    # ── KPI cards ──
    total = len(elevators)
    active = sum(1 for e in elevators if e["status"] == "ACTIVE")
    under_repair = sum(1 for e in elevators if e["status"] == "UNDER_REPAIR")
    high_risk = sum(1 for e in elevators if e["risk_score"] >= 70)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Elevators", total)
    k2.metric("Active", active, delta=f"{active/total*100:.0f}%" if total else "")
    k3.metric("Under Repair", under_repair)
    k4.metric("High Risk (≥70)", high_risk, delta_color="inverse")

    st.divider()

    # ── Charts row ──
    col_left, col_right = st.columns(2)

    with col_left:
        status_counts = {}
        for e in elevators:
            status_counts[e["status"]] = status_counts.get(e["status"], 0) + 1
        fig = px.pie(
            values=list(status_counts.values()),
            names=list(status_counts.keys()),
            title="Status Distribution",
            color_discrete_map={"ACTIVE": "#22c55e", "INACTIVE": "#ef4444", "UNDER_REPAIR": "#f59e0b"},
            hole=0.4,
        )
        fig.update_layout(margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        df_risk = pd.DataFrame(
            [{"city": e["city"], "risk": e["risk_score"]} for e in elevators]
        )
        city_risk = df_risk.groupby("city")["risk"].mean().reset_index()
        city_risk.columns = ["City", "Avg Risk Score"]
        fig2 = px.bar(
            city_risk.sort_values("Avg Risk Score", ascending=False),
            x="City", y="Avg Risk Score",
            title="Average Risk Score by City",
            color="Avg Risk Score",
            color_continuous_scale=["#22c55e", "#f59e0b", "#ef4444"],
            range_color=[0, 100],
        )
        fig2.update_layout(margin=dict(t=40, b=0, l=0, r=0), coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── Elevator table ──
    st.subheader(f"All Elevators ({total})")
    rows = []
    for e in elevators:
        rows.append({
            "": risk_color(e["risk_score"]),
            "Address": e["address"],
            "City": e["city"],
            "Building": e.get("building_name") or "—",
            "Floors": e["floor_count"],
            "Model": e.get("model") or "—",
            "Status": status_badge(e["status"]),
            "Risk Score": f"{e['risk_score']:.0f}",
            "Next Service": e.get("next_service_date") or "—",
        })
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        height=min(40 + len(rows) * 35, 600),
    )

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SERVICE CALLS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "calls":
    st.title("📞 Service Calls")

    col1, col2, col3 = st.columns(3)
    with col1:
        status_f = st.selectbox("Status", ["All", "OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"])
    with col2:
        priority_f = st.selectbox("Priority", ["All", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
    with col3:
        fault_f = st.selectbox("Fault Type", ["All", "MECHANICAL", "ELECTRICAL", "SOFTWARE", "STUCK", "DOOR", "OTHER"])

    params = {"limit": 200}
    if status_f != "All":
        params["status"] = status_f
    if priority_f != "All":
        params["priority"] = priority_f
    if fault_f != "All":
        params["fault_type"] = fault_f

    calls = api("GET", "/calls", token=TOKEN, params=params) or []

    if not calls:
        st.info("No service calls found.")
        st.stop()

    # KPIs
    total_c = len(calls)
    open_c = sum(1 for c in calls if c["status"] == "OPEN")
    critical_c = sum(1 for c in calls if c["priority"] == "CRITICAL")
    recurring_c = sum(1 for c in calls if c["is_recurring"])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Calls", total_c)
    k2.metric("Open", open_c)
    k3.metric("Critical", critical_c, delta_color="inverse")
    k4.metric("Recurring ⚠️", recurring_c, delta_color="inverse")

    st.divider()

    # Charts
    col_l, col_r = st.columns(2)
    with col_l:
        p_counts = {}
        for c in calls:
            p_counts[c["priority"]] = p_counts.get(c["priority"], 0) + 1
        p_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        p_vals = [p_counts.get(p, 0) for p in p_order]
        fig = px.bar(
            x=p_order, y=p_vals,
            title="Calls by Priority",
            color=p_order,
            color_discrete_map={"CRITICAL": "#ef4444", "HIGH": "#f97316", "MEDIUM": "#f59e0b", "LOW": "#22c55e"},
        )
        fig.update_layout(showlegend=False, margin=dict(t=40, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        ft_counts = {}
        for c in calls:
            ft_counts[c["fault_type"]] = ft_counts.get(c["fault_type"], 0) + 1
        fig2 = px.pie(
            values=list(ft_counts.values()),
            names=list(ft_counts.keys()),
            title="Calls by Fault Type",
            hole=0.4,
        )
        fig2.update_layout(margin=dict(t=40, b=0))
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader(f"All Service Calls ({total_c})")

    priority_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
    rows = []
    for c in calls:
        rows.append({
            "Priority": f"{priority_icon.get(c['priority'], '')} {c['priority']}",
            "Status": status_badge(c["status"]),
            "Fault": c["fault_type"],
            "Reported By": c["reported_by"],
            "Description": c["description"][:60] + ("…" if len(c["description"]) > 60 else ""),
            "Recurring": "⚠️ Yes" if c["is_recurring"] else "No",
            "Created": c["created_at"][:16].replace("T", " "),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                 height=min(40 + len(rows) * 35, 600))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: TECHNICIANS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "technicians":
    st.title("👷 Technicians")

    technicians = api("GET", "/technicians", token=TOKEN, params={"limit": 100}) or []

    if not technicians:
        st.info("No technicians found.")
        st.stop()

    total_t = len(technicians)
    available_t = sum(1 for t in technicians if t["is_available"])
    active_t = sum(1 for t in technicians if t["is_active"])

    k1, k2, k3 = st.columns(3)
    k1.metric("Total Technicians", total_t)
    k2.metric("Available Now", available_t)
    k3.metric("Active", active_t)

    st.divider()

    for tech in technicians:
        avail_icon = "🟢" if tech["is_available"] else "🔴"
        with st.expander(f"{avail_icon} {tech['name']} — {tech['role']}", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.write(f"**Email:** {tech['email']}")
            col1.write(f"**Phone:** {tech.get('phone') or '—'}")
            col2.write(f"**Role:** {tech['role']}")
            col2.write(f"**Max daily calls:** {tech['max_daily_calls']}")
            col3.write(f"**Specializations:** {', '.join(tech['specializations']) or '—'}")
            col3.write(f"**Area codes:** {', '.join(tech['area_codes']) or '—'}")

            # Stats
            stats = api("GET", f"/technicians/{tech['id']}/stats", token=TOKEN)
            if stats:
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("Total Assigned", stats["total_calls_assigned"])
                s2.metric("Resolved", stats["total_calls_resolved"])
                s3.metric("Avg Resolution", f"{stats['avg_resolution_hours']:.1f}h" if stats["avg_resolution_hours"] else "—")
                s4.metric("Today's Calls", stats["calls_today"])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: MAINTENANCE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "maintenance":
    st.title("🔧 Maintenance Schedule")

    col1, col2 = st.columns(2)
    with col1:
        status_f = st.selectbox("Status", ["All", "SCHEDULED", "COMPLETED", "OVERDUE", "CANCELLED"])
    with col2:
        type_f = st.selectbox("Type", ["All", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "INSPECTION"])

    params = {"limit": 200}
    if status_f != "All":
        params["status"] = status_f

    maintenances = api("GET", "/maintenance", token=TOKEN, params=params) or []
    if type_f != "All":
        maintenances = [m for m in maintenances if m["maintenance_type"] == type_f]

    if not maintenances:
        st.info("No maintenance events found.")
        st.stop()

    total_m = len(maintenances)
    scheduled_m = sum(1 for m in maintenances if m["status"] == "SCHEDULED")
    overdue_m = sum(1 for m in maintenances if m["status"] == "OVERDUE")
    completed_m = sum(1 for m in maintenances if m["status"] == "COMPLETED")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Events", total_m)
    k2.metric("Scheduled", scheduled_m)
    k3.metric("Overdue 🚨", overdue_m, delta_color="inverse")
    k4.metric("Completed", completed_m)

    st.divider()

    # Timeline chart
    if maintenances:
        rows_m = []
        for m in maintenances:
            rows_m.append({
                "ID": str(m["id"])[:8],
                "Type": m["maintenance_type"],
                "Status": m["status"],
                "Date": m["scheduled_date"],
            })
        df_m = pd.DataFrame(rows_m)
        df_m["Date"] = pd.to_datetime(df_m["Date"])
        monthly = df_m.groupby([df_m["Date"].dt.to_period("M").astype(str), "Status"]).size().reset_index()
        monthly.columns = ["Month", "Status", "Count"]
        fig = px.bar(
            monthly, x="Month", y="Count", color="Status",
            title="Maintenance Events by Month",
            color_discrete_map={"SCHEDULED": "#3b82f6", "COMPLETED": "#22c55e",
                                 "OVERDUE": "#ef4444", "CANCELLED": "#6b7280"},
        )
        fig.update_layout(margin=dict(t=40, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader(f"All Events ({total_m})")

    rows_table = []
    for m in maintenances:
        rows_table.append({
            "Status": status_badge(m["status"]),
            "Type": m["maintenance_type"],
            "Scheduled Date": m["scheduled_date"],
            "Elevator ID": str(m["elevator_id"])[:8] + "…",
            "Technician": str(m.get("technician_id") or "Unassigned")[:8],
            "Completed": m["completed_at"][:10] if m.get("completed_at") else "—",
        })
    st.dataframe(pd.DataFrame(rows_table), use_container_width=True, hide_index=True,
                 height=min(40 + len(rows_table) * 35, 500))

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "analytics":
    st.title("📊 Analytics")

    now = datetime.now()
    col1, col2 = st.columns(2)
    with col1:
        year = st.selectbox("Year", list(range(now.year, now.year - 3, -1)))
    with col2:
        month = st.selectbox("Month", list(range(1, 13)),
                             index=now.month - 1,
                             format_func=lambda m: datetime(2000, m, 1).strftime("%B"))

    summary = api("GET", f"/analytics/monthly-summary?year={year}&month={month}", token=TOKEN)

    if summary:
        st.subheader(f"Monthly Summary — {datetime(year, month, 1).strftime('%B %Y')}")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Calls", summary["total_calls"])
        k2.metric("Resolved", summary["resolved_calls"])
        k3.metric("Resolution Rate", f"{summary['resolution_rate']}%")
        k4.metric("Recurring Calls", summary["recurring_calls"])
        k5.metric("Avg Resolution", f"{summary['avg_resolution_hours']:.1f}h" if summary["avg_resolution_hours"] else "—")

        col_l, col_r = st.columns(2)
        with col_l:
            if summary["calls_by_priority"]:
                fig_p = px.bar(
                    x=list(summary["calls_by_priority"].keys()),
                    y=list(summary["calls_by_priority"].values()),
                    title="Calls by Priority",
                    color=list(summary["calls_by_priority"].keys()),
                    color_discrete_map={"CRITICAL": "#ef4444", "HIGH": "#f97316",
                                        "MEDIUM": "#f59e0b", "LOW": "#22c55e"},
                )
                fig_p.update_layout(showlegend=False, margin=dict(t=40, b=0))
                st.plotly_chart(fig_p, use_container_width=True)

        with col_r:
            if summary["calls_by_fault_type"]:
                fig_f = px.pie(
                    values=list(summary["calls_by_fault_type"].values()),
                    names=list(summary["calls_by_fault_type"].keys()),
                    title="Calls by Fault Type",
                    hole=0.4,
                )
                fig_f.update_layout(margin=dict(t=40, b=0))
                st.plotly_chart(fig_f, use_container_width=True)

    st.divider()

    # Risk elevators
    st.subheader("🚨 High Risk Elevators (score ≥ 70)")
    risk_threshold = st.slider("Risk threshold", 0, 100, 70)
    risk_data = api("GET", f"/analytics/risk-elevators?threshold={risk_threshold}", token=TOKEN) or []

    if risk_data:
        df_risk = pd.DataFrame([{
            "Address": r["address"],
            "City": r["city"],
            "Building": r.get("building_name") or "—",
            "Risk Score": r["risk_score"],
            "Status": r["status"],
            "Next Service": r.get("next_service_date") or "—",
        } for r in risk_data])

        fig_risk = px.bar(
            df_risk.sort_values("Risk Score", ascending=True),
            x="Risk Score", y="Address",
            orientation="h",
            title=f"Elevators with Risk Score ≥ {risk_threshold}",
            color="Risk Score",
            color_continuous_scale=["#f59e0b", "#ef4444"],
            range_color=[risk_threshold, 100],
        )
        fig_risk.update_layout(margin=dict(t=40, b=0), yaxis_title="")
        st.plotly_chart(fig_risk, use_container_width=True)
    else:
        st.success(f"No elevators with risk score ≥ {risk_threshold} 🎉")

    st.divider()

    # Technician performance
    st.subheader("👷 Technician Performance")
    perf = api("GET", "/analytics/technician-performance", token=TOKEN) or []
    if perf:
        df_perf = pd.DataFrame([{
            "Name": p["name"],
            "Total Assigned": p["total_assigned"],
            "Total Resolved": p["total_resolved"],
            "Avg Resolution (h)": f"{p['avg_resolution_hours']:.1f}" if p["avg_resolution_hours"] else "—",
        } for p in perf])
        st.dataframe(df_perf, use_container_width=True, hide_index=True)
