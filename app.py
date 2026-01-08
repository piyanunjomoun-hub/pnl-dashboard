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
st.set_page_config(page_title="Production P&L", page_icon="📊", remember=False, layout="wide")


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
    """
    Render pretty progress bar with text.
    """
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


# -----------------------------
# Google Sheets connection
# -----------------------------
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

    raw = raw.strip()
    info = json.loads(raw)
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
ACH_HEADERS = ["year","month","target"]  # month 0 = yearly target row


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


# -----------------------------
# Achievement
# -----------------------------
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
    year = int(year)
    month = int(month)
    target = float(target)

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
# Load from Google Sheets
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

# Year view (Jan-Dec)
if df_all.empty:
    df_year = df_all
else:
    df_year = df_all.copy()
    df_year = df_year[(df_year["tx_date"].dt.date >= start_y) & (df_year["tx_date"].dt.date <= end_y)]

df_year = add_net_cols(df_year)

# Sales (Income only)
sales_month = float(df[df["tx_type"] == "Income"]["net"].sum()) if not df.empty else 0.0
sales_ytd = float(df_year[df_year["tx_type"] == "Income"]["net"].sum()) if not df_year.empty else 0.0

# P&L month
total_income = sales_month
total_expense = float(df[df["tx_type"] == "Expense"]["net"].sum()) if not df.empty else 0.0
profit = total_income - total_expense
margin = (profit / total_income * 100.0) if total_income > 0 else 0.0


# -----------------------------
# Targets
# -----------------------------
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

    # KPI cards
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
          <div class="card-value">{money(total_expense)}</div>
          <div class="card-sub">รายจ่ายเดือนนี้</div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">PROFIT / LOSS</div>
          <div class="card-value">{money(profit)}</div>
          <div class="card-sub">กำไร/ขาดทุนเดือนนี้</div>
        </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">PROFIT MARGIN</div>
          <div class="card-value">{margin:.0f}%</div>
          <div class="card-sub">Profit / Income</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # Progress blocks (MONTH / YEAR)
    a1, a2 = st.columns(2)
    with a1:
        progress_block(
            title="ACHIEVEMENT (MONTH)",
            current=sales_month,
            target=monthly_target,
            gap_label="ยังขาด"
        )
    with a2:
        progress_block(
            title="ACHIEVEMENT (YEAR)",
            current=sales_ytd,
            target=annual_target,
            gap_label="ยังขาด"
        )

    st.write("")

    # Chart: Jan-Dec (Income & Expense)
    left, right = st.columns([2.1, 1.2])

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Monthly Chart (Jan–Dec)** <span class='small-muted' style='float:right'>Sales vs Expense</span>",
                    unsafe_allow_html=True)

        if df_year.empty:
            st.info("ยังไม่มีข้อมูลในปีนี้")
        else:
            d = df_year.copy()
            d["month"] = d["tx_date"].dt.month
            d = d.groupby(["month","tx_type"], as_index=False)["net"].sum()

            months = pd.DataFrame({"month": list(range(1, 13))})
            inc = d[d["tx_type"] == "Income"][["month","net"]].rename(columns={"net":"Income"})
            exp = d[d["tx_type"] == "Expense"][["month","net"]].rename(columns={"net":"Expense"})
            m = months.merge(inc, on="month", how="left").merge(exp, on="month", how="left").fillna(0.0)

            month_labels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            m["month_name"] = m["month"].apply(lambda x: month_labels[int(x)-1])

            melt = m.melt(id_vars=["month","month_name"], value_vars=["Income","Expense"],
                          var_name="metric", value_name="value")

            chart = (
                alt.Chart(melt)
                .mark_line(point=True)
                .encode(
                    x=alt.X("month_name:N", sort=month_labels, title=""),
                    y=alt.Y("value:Q", title=""),
                    color=alt.Color("metric:N", title=""),
                    tooltip=["month_name","metric", alt.Tooltip("value:Q", format=",.0f")]
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Quick Export** <span class='small-muted' style='float:right'>CSV</span>", unsafe_allow_html=True)
        st.write("ดาวน์โหลดรายการที่กรองด้วย “เดือน + ค้นหา”")
        if df.empty:
            st.button("Download CSV", use_container_width=True, disabled=True)
        else:
            out = df.copy()
            out["tx_date"] = out["tx_date"].dt.date.astype(str)
            csv_bytes = out.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Download CSV", data=csv_bytes, file_name="transactions_export.csv",
                               mime="text/csv", use_container_width=True)
        st.caption("*เหมาะส่งให้บัญชี หรือทำ Pivot ต่อใน Excel")
        st.markdown("</div>", unsafe_allow_html=True)

    st.write("")

    # Add Transaction
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("**Add Transaction**")

    category_presets = ["Production Fee", "Studio", "Crew", "Equipment", "Post-Production", "Travel", "Ads", "Other"]
    payment_presets = ["Bank Transfer", "Cash", "Credit", "Other"]
    status_presets = ["Planned", "Paid", "Invoiced", "Received", "Other"]

    with st.form("add_tx", clear_on_submit=True):
        r1 = st.columns([1.1, 1.6, 1.0, 1.3, 1.3])
        with r1[0]:
            d = st.date_input("วันที่", value=date.today())
        with r1[1]:
            project = st.text_input("Project / Client", value="", placeholder="Client A - TVC")
        with r1[2]:
            tx_type = st.selectbox("ประเภท", ["Income", "Expense"])
        with r1[3]:
            category = st.selectbox("หมวดหมู่", category_presets)
        with r1[4]:
            vendor = st.text_input("Vendor/Payee", value="", placeholder="Studio / Freelance / Supplier")

        r2 = st.columns([2.2, 0.9, 1.1, 1.0, 1.2])
        with r2[0]:
            desc = st.text_input("คำอธิบาย", value="", placeholder="Milestone / Equipment rent / Crew fee")
        with r2[1]:
            qty = st.number_input("Qty", min_value=0.0, value=1.0, step=1.0)
        with r2[2]:
            unit_price = st.number_input("Unit Price", min_value=0.0, value=0.0, step=100.0)
        with r2[3]:
            vat_percent = st.number_input("VAT %", min_value=0.0, max_value=20.0, value=0.0, step=1.0)
        with r2[4]:
            pay = st.selectbox("Payment", payment_presets)

        r3 = st.columns([1.1, 1.4, 1.5, 1.0])
        with r3[0]:
            status = st.selectbox("Status", status_presets)
        with r3[1]:
            ref = st.text_input("Ref No.", value="", placeholder="INV-001 / RC-001")
        with r3[2]:
            base, vat, net = calc_amount(qty, unit_price, vat_percent)
            st.text_input("Net", value=f"{net:,.0f}", disabled=True)
        with r3[3]:
            submitted = st.form_submit_button("เพิ่มรายการ", type="primary", use_container_width=True)

        if submitted:
            nid = next_id(df_all)
            row = dict(
                id=nid,
                tx_date=d.isoformat(),
                project=project.strip(),
                tx_type=tx_type,
                category=category,
                vendor=vendor.strip(),
                description=desc.strip(),
                qty=float(qty),
                unit_price=float(unit_price),
                vat_percent=float(vat_percent),
                payment=pay,
                status=status,
                ref=ref.strip(),
                created_at=datetime.now().isoformat(),
            )
            append_transaction(tx_ws, row)
            st.success("เพิ่มรายการแล้ว ✅")
            st.rerun()

    st.write("")
    st.markdown("**Transactions**")
    if df.empty:
        st.caption("0 rows")
    else:
        show = df.copy()
        show["Date"] = show["tx_date"].dt.date.astype(str)
        show["Amount"] = show["base"].round(0).astype(int)
        show["VAT"] = show["vat"].round(0).astype(int)
        show["Net"] = show["net"].round(0).astype(int)
        show = show.rename(columns={
            "project":"Project",
            "tx_type":"Type",
            "category":"Category",
            "vendor":"Vendor",
            "description":"Description",
            "qty":"Qty",
            "unit_price":"Unit",
            "status":"Status",
            "ref":"Ref",
        })
        cols = ["id","Date","Project","Type","Category","Vendor","Description","Qty","Unit","Amount","VAT","Net","Status","Ref"]
        st.dataframe(show[cols], use_container_width=True, hide_index=True)

    st.markdown("</div>", unsafe_allow_html=True)


elif nav == "Transactions":
    st.markdown("### Transactions")
    st.caption("ดูรายการตามเดือน + ค้นหา และลบรายการที่กรอกผิด (Google Sheets)")

    if df.empty:
        st.info("ไม่มีรายการในช่วงที่เลือก")
    else:
        st.markdown("#### Delete Transaction")
        id_list = df["id"].astype(int).sort_values(ascending=False).tolist()

        colA, colB, colC = st.columns([1.2, 1.2, 2.6], vertical_alignment="center")
        with colA:
            selected_id = st.selectbox("เลือก ID ที่ต้องการลบ", id_list)
        with colB:
            confirm = st.checkbox("ยืนยันว่าต้องการลบ", value=False)
        with colC:
            st.caption("ลบแล้วกู้คืนไม่ได้ทันที แต่ย้อนจาก Version history ของ Google Sheets ได้")

        preview = df[df["id"].astype(int) == int(selected_id)].head(1)
        if not preview.empty:
            p = preview.iloc[0]
            _, _, net = calc_amount(p.get("qty"), p.get("unit_price"), p.get("vat_percent"))
            st.write(f"กำลังจะลบ: **{p.get('tx_date').date()} | {p.get('tx_type')} | {p.get('project','')} | Net {money(net)}**")

        if st.button("🗑️ Delete Selected Transaction", type="primary", disabled=not confirm):
            ok = delete_transaction_by_id(tx_ws, int(selected_id))
            if ok:
                st.success(f"ลบรายการ ID={selected_id} เรียบร้อย ✅")
                st.rerun()
            else:
                st.error("ไม่พบรายการนี้ในชีท (อาจถูกลบไปแล้ว)")

        st.markdown("---")
        out = df.copy()
        out["tx_date"] = out["tx_date"].dt.date.astype(str)
        out = out.sort_values(["tx_date","id"], ascending=[False, False])
        st.dataframe(out, use_container_width=True, hide_index=True)


elif nav == "Export":
    st.markdown("### Export")
    st.caption("ดาวน์โหลด CSV ตามเดือน/การค้นหา")

    if df.empty:
        st.warning("ไม่มีข้อมูลให้ Export")
    else:
        out = df.copy()
        out["tx_date"] = out["tx_date"].dt.date.astype(str)
        csv_bytes = out.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name="transactions_export.csv",
            mime="text/csv",
            use_container_width=True
        )


elif nav == "Achievement":
    st.markdown("### Achievement")
    st.caption("ตั้งเป้าหมายยอดขายรายปี และ (ถ้าต้องการ) override เป้ารายเดือน")

    if ach_ws is None:
        st.error("ยังไม่มีแท็บชื่อ `achievement` ใน Google Sheets")
        st.info("ไปที่ Google Sheets → เพิ่ม Sheet ใหม่ → ตั้งชื่อแท็บว่า `achievement` แล้วกลับมารีเฟรชหน้านี้")
        st.stop()

    ensure_headers(ach_ws, ACH_HEADERS)
    ach_df = read_achievement(ach_ws)

    year_input = st.number_input("เลือกปีที่ต้องการตั้งเป้า", min_value=2000, max_value=2100, value=int(year_selected), step=1)

    annual, monthly_map = get_targets_for_year(ach_df, int(year_input))

    st.markdown("#### เป้าหมายรายปี")
    col1, col2 = st.columns([1.2, 1.0], vertical_alignment="center")
    with col1:
        annual_new = st.number_input("ตั้งเป้ายอดขายทั้งปี (บาท)", min_value=0.0, value=float(annual), step=10000.0)
    with col2:
        st.caption("ถ้าตั้งรายปี = ระบบเฉลี่ยต่อเดือนอัตโนมัติ (รายปี / 12)")
        save_year = st.button("บันทึกเป้ารายปี", use_container_width=True)

    if save_year:
        upsert_target(ach_ws, int(year_input), 0, float(annual_new))
        st.success("บันทึกเป้ารายปีแล้ว ✅")
        st.rerun()

    st.markdown("#### เป้าหมายรายเดือน (Optional)")
    st.caption("ถ้าใส่ 0 = ใช้ค่าเฉลี่ยจากรายปีแทน")

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    rows = []
    for m in range(1, 13):
        rows.append({"month": m, "month_name": months[m-1], "target": float(monthly_map.get(m, 0.0))})

    editor_df = pd.DataFrame(rows)
    edited = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "month": st.column_config.NumberColumn("Month", disabled=True),
            "month_name": st.column_config.TextColumn("Name", disabled=True),
            "target": st.column_config.NumberColumn("Monthly Target (บาท)", min_value=0.0, step=1000.0),
        }
    )

    if st.button("บันทึกเป้ารายเดือน", type="primary", use_container_width=True):
        for _, r in edited.iterrows():
            m = int(r["month"])
            t = float(r["target"] or 0.0)
            upsert_target(ach_ws, int(year_input), m, t)
        st.success("บันทึกเป้ารายเดือนแล้ว ✅")
        st.rerun()

    st.markdown("---")
    st.markdown("#### ตัวอย่างตามโจทย์")
    st.write(f"- ถ้าตั้งเป้ารายปี {money(10_000_000)} → ค่าเฉลี่ยต่อเดือน {money(10_000_000/12)}")
    st.write("- Dashboard จะแสดงยอดเดือนนี้ / เป้ารายเดือน + ยังขาดอีกเท่าไหร่ + % พร้อม progress bar")
