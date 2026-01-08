import json
from datetime import date, datetime

import streamlit as st
import pandas as pd
import altair as alt
from dateutil.relativedelta import relativedelta

import gspread
from google.oauth2.service_account import Credentials


# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="Production P&L", page_icon="📊", layout="wide")


# =========================
# Theme Toggle (Dark / Light)
# =========================
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

with st.sidebar:
    is_dark = st.toggle("🌙 Dark mode", value=(st.session_state.theme == "dark"))
    st.session_state.theme = "dark" if is_dark else "light"

DARK_CSS = """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 2.2rem; max-width: 1200px; }
.stApp { background-color:#0F172A; color:#E5E7EB; }
[data-testid="stSidebar"] { background:#0B1220; }
[data-testid="stSidebar"] * { color:#E5E7EB !important; }

.card{
  background:#111827;
  border:1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 10px 22px rgba(0,0,0,0.35);
}
.card-title{ font-size: 12px; letter-spacing:.06em; color: rgba(229,231,235,.70); font-weight: 800; text-transform: uppercase;}
.card-value{ font-size: 26px; font-weight: 900; margin-top: 4px; color:#E5E7EB; }
.card-sub{ font-size: 12px; color: rgba(229,231,235,.60); margin-top: 2px; }

.small-muted{ color: rgba(229,231,235,.65); font-size: 12px; }
hr.soft{ border:none; height:1px; background: rgba(255,255,255,0.10); margin:14px 0; }

div[data-testid="stDataFrame"]{
  background:#0B1220;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
}

/* Progress */
.pb-wrap{ margin-top: 10px; }
.pb-track{
  width:100%;
  height: 12px;
  background: rgba(255,255,255,0.10);
  border-radius: 999px;
  overflow: hidden;
}
.pb-fill{
  height: 12px;
  width: var(--w);
  background: linear-gradient(90deg, rgba(37,99,235,1), rgba(59,130,246,1));
  border-radius: 999px;
  box-shadow: 0 0 16px rgba(59,130,246,0.25);
}
.pb-meta{ display:flex; justify-content: space-between; margin-top:6px; }
.pb-meta span{ font-size: 12px; color: rgba(229,231,235,.70); }

.stButton > button{ background:#2563EB; color:white; border-radius:10px; border:0; }
</style>
"""

LIGHT_CSS = """
<style>
.block-container { padding-top: 1.0rem; padding-bottom: 2.2rem; max-width: 1200px; }
.stApp { background-color:#F8FAFC; color:#0F172A; }
[data-testid="stSidebar"] { background:#FFFFFF; }

.card{
  background:#FFFFFF;
  border:1px solid rgba(15,23,42,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 6px 18px rgba(15,23,42,0.06);
}
.card-title{ font-size: 12px; letter-spacing:.06em; color: rgba(15,23,42,.60); font-weight: 800; text-transform: uppercase;}
.card-value{ font-size: 26px; font-weight: 900; margin-top: 4px; }
.card-sub{ font-size: 12px; color: rgba(15,23,42,.55); margin-top: 2px; }

.small-muted{ color: rgba(15,23,42,.55); font-size: 12px; }
hr.soft{ border:none; height:1px; background: rgba(15,23,42,0.08); margin:14px 0; }

div[data-testid="stDataFrame"]{
  background:#FFFFFF;
  border-radius: 12px;
  border: 1px solid rgba(15,23,42,0.08);
}

/* Progress */
.pb-wrap{ margin-top: 10px; }
.pb-track{
  width:100%;
  height: 12px;
  background: rgba(15,23,42,0.08);
  border-radius: 999px;
  overflow: hidden;
}
.pb-fill{
  height: 12px;
  width: var(--w);
  background: linear-gradient(90deg, rgba(37,99,235,1), rgba(59,130,246,1));
  border-radius: 999px;
  box-shadow: 0 0 16px rgba(59,130,246,0.18);
}
.pb-meta{ display:flex; justify-content: space-between; margin-top:6px; }
.pb-meta span{ font-size: 12px; color: rgba(15,23,42,.60); }

.stButton > button{ background:#2563EB; color:white; border-radius:10px; border:0; }
</style>
"""

st.markdown(DARK_CSS if st.session_state.theme == "dark" else LIGHT_CSS, unsafe_allow_html=True)


# -----------------------------
# Helpers
# -----------------------------
def money(x: float) -> str:
    try:
        return f"฿{x:,.0f}"
    except Exception:
        return "฿0"


def calc_amount(qty, unit_price, vat_percent):
    qty = float(qty or 0)
    unit_price = float(unit_price or 0)
    vat_percent = float(vat_percent or 0)
    base = qty * unit_price
    vat = base * (vat_percent / 100.0)
    net = base + vat
    return base, vat, net


def month_range(d: date):
    start = d.replace(day=1)
    end = (start + relativedelta(months=1)) - relativedelta(days=1)
    return start, end


def year_range(y: int):
    return date(y, 1, 1), date(y, 12, 31)


def progress_block(title: str, current: float, target: float, gap_label: str):
    if target <= 0:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">{title}</div>
          <div class="card-value">{money(current)} / -</div>
          <div class="card-sub">ตั้งเป้าหมายที่เมนู Achievement</div>
        </div>
        """, unsafe_allow_html=True)
        return

    pct = (current / target) * 100.0
    pct_clamped = max(0.0, min(pct, 100.0))
    gap = max(target - current, 0.0)

    st.markdown(f"""
    <div class="card">
      <div class="card-title">{title}</div>
      <div class="card-value">{money(current)} / {money(target)}</div>
      <div class="card-sub">{gap_label} {money(gap)} • ทำได้ {pct:.1f}%</div>

      <div class="pb-wrap">
        <div class="pb-track">
          <div class="pb-fill" style="--w:{pct_clamped:.2f}%;"></div>
        </div>
        <div class="pb-meta">
          <span>0%</span>
          <span>{pct_clamped:.1f}%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    raw = st.secrets.get("GCP_SERVICE_ACCOUNT", "")
    if not raw:
        st.error("Missing GCP_SERVICE_ACCOUNT in Secrets")
        st.stop()

    info = json.loads(raw.strip())
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def get_worksheets():
    sheet_id = st.secrets.get("GSHEET_ID", "")
    if not sheet_id:
        st.error("Missing GSHEET_ID in Secrets")
        st.stop()

    gc = get_gspread_client()
    sh = gc.open_by_key(sheet_id)

    tx_ws = sh.worksheet("transactions")
    try:
        ach_ws = sh.worksheet("achievement")
    except Exception:
        ach_ws = None

    return sh, tx_ws, ach_ws


TX_HEADERS = [
    "id","tx_date","project","tx_type","category","vendor","description",
    "qty","unit_price","vat_percent","payment","status","ref","created_at"
]
ACH_HEADERS = ["year","month","target"]


def ensure_headers(ws, headers):
    existing = ws.row_values(1)
    if existing == headers:
        return
    if len(existing) == 0:
        ws.append_row(headers)
        return
    st.error("Header row ในชีทไม่ตรงตามที่ต้องการ กรุณาตั้งหัวคอลัมน์ให้ตรงนี้")
    st.code(",".join(headers))
    st.stop()


def read_transactions(ws) -> pd.DataFrame:
    ensure_headers(ws, TX_HEADERS)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["tx_date"] = pd.to_datetime(df["tx_date"], errors="coerce")
    for col in ["qty","unit_price","vat_percent"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
    return df


def next_id(df: pd.DataFrame) -> int:
    return 1 if df.empty else int(df["id"].max()) + 1


def append_transaction(ws, row: dict):
    values = [
        row["id"], row["tx_date"], row.get("project",""), row["tx_type"], row.get("category",""),
        row.get("vendor",""), row.get("description",""), row.get("qty", 1), row.get("unit_price", 0),
        row.get("vat_percent", 0), row.get("payment",""), row.get("status",""), row.get("ref",""),
        row.get("created_at",""),
    ]
    ws.append_row(values, value_input_option="USER_ENTERED")


def find_row_by_id(ws, target_id: int):
    values = ws.get_all_values()
    if len(values) <= 1:
        return None
    for i in range(1, len(values)):
        row = values[i]
        if not row:
            continue
        try:
            rid = int(str(row[0]).strip())
        except Exception:
            continue
        if rid == int(target_id):
            return i + 1
    return None


def delete_transaction_by_id(ws, target_id: int) -> bool:
    rownum = find_row_by_id(ws, target_id)
    if rownum is None:
        return False
    ws.delete_rows(rownum)
    return True


def read_achievement(ws) -> pd.DataFrame:
    ensure_headers(ws, ACH_HEADERS)
    rec = ws.get_all_records()
    df = pd.DataFrame(rec)
    if df.empty:
        return df
    df["year"] = pd.to_numeric(df["year"], errors="coerce").fillna(0).astype(int)
    df["month"] = pd.to_numeric(df["month"], errors="coerce").fillna(0).astype(int)
    df["target"] = pd.to_numeric(df["target"], errors="coerce").fillna(0.0)
    return df


def upsert_target(ws, year: int, month: int, target: float):
    year, month, target = int(year), int(month), float(target)

    values = ws.get_all_values()
    if len(values) == 0:
        ws.append_row(ACH_HEADERS)
        values = ws.get_all_values()

    for i in range(1, len(values)):
        row = values[i]
        if len(row) < 3:
            continue
        try:
            y = int(str(row[0]).strip())
            m = int(str(row[1]).strip())
        except Exception:
            continue
        if y == year and m == month:
            ws.update_cell(i + 1, 3, target)
            return
    ws.append_row([year, month, target], value_input_option="USER_ENTERED")


def get_targets_for_year(ach_df: pd.DataFrame, year: int):
    if ach_df.empty:
        return 0.0, {m: 0.0 for m in range(1, 13)}

    ydf = ach_df[ach_df["year"] == int(year)]
    yearly = float(ydf[ydf["month"] == 0]["target"].max()) if not ydf[ydf["month"] == 0].empty else 0.0

    monthly = {m: 0.0 for m in range(1, 13)}
    mdf = ydf[(ydf["month"] >= 1) & (ydf["month"] <= 12)]
    for _, r in mdf.iterrows():
        monthly[int(r["month"])] = float(r["target"])
    return yearly, monthly


# -----------------------------
# Sidebar nav
# -----------------------------
with st.sidebar:
    st.markdown("**Production P&L**")
    st.caption("Google Sheets • No Login")
    st.markdown('<hr class="soft">', unsafe_allow_html=True)
    nav = st.radio("", ["Dashboard", "Transactions", "Export", "Achievement"], index=0, label_visibility="collapsed")
    st.markdown('<hr class="soft">', unsafe_allow_html=True)
    st.caption("ต้องมีแท็บ: transactions, achievement")


# -----------------------------
# Filter bar
# -----------------------------
c1, c2, c3 = st.columns([1.1, 1.6, 1.0], vertical_alignment="center")
with c1:
    month_pick = st.date_input("เดือน", value=date.today().replace(day=1))
with c2:
    search = st.text_input("ค้นหา", value="", placeholder="โปรเจกต์/หมวด/คำอธิบาย/Ref…")
with c3:
    add_sample = st.button("ใส่ข้อมูลตัวอย่าง", use_container_width=True)

start_m, end_m = month_range(month_pick)
year_selected = month_pick.year
start_y, end_y = year_range(year_selected)
month_idx = month_pick.month


# -----------------------------
# Load Sheets
# -----------------------------
sh, tx_ws, ach_ws = get_worksheets()
df_all = read_transactions(tx_ws)

if add_sample:
    nid = next_id(df_all)
    demo = [
        dict(id=nid, tx_date=start_m.isoformat(), project="Client A - TVC", tx_type="Income",
             category="Production Fee", vendor="Client A", description="Milestone payment",
             qty=1, unit_price=50000, vat_percent=0, payment="Bank Transfer", status="Received",
             ref="INV-001", created_at=datetime.now().isoformat()),
        dict(id=nid+1, tx_date=start_m.isoformat(), project="Client A - TVC", tx_type="Expense",
             category="Studio", vendor="Studio X", description="Studio rental",
             qty=1, unit_price=3500, vat_percent=7, payment="Bank Transfer", status="Paid",
             ref="RC-001", created_at=datetime.now().isoformat()),
    ]
    for r in demo:
        append_transaction(tx_ws, r)
    st.success("ใส่ข้อมูลตัวอย่างแล้ว ✅")
    st.rerun()


def add_net_cols(dfin: pd.DataFrame) -> pd.DataFrame:
    if dfin.empty:
        return dfin
    d = dfin.copy()
    d["base"], d["vat"], d["net"] = zip(*d.apply(lambda r: calc_amount(r["qty"], r["unit_price"], r["vat_percent"]), axis=1))
    return d


# Month view
if df_all.empty:
    df = df_all
else:
    df = df_all.copy()
    df = df[(df["tx_date"].dt.date >= start_m) & (df["tx_date"].dt.date <= end_m)]
    if search.strip():
        s = search.strip().lower()
        def match_row(r):
            blob = " ".join([
                str(r.get("project","")),
                str(r.get("category","")),
                str(r.get("vendor","")),
                str(r.get("description","")),
                str(r.get("ref","")),
            ]).lower()
            return s in blob
        df = df[df.apply(match_row, axis=1)]

df = add_net_cols(df)

# Year view
if df_all.empty:
    df_year = df_all
else:
    df_year = df_all.copy()
    df_year = df_year[(df_year["tx_date"].dt.date >= start_y) & (df_year["tx_date"].dt.date <= end_y)]

df_year = add_net_cols(df_year)

# Sales
sales_month = float(df[df["tx_type"] == "Income"]["net"].sum()) if not df.empty else 0.0
sales_ytd = float(df_year[df_year["tx_type"] == "Income"]["net"].sum()) if not df_year.empty else 0.0

# P&L (month)
total_income = sales_month
total_expense = float(df[df["tx_type"] == "Expense"]["net"].sum()) if not df.empty else 0.0
profit = total_income - total_expense
margin = (profit / total_income * 100.0) if total_income > 0 else 0.0

# Targets
annual_target = 0.0
monthly_targets = {m: 0.0 for m in range(1, 13)}
if ach_ws is not None:
    ach_df = read_achievement(ach_ws)
    annual_target, monthly_targets = get_targets_for_year(ach_df, year_selected)

default_monthly_target = (annual_target / 12.0) if annual_target > 0 else 0.0
monthly_target = monthly_targets.get(month_idx, 0.0) or default_monthly_target


# -----------------------------
# Pages
# -----------------------------
if nav == "Dashboard":
    st.markdown("### Dashboard")
    st.caption("ภาพรวมรายเดือน + กราฟรายเดือนทั้งปี + Achievement")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">TOTAL INCOME (SALES)</div>
          <div class="card-value">{money(total_income)}</div>
          <div class="card-sub">ยอดขายเดือนนี้</div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">TOTAL EXPENSE</div>
          <div class="card
