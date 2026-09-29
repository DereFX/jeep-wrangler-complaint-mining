"""Read-only Streamlit dashboard for the REST API."""

import json
import os
import hmac
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
API_TOKEN = os.environ.get("API_BEARER_TOKEN")


def get_json(path: str) -> dict:
    request = Request(API_BASE + path, headers={"Authorization": "Bearer " + API_TOKEN})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


@st.cache_data(ttl=30)
def load_data() -> tuple[dict, list[dict]]:
    summary = get_json("/summary")
    claims = []
    cursor = None
    while len(claims) < 5000:
        query = "?" + urlencode({"limit": 200, **({"cursor": cursor} if cursor else {})})
        page = get_json("/claims" + query)
        claims.extend(page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return summary, claims


st.set_page_config(page_title="Wrangler Complaint Signals", layout="wide")
st.title("Jeep Wrangler electrical complaint signals")
st.caption("Complaint patterns for analyst review. Counts are not failure rates or confirmed defects.")

if not API_TOKEN:
    st.error("API_BEARER_TOKEN is required for the dashboard to read claims.")
    st.stop()

entered_token = st.text_input("Dashboard access token", type="password")
if not entered_token or not hmac.compare_digest(entered_token, API_TOKEN):
    if entered_token:
        st.error("Invalid access token")
    st.stop()

try:
    summary, claims = load_data()
except Exception as error:
    st.error(f"Could not load the complaint API: {error}")
    st.stop()

if not claims:
    st.info("No processed claims yet. Submit a small batch through the REST API.")
    st.stop()

families = {row["issue_family"]: row["count"] for row in summary["by_issue_family"]}
labels = {row["issue_family"]: row.get("issue_label", row["issue_family"]) for row in claims}
top_family = max(families, key=families.get)
first, second, third = st.columns(3)
first.metric("Processed complaints", summary["total_claims"])
second.metric("Largest issue group", f"{families[top_family]} complaints", help=labels.get(top_family, top_family))
third.metric("Needs analyst review", summary["needs_review"])

monthly = pd.DataFrame(summary["monthly_by_issue"])
monthly["issue"] = monthly["issue_family"].map(lambda value: labels.get(value, value))
chart = monthly.pivot_table(index="received_month", columns="issue", values="count", aggfunc="sum", fill_value=0)
all_months = pd.period_range(chart.index.min(), chart.index.max(), freq="M").astype(str)
chart = chart.reindex(all_months, fill_value=0)
st.subheader("Monthly complaint volume by issue")
st.line_chart(chart)

choices = ["All issues"] + [labels.get(key, key) for key in families]
selected = st.selectbox("Issue group", choices)
selected_key = next((key for key in families if labels.get(key, key) == selected), None)
filtered = [row for row in claims if selected_key is None or row["issue_family"] == selected_key]
filtered.sort(key=lambda row: (row.get("received_date") or "", row.get("complaint_id") or ""), reverse=True)
st.subheader(f"Complaints ({len(filtered)})")
table = pd.DataFrame(filtered)
columns = [key for key in ("complaint_id", "received_date", "model_year", "issue_label", "symptom_summary", "needs_human_review") if key in table]
st.dataframe(table[columns], use_container_width=True, hide_index=True)

ids = [row["complaint_id"] for row in filtered]
chosen = st.selectbox("Read a complaint", ids)
record = next(row for row in filtered if row["complaint_id"] == chosen)
st.write(record.get("narrative", ""))
st.caption(f"AI provider: {record.get('ai_provider', 'unknown')}. Review labels against the original report before acting.")
