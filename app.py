import io
import os
import base64
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# -------------------------
# UI CONFIG
# -------------------------
st.set_page_config(
    page_title="Transaction Risk Scoring",
    page_icon="🕵️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
        .metric-box {
            padding: 15px;
            border-radius: 12px;
            background: #f9f9f9;
            box-shadow: 0px 2px 6px rgba(0,0,0,0.05);
            text-align: center;
        }
        .risk-high {color: #e63946; font-weight: bold;}
        .risk-medium {color: #f4a261; font-weight: bold;}
        .risk-low {color: #2a9d8f; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

st.title("🕵️ Transaction Risk Scoring Dashboard")
st.caption("Upload transactions → score risk → analyze top risks & portfolio distribution.")

# -------------------------
# Helper Functions
# -------------------------
def make_download_link(df: pd.DataFrame, filename: str) -> str:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    b64 = base64.b64encode(csv_bytes).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="color: #0068c9; font-weight: bold;">⬇️ Download Scored CSV</a>'

# Risk Configurations
HIGH_RISK_COUNTRIES = {"IR", "KP", "SY", "CU", "RU", "UA", "AF", "IQ", "YE", "SO", "SD", "CD"}
RISKY_MERCHANT_CATS = {"gambling", "crypto", "virtual_goods", "adult", "gift_cards"}
KYC_TIER_SCORES = {"tier_1": 10, "basic": 10, "lite": 10, "tier_2": 5, "standard": 5, "tier_3": 0, "enhanced": 0, "full": 0}
CATEGORY_RULES = {"Low": (0, 39), "Medium": (40, 69), "High": (70, 100)}

# -------------------------
# Risk Scoring Engine
# -------------------------
def to_float(x):
    try:
        if x is None or (isinstance(x, str) and x.strip() == ""):
            return None
        return float(x)
    except Exception:
        return None

def score_transaction(row: pd.Series) -> int:
    score = 10
    sanctioned = str(row.get("sanctioned_party_flag", 0)).strip()
    if sanctioned in {"1", "true", "True", "TRUE"} or sanctioned == 1:
        return 100
    amt = to_float(row.get("amount_usd"))
    if amt:
        score += 20 if amt > 10000 else 15 if amt > 5000 else 10 if amt > 1000 else 0
    sc, rc = str(row.get("sender_country", "")).upper(), str(row.get("receiver_country", "")).upper()
    if sc and rc and sc != rc:
        score += 5
    if sc in HIGH_RISK_COUNTRIES or rc in HIGH_RISK_COUNTRIES:
        score += 15
    score += KYC_TIER_SCORES.get(str(row.get("kyc_tier", "")).lower().strip(), 5)
    v1h, v24h = to_float(row.get("velocity_1h")), to_float(row.get("velocity_24h"))
    if v1h:
        score += 15 if v1h > 5 else 8 if v1h > 2 else 0
    if v24h:
        score += 10 if v24h > 20 else 5 if v24h > 10 else 0
    if str(row.get("merchant_category", "")).lower().strip() in RISKY_MERCHANT_CATS:
        score += 10
    if str(row.get("device_change_flag", 0)).strip() in {"1", "true", "True", "TRUE"}:
        score += 10
    age = to_float(row.get("customer_age_days"))
    if age:
        score += 15 if age < 30 else 10 if age < 90 else 5 if age < 365 else 0
    prior = to_float(row.get("prior_txn_24h"))
    if prior:
        score += 10 if prior > 10 else 5 if prior > 3 else 0
    return max(0, min(100, int(round(score))))

def categorize(score: int) -> str:
    for name, (lo, hi) in CATEGORY_RULES.items():
        if lo <= score <= hi:
            return name
    return "Low"

# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    st.info("Tune business rules in code if needed.")
    st.json(CATEGORY_RULES)
    st.markdown("**High-Risk Countries**")
    st.code(", ".join(sorted(HIGH_RISK_COUNTRIES)))
    st.markdown("**Risky Merchant Categories**")
    st.code(", ".join(sorted(RISKY_MERCHANT_CATS)))

# -------------------------
# Upload CSV
# -------------------------
required_cols = ["txn_id","timestamp","sender_country","receiver_country","amount_usd","channel","customer_age_days","prior_txn_24h","sanctioned_party_flag","kyc_tier","merchant_category","velocity_1h","velocity_24h","device_change_flag"]

uploaded = st.file_uploader("📂 Upload Transactions CSV", type=["csv"])

if not uploaded:
    st.info("⬆️ Upload your transactions file to begin.")
    st.stop()

# -------------------------
# Process Data
# -------------------------
df = pd.read_csv(uploaded)
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

df_scored = df.copy()
df_scored["risk_score"] = df_scored.apply(score_transaction, axis=1)
df_scored["risk_category"] = df_scored["risk_score"].apply(categorize)

# -------------------------
# KPIs
# -------------------------
high = int((df_scored["risk_category"] == "High").sum())
med = int((df_scored["risk_category"] == "Medium").sum())
low = int((df_scored["risk_category"] == "Low").sum())
total = len(df_scored)
pct_high = round(100 * high / total, 1)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Transactions", total)
col2.metric("High Risk", high, f"{pct_high}%", delta_color="inverse")
col3.metric("Medium Risk", med)
col4.metric("Average Score", round(float(df_scored["risk_score"].mean()), 1))

st.divider()

# -------------------------
# Top High-Risk Transactions
# -------------------------
st.subheader("🚨 Top 20 High-Risk Transactions")
top_high = df_scored[df_scored["risk_category"]=="High"].nlargest(20, "risk_score")
st.dataframe(top_high, use_container_width=True, hide_index=True)

# -------------------------
# Charts
# -------------------------
left, right = st.columns(2)

with left:
    st.subheader("📊 Risk Category Distribution")
    # --- Risk distribution counts ---
    counts = df["risk_category"].value_counts().reset_index()
    counts.columns = ["risk_category", "count"]

    # --- Pie chart ---
    fig = px.pie(
        counts,
        names="risk_category",
        values="count",
        hole=0.3,
        color_discrete_sequence=["#2a9d8f", "#f4a261", "#e63946"]
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("🌍 Top Risky Corridors")
    df_scored["corridor"] = df_scored["sender_country"].str.upper() + ">" + df_scored["receiver_country"].str.upper()
    corr = df_scored.groupby("corridor").size().reset_index(name="count").sort_values("count", ascending=False).head(10)
    fig2 = px.bar(corr, x="corridor", y="count", text="count", color="count",
                  color_continuous_scale="Reds")
    st.plotly_chart(fig2, use_container_width=True)

# -------------------------
# Download Button
# -------------------------
st.subheader("⬇️ Export Results")
st.markdown(make_download_link(df_scored, "transactions_scored.csv"), unsafe_allow_html=True)

# -------------------------
# Narrative Summary
# -------------------------
st.subheader("📜 Portfolio Risk Narrative")
heuristics_text = f"Out of {total} transactions, {high} are High risk ({pct_high}%), {med} Medium, and {low} Low risk. The average score is {round(float(df_scored['risk_score'].mean()),1)}."
st.success(heuristics_text)

st.caption("NIUM © 2025")

