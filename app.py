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
.block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1200px; }
.stApp { background-color:#0F172A; color:#E5E7EB; }
[data-testid="stSidebar"] { background:#0B1220; }
[data-testid="stSidebar"] * { color:#E5E7EB !important; }

.card {
  background:#111827;
  border:1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 10px 22px rgba(0,0,0,0.35);
}
.card-title { font-size: 12px; letter-spacing: .06em; color: rgba(229,231,235,.70); font-weight: 800; text-transform: uppercase;}
.card-value { font-size: 26px; font-weight: 900; margin-top: 4px; color:#E5E7EB; }
.card-sub { font-size: 12px; color: rgba(229,231,235,.60); margin-top: 2px; }
.small-muted { color: rgba(229,231,235,.65); font-size: 12px; }
hr.soft { border: none; height: 1px; background: rgba(255,255,255,0.10); margin: 14px 0; }
.sidebar-title { font-weight: 900; font-size: 16px; }
.sidebar-sub { font-size: 12px; opacity: .75; margin-top: -6px; }

.topbar {
  background:#111827;
  border:1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 10px 22px rgba(0,0,0,0.35);
}

div[data-testid="stDataFrame"] {
  background:#0B1220;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.08);
}

.stButton > button { background:#2563EB; color:white; border-radius:10px; border:0; }
</style>
"""

LIGHT_CSS = """
<style>
.block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1200px; }
.stApp { background-color:#F8FAFC; color:#0F172A; }
[data-testid="stSidebar"] { background:#FFFFFF; }

.card {
  background:#FFFFFF;
  border:1px solid rgba(15,23,42,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 6px 18px rgba(15,23,42,0.06);
}
.card-title { font-size: 12px; letter-spacing: .06em; color: rgba(15,23,42,.60); font-weight: 800; text-transform: uppercase;}
.card-value { font-size: 26px; font-weight: 900; margin-top: 4px; }
.card-sub { font-size: 12px; color: rgba(15,23,42,.55); margin-top: 2px; }
.small-muted { color: rgba(15,23,42,.55); font-size: 12px; }
hr.soft { border: none; height: 1px; background: rgba(15,23,42,0.08); margin: 14px 0; }
.sidebar-title { font-weight: 900; font-size: 16px; }
.sidebar-sub { font-size: 12px; opacity: .7; margin-top: -6px; }

.topbar {
  background:#FFFFFF;
  border:1px solid rgba(15,23,42,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 6px 18px rgba(15,23,42,0.06);
}

div[data-testid="stDataFrame"] {
  background:#FFFFFF;
  border-radius: 12px;
  border: 1px solid rgba(15,23,42,0.08);
}

.stButton > button { background:#2563EB; color:white; border-radius:10px; border:0; }
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

def month_range(month: date):
    start = month.replace(day=1)
    end = (start + relativedelta(months=1)) - relativedelta(days=1)
    return start, end

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

    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("'''") and raw.endswith("'''"):
            raw = raw[3:-3].strip()

    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def get_sheet():
    sheet_id = st.secrets.get("GSHEET_ID", "")
    if not sheet_id:
        st.error("Missing GSHEET_ID in Secrets")
        st.stop()
    gc = get_gspread_client()
    sh = gc.open_by_key(sheet_id)
    return sh.worksheet("transactions")

REQUIRED_HEADERS = [
    "id","tx_date","project","tx_type","category","vendor","description",
    "qty","unit_price","vat_percent","payment","status","ref","created_at"
]

def ensure_headers(ws):
    headers = ws.row_values(1)
    if headers == REQUIRED_HEADERS:
        return
    if len(headers) == 0:
        ws.append_row(REQUIRED_HEADERS)
        return
    st.error("Header row ในชีท 'transactions' ไม่ตรงตามที่ต้องการ กรุณาตั้งหัวคอลัมน์ให้ตรงนี้")
    st.code(",".join(REQUIRED_HEADERS))
    st.stop()

def read_transactions(ws) -> pd.DataFrame:
    ensure_headers(ws)
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

# -------- Delete helpers (by ID) --------
def find_row_by_id(ws, target_id: int):
    values = ws.get_all_values()  # includes header
    if len(values) <= 1:
        return None
    for i in range(1, len(values)):  # start after header
        row = values[i]
        if not row:
            continue
        try:
            rid = int(str(row[0]).strip())  # col A = id
        except:
            continue
        if rid == int(target_id):
            return i + 1  # convert 0-based list index to sheet row number
    return None

def delete_transaction_by_id(ws, target_id: int) -> bool:
    rownum = find_row_by_id(ws, target_id)
    if rownum is None:
        return False
    ws.delete_rows(rownum)
    return True

# -----------------------------
# Sidebar nav
# -----------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-title">Production P&L</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">Google Sheets • No Auth</div>', unsafe_allow_html=True)
    st.markdown('<hr class="soft">', unsafe_allow_html=True)
    nav = st.radio("", ["Dashboard", "Transactions", "Export"], index=0, label_visibility="collapsed")
    st.markdown('<hr class="soft">', unsafe_allow_html=True)
    st.caption("ข้อมูลเก็บใน Google Sheets ✅")

# -----------------------------
# Top bar (like screenshot)
# -----------------------------
st.markdown(
    f"""
<div class="topbar">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      <div style="font-weight:900; font-size:18px;">Production P&L Dashboard</div>
      <div class="small-muted">No Login/Signup • Theme: <b>{st.session_state.theme.upper()}</b></div>
    </div>
    <div class="small-muted"><b>Ready</b></div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)
st.write("")

# -----------------------------
# Filter bar (month + search + sample)
# -----------------------------
c1, c2, c3 = st.columns([1.1, 1.6, 1.0], vertical_alignment="center")
with c1:
    month_pick = st.date_input("เดือน", value=date.today().replace(day=1))
with c2:
    search = st.text_input("ค้นหา", value="", placeholder="โปรเจกต์/หมวด/คำอธิบาย/Ref…")
with c3:
    add_sample = st.button("ใส่ข้อมูลตัวอย่าง", use_container_width=True)

start, end = month_range(month_pick)

# -----------------------------
# Load from Google Sheets
# -----------------------------
ws = get_sheet()
df_all = read_transactions(ws)

# Add sample
if add_sample:
    nid = next_id(df_all)
    demo = [
        dict(id=nid, tx_date=start.isoformat(), project="Client A - TVC", tx_type="Income",
             category="Production Fee", vendor="Client A", description="Shooting day rate / milestone",
             qty=1, unit_price=8000, vat_percent=0, payment="Bank Transfer", status="Planned",
             ref="INV-001", created_at=datetime.now().isoformat()),
        dict(id=nid+1, tx_date=start.isoformat(), project="Client A - TVC", tx_type="Expense",
             category="Studio", vendor="Studio X", description="Studio rental",
             qty=1, unit_price=3500, vat_percent=7, payment="Bank Transfer", status="Paid",
             ref="RC-001", created_at=datetime.now().isoformat()),
    ]
    for r in demo:
        append_transaction(ws, r)
    st.success("ใส่ข้อมูลตัวอย่างแล้ว ✅")
    st.rerun()

# Filter month + search
if df_all.empty:
    df = df_all
else:
    df = df_all.copy()
    df = df[(df["tx_date"].dt.date >= start) & (df["tx_date"].dt.date <= end)]
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

# Compute totals
if df.empty:
    total_income = total_expense = profit = margin = 0.0
else:
    df["base"], df["vat"], df["net"] = zip(*df.apply(lambda r: calc_amount(r["qty"], r["unit_price"], r["vat_percent"]), axis=1))
    income_df = df[df["tx_type"] == "Income"]
    expense_df = df[df["tx_type"] == "Expense"]
    total_income = float(income_df["net"].sum())
    total_expense = float(expense_df["net"].sum())
    profit = total_income - total_expense
    margin = (profit / total_income * 100.0) if total_income > 0 else 0.0

# -----------------------------
# Pages
# -----------------------------
if nav == "Dashboard":
    st.markdown("### Dashboard")
    st.caption("ภาพรวมรายเดือน + บันทึกรายการ (Google Sheets)")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">TOTAL INCOME</div>
          <div class="card-value">{money(total_income)}</div>
          <div class="card-sub">รายรับรวม (เดือนที่เลือก)</div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">TOTAL EXPENSE</div>
          <div class="card-value">{money(total_expense)}</div>
          <div class="card-sub">รายจ่ายรวม (เดือนที่เลือก)</div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="card">
          <div class="card-title">PROFIT / LOSS</div>
          <div class="card-value">{money(profit)}</div>
          <div class="card-sub">กำไร/ขาดทุน</div>
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
    left, right = st.columns([2.1, 1.2])

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Monthly Chart** <span class='small-muted' style='float:right'>Income / Expense / Profit</span>",
                    unsafe_allow_html=True)
        if df.empty:
            st.info("ยังไม่มีข้อมูลในเดือนนี้")
        else:
            d = df.copy()
            d["day"] = d["tx_date"].dt.date.astype(str)
            daily = (
                d.groupby(["day","tx_type"], as_index=False)["net"].sum()
                .pivot(index="day", columns="tx_type", values="net")
                .fillna(0.0)
                .reset_index()
            )
            if "Income" not in daily.columns: daily["Income"] = 0.0
            if "Expense" not in daily.columns: daily["Expense"] = 0.0
            daily["Profit"] = daily["Income"] - daily["Expense"]
            melt = daily.melt("day", var_name="metric", value_name="value")
            chart = (
                alt.Chart(melt)
                .mark_line(point=True)
                .encode(
                    x=alt.X("day:N", title=""),
                    y=alt.Y("value:Q", title=""),
                    color=alt.Color("metric:N", title=""),
                    tooltip=["day","metric", alt.Tooltip("value:Q", format=",.0f")]
                )
                .properties(height=280)
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
            append_transaction(ws, row)
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


if nav == "Transactions":
    st.markdown("### Transactions")
    st.caption("ดูรายการตามเดือน + ค้นหา และลบรายการที่กรอกผิด (Google Sheets)")

    if df.empty:
        st.info("ไม่มีรายการในช่วงที่เลือก")
    else:
        # Delete block
        st.markdown("#### Delete Transaction")
        id_list = df["id"].astype(int).sort_values(ascending=False).tolist()

        colA, colB, colC = st.columns([1.2, 1.2, 2.6], vertical_alignment="center")
        with colA:
            selected_id = st.selectbox("เลือก ID ที่ต้องการลบ", id_list)
        with colB:
            confirm = st.checkbox("ยืนยันว่าต้องการลบ", value=False)
        with colC:
            st.caption("ลบแล้วกู้คืนไม่ได้ทันที แต่สามารถย้อนจาก Version history ของ Google Sheets ได้")

        preview = df[df["id"].astype(int) == int(selected_id)].head(1)
        if not preview.empty:
            p = preview.iloc[0]
            base, vat, net = calc_amount(p.get("qty"), p.get("unit_price"), p.get("vat_percent"))
            st.write(
                f"กำลังจะลบ: **{p.get('tx_date').date()} | {p.get('tx_type')} | {p.get('project','')} | "
                f"{p.get('category','')} | {p.get('vendor','')} | Net {money(net)}**"
            )

        if st.button("🗑️ Delete Selected Transaction", type="primary", disabled=not confirm):
            ok = delete_transaction_by_id(ws, int(selected_id))
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


if nav == "Export":
    st.markdown("### Export")
    st.caption("ดาวน์โหลด CSV ตามเดือน/การค้นหา (Google Sheets)")

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
