import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Transaction Risk Scoring", layout="wide")

st.title("💳 Transaction Risk Scoring App")

# --- Upload CSV ---
uploaded_file = st.file_uploader("Upload a CSV file of transactions", type=["csv"])

# --- Risk scoring function ---
def calculate_risk_score(row):
    score = 10

    # Amount-based scoring
    if row["amount_usd"] > 10000:
        score += 30
    elif row["amount_usd"] > 5000:
        score += 20
    elif row["amount_usd"] > 1000:
        score += 10

    # Country corridor risk (example: sender != receiver)
    if row["sender_country"] != row["receiver_country"]:
        score += 10

    # KYC tier
    if row["kyc_tier"] == "low":
        score += 20
    elif row["kyc_tier"] == "medium":
        score += 10

    # Velocity
    if row["velocity_1h"] > 5:
        score += 20
    if row["velocity_24h"] > 20:
        score += 20

    # Merchant category
    if row["merchant_category"] in ["gambling", "crypto", "luxury_goods"]:
        score += 15

    # Device change
    if row["device_change_flag"] == 1:
        score += 15

    # Account age
    if row["customer_age_days"] < 30:
        score += 15
    elif row["customer_age_days"] < 90:
        score += 10

    # Sanctioned party
    if row["sanctioned_party_flag"] == 1:
        return 100

    return min(score, 100)

# --- Risk category function ---
def categorize_risk(score):
    if score >= 70:
        return "High"
    elif score >= 40:
        return "Medium"
    else:
        return "Low"

# --- Process uploaded file ---
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Compute risk score & category
    df["risk_score"] = df.apply(calculate_risk_score, axis=1)
    df["risk_category"] = df["risk_score"].apply(categorize_risk)

    st.subheader("📊 Risk Analysis Dashboard")

    # --- Metrics ---
    total_txns = len(df)
    high_risk = len(df[df["risk_category"] == "High"])
    medium_risk = len(df[df["risk_category"] == "Medium"])
    low_risk = len(df[df["risk_category"] == "Low"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Transactions", total_txns)
    col2.metric("High Risk", high_risk)
    col3.metric("Medium Risk", medium_risk)
    col4.metric("Low Risk", low_risk)

    # --- Top 20 High Risk ---
    st.subheader("🚨 Top 20 High-Risk Transactions")
    top20 = df.sort_values("risk_score", ascending=False).head(20)
    st.dataframe(top20)

    # --- Distribution charts ---
    st.subheader("📈 Risk Category Distribution")

    counts = df["risk_category"].value_counts().reset_index()
    counts.columns = ["risk_category", "count"]

    # Pie chart
    fig1 = px.pie(
        counts,
        names="risk_category",
        values="count",
        hole=0.3,
        color_discrete_sequence=["#2a9d8f", "#f4a261", "#e63946"]
    )

    # Bar chart
    fig2 = px.bar(
        counts,
        x="risk_category",
        y="count",
        color="risk_category",
        color_discrete_sequence=["#2a9d8f", "#f4a261", "#e63946"],
        text="count"
    )

    colA, colB = st.columns(2)
    colA.plotly_chart(fig1, use_container_width=True)
    colB.plotly_chart(fig2, use_container_width=True)

    # --- Optional Narrative ---
    st.subheader("📝 Narrative Summary")
    summary = f"""
    Out of {total_txns} transactions:
    - {high_risk} are **High Risk**  
    - {medium_risk} are **Medium Risk**  
    - {low_risk} are **Low Risk**

    The system flagged {high_risk} transactions as potentially risky, requiring further investigation.
    """
    st.info(summary)

else:
    st.warning("Please upload a CSV file to proceed.")
