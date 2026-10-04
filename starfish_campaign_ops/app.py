"""Starfish Campaign Operations & Reconciliation Automation.

Streamlit entry point.  Run with:

    streamlit run app.py

The UI is a thin layer over the deterministic backend (ingestion -> matching
-> reconciliation -> SQLite -> metrics/reports).  No business logic lives
here; no LLM is required for any number shown on screen.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Make package-relative imports work when launched via `streamlit run app.py`
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import streamlit as st  # noqa: E402

from config.settings import settings  # noqa: E402
from database import db  # noqa: E402

st.set_page_config(
    page_title="Starfish Campaign Ops",
    page_icon="⭐",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
/* ---- metric cards ---- */
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e6e8ee;
    border-left: 4px solid #1f5fbf;
    border-radius: 8px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
}
div[data-testid="stMetric"] label { color: #5b6472; font-weight: 600; }
div[data-testid="stMetricValue"] { font-size: 1.5rem; color: #17233b; }

/* ---- status badges ---- */
.sf-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: .02em;
    white-space: nowrap;
}
.sf-badge-green  { background:#e5f6ec; color:#1a7d42; }
.sf-badge-amber  { background:#fdf2dc; color:#9a6b00; }
.sf-badge-red    { background:#fdeaea; color:#b42318; }
.sf-badge-blue   { background:#e8f0fe; color:#1f5fbf; }
.sf-badge-gray   { background:#eef0f3; color:#5b6472; }

/* ---- tables ---- */
table.sf-table { width:100%; border-collapse:collapse; font-size:.86rem; }
table.sf-table th {
    background:#f2f5f9; color:#3a4356; text-align:left;
    padding:8px 10px; border-bottom:2px solid #dde3ea; font-weight:700;
}
table.sf-table td { padding:7px 10px; border-bottom:1px solid #edf0f4; color:#243044; }
table.sf-table tr:hover td { background:#f8fafc; }

/* ---- misc ---- */
.sidebar-content section { padding-top: 1rem; }
h1, h2, h3 { color:#17233b; }
.stApp footer { visibility: hidden; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# data access helpers (thin wrappers around the existing modules)
# ---------------------------------------------------------------------------

@st.cache_resource
def _db_conn():
    conn = db.connect(settings.db_path)
    db.init_db(conn)
    return conn


def _campaign_summary(conn):
    row = conn.execute(
        "SELECT client_name, campaign_name FROM campaigns LIMIT 1"
    ).fetchone()
    return row


def _has_data(conn) -> bool:
    n = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    return int(n) > 0


def load_demo():
    """Run the full deterministic pipeline over demo_data/ and persist it."""
    from demo_loader import load_demo as _load

    res = _load()               # persists to settings.db_path (wipes + reloads)
    _db_conn.clear()            # drop cached connection so UI reopens fresh DB
    return res


# ---------------------------------------------------------------------------
# navigation
# ---------------------------------------------------------------------------

PAGES = [
    ("Home", "ui.home"),
    ("Dashboard", "ui.dashboard"),
    ("Files", "ui.files"),
    ("Creators", "ui.creators"),
    ("Deliverables", "ui.deliverables"),
    ("Performance", "ui.performance"),
    ("Financials", "ui.financials"),
    ("Reconciliation", "ui.reconciliation"),
    ("Exceptions", "ui.exceptions"),
    ("Reports", "ui.reports"),
]

with st.sidebar:
    st.markdown("## ⭐ Starfish Ops")
    st.caption("Campaign operations & reconciliation automation")
    choice = st.radio("Navigation", [name for name, _ in PAGES], label_visibility="collapsed")
    st.divider()
    ai_on = settings.ai_enabled
    if ai_on:
        st.success(f"AI mode: {settings.qwen_mode}")
    else:
        st.info("AI features unavailable — running deterministic demo mode.")
    st.caption("Reconciliation is always deterministic Python. AI never touches numbers.")

page_module = dict(PAGES)[choice]

conn = _db_conn()
summary = _campaign_summary(conn)
if summary:
    st.sidebar.markdown(
        f"**{summary['campaign_name']}**\n\n{summary['client_name']}"
    )

# ---------------------------------------------------------------------------
# Home page (rendered here); every other page module exposes render(conn)
# ---------------------------------------------------------------------------

if page_module == "ui.home":
    st.title("Starfish Campaign Operations Automation")
    st.markdown(
        "Turn fragmented campaign files — contracts, invoices, payouts, "
        "deliverable trackers and analytics exports — into **one reconciled "
        "campaign record**, an exception queue, and report-ready outputs."
    )
    st.caption(
        "This is an operational automation layer around your existing "
        "analytics tooling — not another influencer analytics platform."
    )

    if _has_data(conn):
        s = summary
        st.subheader("Loaded campaign")
        c1, c2, c3 = st.columns(3)
        c1.metric("Client", s["client_name"])
        c2.metric("Campaign", s["campaign_name"])
        n_exc = conn.execute(
            "SELECT COUNT(*) FROM exceptions WHERE status='OPEN'"
        ).fetchone()[0]
        c3.metric("Open exceptions", int(n_exc))
        st.markdown("---")
        left, right = st.columns([2, 1])
        with left:
            if st.button("🔄 Reload Demo Campaign", use_container_width=True):
                with st.spinner("Processing campaign files…"):
                    try:
                        res = load_demo()
                        st.session_state["demo_result"] = res
                        st.rerun()
                    except Exception as exc:  # pragma: no cover
                        st.error(f"Demo load failed: {exc}")
        with right:
            if st.button("Continue to Dashboard →", use_container_width=True):
                st.info("Use the sidebar to open **Dashboard**.")
    else:
        st.info("No campaign loaded yet. Load the built-in demo or upload files on the Files page.")
        if st.button("🚀 Load Demo Campaign", type="primary", use_container_width=True):
            with st.spinner("Ingesting files, matching creators, reconciling…"):
                try:
                    res = load_demo()
                    st.session_state["demo_result"] = res
                    st.rerun()
                except Exception as exc:
                    st.error(f"Demo load failed: {exc}")
                    st.code(traceback.format_exc())

else:
    module = __import__(page_module, fromlist=["render"])
    try:
        module.render(conn)
    except Exception as exc:  # keep the app alive on per-page errors
        st.error(f"This page hit an error: {exc}")
        st.code(traceback.format_exc())
