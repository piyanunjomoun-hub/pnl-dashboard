import streamlit as st
import sqlite3
import pandas as pd
import altair as alt
from datetime import date

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(
    page_title="Production P&L Dashboard",
    page_icon="📊",
    layout="wide"
)

import os
os.makedirs("data", exist_ok=True)
DB_PATH = "data/pnl.sqlite3"

# -------------------------
# DATABASE
# -------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_date TEXT,
            tx_type TEXT,
            category TEXT,
            amount REAL,
            note TEXT
        )
    """)
    conn.commit()
    conn.close()

def insert_tx(tx_date, tx_type, category, amount, note):
    conn = get_conn()
    conn.execute(
        "INSERT INTO transactions (tx_date, tx_type, category, amount, note) VALUES (?, ?, ?, ?, ?)",
        (tx_date, tx_type, category, amount, note)
    )
    conn.commit()
    conn.close()

def load_data():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM transactions", conn)
    conn.close()
    if not df.empty:
        df["tx_date"] = pd.to_datetime(df["tx_date"])
    return df

init_db()

# -------------------------
# HEADER
# -------------------------
st.title("📊 Production P&L Dashboard")
st.caption("ระบบบันทึกรายรับ–รายจ่าย และคำนวณกำไร/ขาดทุน")

# -------------------------
# ADD TRANSACTION
# -------------------------
st.subheader("➕ เพิ่มรายการ")

with st.form("add_form", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        tx_date = st.date_input("วันที่", value=date.today())
    with c2:
        tx_type = st.selectbox("ประเภท", ["REVENUE", "EXPENSE"])
    with c3:
        category = st.text_input("หมวดหมู่ (เช่น ค่าถ่ายทำ / รายได้งานลูกค้า)")
    with c4:
        amount = st.number_input("จำนวนเงิน", min_value=0.0, step=100.0)

    note = st.text_area("หมายเหตุ", height=60)

    submitted = st.form_submit_button("บันทึก")
    if submitted:
        if category.strip() == "" or amount <= 0:
            st.error("กรุณากรอกหมวดหมู่และจำนวนเงินให้ถูกต้อง")
        else:
            insert_tx(tx_date.isoformat(), tx_type, category, amount, note)
            st.success("บันทึกรายการเรียบร้อย ✅")
            st.rerun()

# -------------------------
# LOAD DATA
# -------------------------
df = load_data()

st.divider()

# -------------------------
# SUMMARY
# -------------------------
st.subheader("📈 สรุปภาพรวม")

if df.empty:
    st.info("ยังไม่มีข้อมูล กรุณาเพิ่มรายการด้านบน")
else:
    revenue = df[df["tx_type"] == "REVENUE"]["amount"].sum()
    expense = df[df["tx_type"] == "EXPENSE"]["amount"].sum()
    profit = revenue - expense

    k1, k2, k3 = st.columns(3)
    k1.metric("Revenue", f"{revenue:,.2f}")
    k2.metric("Expense", f"{expense:,.2f}")
    k3.metric("Profit / Loss", f"{profit:,.2f}")

# -------------------------
# TABLE
# -------------------------
st.subheader("📋 รายการทั้งหมด")

if not df.empty:
    st.dataframe(
        df.sort_values("tx_date", ascending=False),
        use_container_width=True,
        hide_index=True
    )

# -------------------------
# MONTHLY CHART
# -------------------------
st.subheader("📊 กราฟรายเดือน")

if not df.empty:
    df["month"] = df["tx_date"].dt.to_period("M").astype(str)

    monthly = (
        df.pivot_table(
            index="month",
            columns="tx_type",
            values="amount",
            aggfunc="sum",
            fill_value=0
        )
        .reset_index()
    )

    if "REVENUE" not in monthly:
        monthly["REVENUE"] = 0
    if "EXPENSE" not in monthly:
        monthly["EXPENSE"] = 0

    monthly["PROFIT"] = monthly["REVENUE"] - monthly["EXPENSE"]

    chart_data = monthly.melt(
        "month",
        value_vars=["REVENUE", "EXPENSE", "PROFIT"],
        var_name="type",
        value_name="amount"
    )

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True)
        .encode(
            x=alt.X("month:N", title="เดือน"),
            y=alt.Y("amount:Q", title="จำนวนเงิน"),
            color="type:N",
            tooltip=["month", "type", alt.Tooltip("amount:Q", format=",.2f")]
        )
        .properties(height=350)
    )

    st.altair_chart(chart, use_container_width=True)

# -------------------------
# EXPORT
# -------------------------
st.subheader("⬇️ Export ข้อมูล")

if not df.empty:
    csv = df.copy()
    csv["tx_date"] = csv["tx_date"].dt.date.astype(str)
    csv_bytes = csv.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name="pnl_export.csv",
        mime="text/csv"
    )
