# app.py
# Streamlit Transaction Risk Scoring App
# -------------------------------------
# Features
# 1) Upload CSV of transactions
# 2) Compute risk score (0-100) using business rules
# 3) Categorize into Low / Medium / High
# 4) Show table of top 20 high-risk transactions
# 5) Show distribution chart
# 6) (Optional) AI narrative summary if OPENAI_API_KEY is set

import io
import os
import base64
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

# -------------------------
# UI CONFIG
# -------------------------
st.set_page_config(
    page_title="Transaction Risk Scoring",
    page_icon="🕵️",
    layout="wide",
)

st.title("🕵️ Transaction Risk Scoring App")
st.caption("Upload a CSV → score risk → see top risks & distribution. Optional AI summary at the end.")

# -------------------------
# Helper: Download link for DataFrame
# -------------------------
def make_download_link(df: pd.DataFrame, filename: str) -> str:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    b64 = base64.b64encode(csv_bytes).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV</a>'

# -------------------------
# Business Rules Configuration (edit as needed)
# -------------------------
HIGH_RISK_COUNTRIES = {
    # Example list; adjust for your org
    "IR", "KP", "SY", "CU", "RU", "UA", "AF", "IQ", "YE", "SO", "SD", "CD"
}

RISKY_MERCHANT_CATS = {
    # Strings should match values in `merchant_category`
    "gambling", "crypto", "virtual_goods", "adult", "gift_cards"
}

KYC_TIER_SCORES = {
    # Map your dataset's kyc_tier values here (case-insensitive)
    # Unknown tiers will default to 5
    "tier_1": 10,
    "basic": 10,
    "lite": 10,
    "tier_2": 5,
    "standard": 5,
    "tier_3": 0,
    "enhanced": 0,
    "full": 0,
}

CATEGORY_RULES = {
    "Low": (0, 39),
    "Medium": (40, 69),
    "High": (70, 100),
}

# -------------------------
# Core Risk Scoring Function
# -------------------------

def score_transaction(row: pd.Series) -> int:
    # Start score at 10
    score = 10

    # 0) Sanctions hard stop
    sanctioned = str(row.get("sanctioned_party_flag", 0)).strip()
    if sanctioned in {"1", "true", "True", "TRUE"} or sanctioned == 1:
        return 100

    # 1) Amount (USD)
    amt = to_float(row.get("amount_usd"))
    if amt is not None:
        if amt > 10000:
            score += 20
        elif amt > 5000:
            score += 15
        elif amt > 1000:
            score += 10
        else:
            score += 0

    # 2) Country corridor risk
    sc = str(row.get("sender_country", "")).upper()
    rc = str(row.get("receiver_country", "")).upper()
    if sc and rc and sc != rc:
        score += 5  # cross-border bump
    if sc in HIGH_RISK_COUNTRIES or rc in HIGH_RISK_COUNTRIES:
        score += 15

    # 3) KYC Tier
    tier_raw = str(row.get("kyc_tier", "")).lower().strip()
    score += KYC_TIER_SCORES.get(tier_raw, 5)

    # 4) Velocity
    v1h = to_float(row.get("velocity_1h"))
    v24h = to_float(row.get("velocity_24h"))
    if v1h is not None:
        if v1h > 5:
            score += 15
        elif v1h > 2:
            score += 8
    if v24h is not None:
        if v24h > 20:
            score += 10
        elif v24h > 10:
            score += 5

    # 5) Merchant category
    mcc = str(row.get("merchant_category", "")).lower().strip()
    if mcc in RISKY_MERCHANT_CATS:
        score += 10

    # 6) Device change
    dchg = str(row.get("device_change_flag", 0)).strip()
    if dchg in {"1", "true", "True", "TRUE"} or dchg == 1:
        score += 10

    # 7) Account age (days)
    age = to_float(row.get("customer_age_days"))
    if age is not None:
        if age < 30:
            score += 15
        elif age < 90:
            score += 10
        elif age < 365:
            score += 5

    # 8) Prior txn in 24h (bursting)
    prior_24h = to_float(row.get("prior_txn_24h"))
    if prior_24h is not None:
        if prior_24h > 10:
            score += 10
        elif prior_24h > 3:
            score += 5

    # Cap at [0, 100]
    score = max(0, min(100, int(round(score))))
    return score


def to_float(x):
    try:
        if x is None or (isinstance(x, str) and x.strip() == ""):
            return None
        return float(x)
    except Exception:
        return None


def categorize(score: int) -> str:
    for name, (lo, hi) in CATEGORY_RULES.items():
        if lo <= score <= hi:
            return name
    return "Low"

# -------------------------
# Sidebar Controls
# -------------------------
with st.sidebar:
    st.header("Settings")
    st.write("Tune business rules in the code (top of file) if needed.")
    st.markdown("**Risk Category Thresholds**")
    st.json(CATEGORY_RULES)

    st.markdown("**High-Risk Countries**")
    st.code(", ".join(sorted(HIGH_RISK_COUNTRIES)))

    st.markdown("**Risky Merchant Categories**")
    st.code(", ".join(sorted(RISKY_MERCHANT_CATS)))

# -------------------------
# File Upload
# -------------------------
required_cols = [
    "txn_id", "timestamp", "sender_country", "receiver_country", "amount_usd",
    "channel", "customer_age_days", "prior_txn_24h", "sanctioned_party_flag",
    "kyc_tier", "merchant_category", "velocity_1h", "velocity_24h", "device_change_flag"
]

uploaded = st.file_uploader("Upload sample_transactions.csv", type=["csv"])

if uploaded is None:
    st.info(
        "⬆️ Upload your CSV to begin. Expected columns: "
        + ", ".join(required_cols)
    )
    st.stop()

# -------------------------
# Load & Validate
# -------------------------
df = pd.read_csv(uploaded)
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

# -------------------------
# Compute Risk
# -------------------------
df_scored = df.copy()
df_scored["risk_score"] = df_scored.apply(score_transaction, axis=1)
df_scored["risk_category"] = df_scored["risk_score"].apply(categorize)

# -------------------------
# KPIs
# -------------------------
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Transactions", len(df_scored))
with col2:
    st.metric("High Risk", int((df_scored["risk_category"] == "High").sum()))
with col3:
    st.metric("Medium Risk", int((df_scored["risk_category"] == "Medium").sum()))
with col4:
    st.metric("Avg Risk Score", round(float(df_scored["risk_score"].mean()), 1))

st.divider()

# -------------------------
# Top 20 High-Risk Table
# -------------------------
st.subheader("Top 20 High-Risk Transactions")
cols_show = [
    "txn_id", "timestamp", "sender_country", "receiver_country", "amount_usd",
    "channel", "merchant_category", "kyc_tier", "velocity_1h", "velocity_24h",
    "prior_txn_24h", "device_change_flag", "sanctioned_party_flag", "risk_score", "risk_category"
]

top_high = (
    df_scored.sort_values(["risk_category", "risk_score"], ascending=[True, False])
    .query('risk_category == "High"')
    .head(20)
)

st.dataframe(top_high[cols_show], use_container_width=True, hide_index=True)

# -------------------------
# Distribution Chart
# -------------------------
st.subheader("Risk Category Distribution")
counts = df_scored["risk_category"].value_counts().rename_axis("risk_category").reset_index(name="count")
fig = px.pie(counts, names="risk_category", values="count", hole=0.3)
st.plotly_chart(fig, use_container_width=True)

# -------------------------
# Download Scored CSV
# -------------------------
st.subheader("Download Results")
st.markdown(make_download_link(df_scored, "transactions_scored.csv"), unsafe_allow_html=True)

# -------------------------
# Optional: AI Narrative Summary (local heuristic or OpenAI if key provided)
# -------------------------
with st.expander("📜 Risk Posture Narrative (Optional)"):
    use_openai = st.toggle("Use OpenAI (requires OPENAI_API_KEY env var)", value=False)

    # Build a structured summary first
    total = len(df_scored)
    high = int((df_scored["risk_category"] == "High").sum())
    med = int((df_scored["risk_category"] == "Medium").sum())
    low = int((df_scored["risk_category"] == "Low").sum())
    pct_high = round(100 * high / total, 1) if total else 0.0

    top_corridors = (
        df_scored.assign(corridor=lambda x: x["sender_country"].astype(str).str.upper() + ">" + x["receiver_country"].astype(str).str.upper())
        .groupby("corridor").size().sort_values(ascending=False).head(3)
    )

    risky_mcc_breakdown = (
        df_scored[df_scored["merchant_category"].str.lower().isin(RISKY_MERCHANT_CATS)]
        ["merchant_category"].str.lower().value_counts().head(5)
    )

    heuristics_text = (
        f"Out of {total} transactions, {high} ({pct_high}%) are High risk, {med} are Medium, and {low} are Low. "
        f"Top corridors by volume: {', '.join([f'{k} ({v})' for k, v in top_corridors.items()]) or 'n/a'}. "
        f"Risky merchant categories observed: {', '.join([f'{k} ({v})' for k, v in risky_mcc_breakdown.items()]) or 'none'}."
    )

    if use_openai and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI()
            prompt = (
                "You are a fraud risk analyst. Write a crisp 4-6 sentence summary of the portfolio risk based on these facts.\n" 
                + heuristics_text
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            ai_text = resp.choices[0].message.content
            st.write(ai_text)
        except Exception as e:
            st.warning(f"OpenAI generation failed; falling back to heuristic summary. Error: {e}")
            st.write(heuristics_text)
    else:
        st.write(heuristics_text)

st.divider()

st.caption("Built with Streamlit • Edit rules at the top to fit your policy. © 2025")
