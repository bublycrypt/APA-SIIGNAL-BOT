import streamlit as st
import pandas as pd
import os
from io import StringIO
import plotly.express as px

st.set_page_config(page_title="APA Signal Dashboard", layout="wide")

st.title("APA Signal Bot — Dashboard")

# Upload or load backtest_trades.csv
st.sidebar.header("Data source")
upload = st.sidebar.file_uploader("Upload backtest_trades.csv", type=["csv"]) 
use_sample = st.sidebar.checkbox("Use sample full_trade_list.csv", value=False)

if upload is not None:
    df = pd.read_csv(upload, parse_dates=["entry_time","exit_time"], infer_datetime_format=True)
elif use_sample and os.path.exists("full_trade_list (1).csv"):
    df = pd.read_csv("full_trade_list (1).csv", parse_dates=["entry_time","exit_time"], infer_datetime_format=True)
elif os.path.exists("backtest_trades.csv"):
    df = pd.read_csv("backtest_trades.csv", parse_dates=["entry_time","exit_time"], infer_datetime_format=True)
else:
    st.info("No trades file found. Run a backtest and export trades, or upload a CSV.")
    st.stop()

st.subheader("Trades overview")
st.write(f"Total trades: {len(df)}")
wins = df[df['outcome']=='win'] if 'outcome' in df.columns else df[df['pnl_r']>0]
losses = df[df['outcome']=='loss'] if 'outcome' in df.columns else df[df['pnl_r']<=0]
st.write(f"Wins: {len(wins)} | Losses: {len(losses)}")

# Show table
st.dataframe(df.tail(200))

# Simple metrics
if 'pnl_r' in df.columns:
    total_r = df['pnl_r'].sum()
    st.metric("Total R", f"{total_r:.2f}R")

# Equity curve
if 'pnl_r' in df.columns:
    equity = df['pnl_r'].cumsum()
    eq_df = pd.DataFrame({"equity": equity, "idx": range(len(equity))})
    fig = px.line(eq_df, x='idx', y='equity', title='Equity Curve (R)')
    st.plotly_chart(fig, use_container_width=True)

# Download cleaned file
st.sidebar.markdown("---")
if st.sidebar.button("Save cleaned trades to backtest_trades.csv"):
    df.to_csv("backtest_trades.csv", index=False)
    st.sidebar.success("Saved as backtest_trades.csv")
