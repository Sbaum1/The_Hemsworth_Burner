# 🦸 Hemsworth V6.2 Training System — Full Control + Working Day & Block Builder

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import plotly.express as px
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# -------------------------------------------------
# Setup
# -------------------------------------------------
st.set_page_config(page_title="Hemsworth Training System", layout="wide")
st.title("🦸 Hemsworth V6.2 Training System")
st.caption("Full Control Edition — Working Day/Block Builder + Safe Data Types")

DATA_PATH = Path("data") / "Hemsworth_Lift_Library.xlsx"
LOG_PATH = Path("data") / "user_logs.csv"
BLOCK_PATH = Path("data") / "custom_blocks.csv"
CUSTOM_DAY_PATH = Path("data") / "Hemsworth_Custom_Days.csv"
UNDO_PATH = Path("data") / "undo_last_save.csv"

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def ensure_dirs():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
ensure_dirs()

def load_library(path: Path):
    """Load Excel safely and fix column names."""
    if not path.exists():
        st.error(f"❌ File not found: {path}")
        return None
    df = pd.read_excel(path, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    # Normalize column names
    for c in list(df.columns):
        if "rest" in c.lower() and c != "Rest":
            df.rename(columns={c: "Rest"}, inplace=True)
    if "Rest" in df.columns:
        df["Rest"] = df["Rest"].astype(str)
    return df

def load_csv(path: Path, cols: list[str]):
    """Load CSV safely."""
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        df = df[cols]
    else:
        df = pd.DataFrame(columns=cols)
    return df

def save_csv(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False)

def plan_columns():
    return [
        "DayTag","Order","Lift / Exercise","Purpose / Role",
        "Region / Muscle Focus","Standard Sets×Reps",
        "Hemsworth Sets×Reps","Rest"
    ]

def _plan_type_safety(plan: pd.DataFrame) -> pd.DataFrame:
    """Ensure consistent column types."""
    plan = plan.copy()
    for c in plan.columns:
        plan[c] = plan[c].astype(str)
    if "Order" in plan.columns:
        plan["Order"] = pd.to_numeric(plan["Order"], errors="coerce").fillna(1).astype(int)
    return plan

def get_master_row(df_master, lift_name):
    row = df_master[df_master["Lift / Exercise"] == lift_name]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "Purpose / Role": r.get("Purpose / Role", ""),
        "Region / Muscle Focus": r.get("Region / Muscle Focus", ""),
        "Standard Sets×Reps": r.get("Standard Sets×Reps", ""),
        "Hemsworth Sets×Reps": r.get("Hemsworth Sets×Reps", ""),
        "Rest": r.get("Rest", "")
    }

def normalize_order(df: pd.DataFrame):
    df = df.sort_values("Order").reset_index(drop=True)
    df["Order"] = range(1, len(df)+1)
    return df

# -------------------------------------------------
# Load Data
# -------------------------------------------------
df = load_library(DATA_PATH)
if df is None:
    st.stop()

# Show diagnostic preview
st.write("📘 Excel Loaded:", len(df), "rows")
st.dataframe(df.head(), use_container_width=True)

user_log = load_csv(LOG_PATH, ["Date","DayTag","Lift / Exercise","Weight (lbs)","Reps","Notes","Mode"])
custom_blocks = load_csv(BLOCK_PATH, ["Lift / Exercise","BlockGroup","DayTag","Purpose / Role"])
custom_days = load_csv(CUSTOM_DAY_PATH, plan_columns())

# -------------------------------------------------
# Fixed get_day_plan()
# -------------------------------------------------
def get_day_plan(day: str, df_master: pd.DataFrame, df_custom: pd.DataFrame):
    """Build plan from Excel or custom override."""
    df_master.columns = [str(c).strip() for c in df_master.columns]
    if "DayTag" not in df_master.columns:
        st.error("⚠️ 'DayTag' column missing in your Excel.")
        return pd.DataFrame(columns=plan_columns())

    df_master["DayTag"] = df_master["DayTag"].astype(str).str.strip()
    base = df_master[df_master["DayTag"].str.lower() == day.lower()].copy()

    # Check for user override
    custom = df_custom[df_custom["DayTag"] == day]
    if not custom.empty:
        return _plan_type_safety(custom.sort_values("Order").reset_index(drop=True))

    plan = pd.DataFrame(columns=plan_columns())
    if base.empty:
        return _plan_type_safety(plan)

    for order, (_, r) in enumerate(base.iterrows(), start=1):
        plan.loc[len(plan)] = {
            "DayTag": day,
            "Order": order,
            "Lift / Exercise": r.get("Lift / Exercise", ""),
            "Purpose / Role": r.get("Purpose / Role", ""),
            "Region / Muscle Focus": r.get("Region / Muscle Focus", ""),
            "Standard Sets×Reps": r.get("Standard Sets×Reps", ""),
            "Hemsworth Sets×Reps": r.get("Hemsworth Sets×Reps", ""),
            "Rest": str(r.get("Rest", ""))
        }
    return _plan_type_safety(plan)

# -------------------------------------------------
# Mode / Tabs
# -------------------------------------------------
mode = st.radio("Select Training Mode:", ["Standard","Hemsworth High Volume"], horizontal=True)
sets_col = "Standard Sets×Reps" if mode == "Standard" else "Hemsworth Sets×Reps"

tab_names = ["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6","Core","📊 Progress","🧱 Day Builder","🧩 Block Builder","⚙️ Reset"]
tabs = st.tabs(tab_names)

# -------------------------------------------------
# Training Tabs
# -------------------------------------------------
for day, tab in zip(tab_names[:7], tabs[:7]):
    with tab:
        st.subheader(f"🏋️ {day}")
        plan = get_day_plan(day, df, custom_days)

        with st.expander("✏️ Edit Day Layout"):
            if plan.empty:
                st.info("No lifts found.")
            else:
                master_lifts = sorted(df["Lift / Exercise"].dropna().unique().tolist())
                edited = []
                for i, row in plan.iterrows():
                    c1,c2,c3,c4 = st.columns([3,1,3,1])
                    with c1:
                        st.write(f"{row['Order']}. {row['Lift / Exercise']}")
                    with c2:
                        act = st.selectbox("Action", ["Keep","Replace","Remove"], key=f"act_{day}_{i}")
                    with c3:
                        repl = None
                        if act == "Replace":
                            repl = st.selectbox("Replace with", master_lifts, key=f"rep_{day}_{i}")
                    with c4:
                        new_order = st.number_input("Order", 1, 99, int(row["Order"]), key=f"ord_{day}_{i}")
                    if act == "Remove":
                        continue
                    elif act == "Replace" and repl:
                        meta = get_master_row(df, repl)
                        edited.append({
                            "DayTag": day, "Order": new_order, "Lift / Exercise": repl,
                            **meta
                        })
                    else:
                        r = row.to_dict()
                        r["Order"] = int(new_order)
                        edited.append(r)
                if st.button(f"💾 Save {day} Layout"):
                    updated = custom_days[custom_days["DayTag"] != day]
                    new_day = pd.DataFrame(edited, columns=plan_columns())
                    save_csv(pd.concat([updated, normalize_order(new_day)], ignore_index=True), CUSTOM_DAY_PATH)
                    st.success("Saved layout.")
                if st.button(f"↩️ Reset {day}"):
                    save_csv(custom_days[custom_days["DayTag"] != day], CUSTOM_DAY_PATH)
                    st.success("Reset to default.")

        plan = get_day_plan(day, df, load_csv(CUSTOM_DAY_PATH, plan_columns()))
        if plan.empty:
            st.info("No lifts configured.")
            continue

        st.dataframe(plan[[ "Order","Lift / Exercise","Purpose / Role","Region / Muscle Focus",sets_col,"Rest"]].rename(columns={sets_col:"Sets×Reps"}), use_container_width=True)

        st.markdown("### Log Sets")
        bulk = []
        for i, row in plan.iterrows():
            c1,c2,c3,c4,c5 = st.columns([3,1,1,1,2])
            with c1: st.write(f"**{row['Lift / Exercise']}**")
            with c2: w = st.number_input("Weight",0,9999,0,5,key=f"w_{day}_{i}")
            with c3: r = st.number_input("Reps",0,200,0,1,key=f"r_{day}_{i}")
            with c4: n = st.text_input("Notes",key=f"n_{day}_{i}")
            with c5:
                if st.button("Save",key=f"s_{day}_{i}"):
                    new = {"Date":datetime.now().strftime("%Y-%m-%d %H:%M"),"DayTag":day,
                           "Lift / Exercise":row["Lift / Exercise"],"Weight (lbs)":w,"Reps":r,"Notes":n,"Mode":mode}
                    user_log.loc[len(user_log)] = new
                    save_csv(user_log, LOG_PATH)
                    st.success("Saved.")
            bulk.append((row["Lift / Exercise"],w,r,n))
        if st.button(f"💾 Save ALL {day}"):
            new = pd.DataFrame([{"Date":datetime.now().strftime("%Y-%m-%d %H:%M"),
                                 "DayTag":day,"Lift / Exercise":a,"Weight (lbs)":b,
                                 "Reps":c,"Notes":d,"Mode":mode} for a,b,c,d in bulk])
            user_log = pd.concat([user_log,new],ignore_index=True)
            save_csv(user_log,LOG_PATH)
            st.success("Saved all sets.")
        st.dataframe(user_log[user_log["DayTag"]==day].tail(10), use_container_width=True)

# -------------------------------------------------
# Progress Tab
# -------------------------------------------------
with tabs[7]:
    st.header("📊 Progress Dashboard")
    if user_log.empty:
        st.info("No logs yet.")
        st.stop()
    user_log["Date"]=pd.to_datetime(user_log["Date"],errors="coerce")
    user_log["Volume"]=user_log["Weight (lbs)"]*user_log["Reps"]
    user_log["Week"]=user_log["Date"].dt.isocalendar().week
    dsel=st.selectbox("Day",["All"]+sorted(user_log["DayTag"].unique()))
    lsel=st.selectbox("Lift",["All"]+sorted(user_log["Lift / Exercise"].unique()))
    f=user_log.copy()
    if dsel!="All": f=f[f["DayTag"]==dsel]
    if lsel!="All": f=f[f["Lift / Exercise"]==lsel]
    trend=f.groupby("Date",as_index=False)["Volume"].sum().sort_values("Date")
    st.plotly_chart(px.line(trend,x="Date",y="Volume",markers=True,template="plotly_dark"),use_container_width=True)
    prs=f.groupby("Lift / Exercise",as_index=False).agg({"Weight (lbs)":"max","Reps":"max","Volume":"max"})
    st.dataframe(prs,use_container_width=True)
    week=f.groupby(["Week","DayTag"],as_index=False)[["Weight (lbs)","Reps","Volume"]].sum()
    st.plotly_chart(px.bar(week,x="Week",y="Volume",color="DayTag",barmode="group",template="plotly_dark"),use_container_width=True)
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine="openpyxl") as w:
        user_log.to_excel(w,"All Logs",index=False)
        prs.to_excel(w,"PRs",index=False)
        week.to_excel(w,"Weekly",index=False)
    buf.seek(0)
    st.download_button("📘 Download Excel Report",buf,file_name=f"Hemsworth_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -------------------------------------------------
# Block Builder Tab
# -------------------------------------------------
with tabs[9]:
    st.header("🧩 Custom Block Builder")
    if df.empty:
        st.info("Lift library empty.")
    else:
        lift_choice = st.selectbox("Select Lift", sorted(df["Lift / Exercise"].unique().tolist()))
        block_choice = st.selectbox("Block", ["A","B","C","D","E"])
        day_choice = st.selectbox("Assign to Day", ["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6"])
        purpose = st.text_input("Purpose / Role")

        if st.button("➕ Add to Custom Block"):
            new_row = {"Lift / Exercise":lift_choice,"BlockGroup":block_choice,"DayTag":day_choice,"Purpose / Role":purpose}
            custom_blocks.loc[len(custom_blocks)] = new_row
            save_csv(custom_blocks, BLOCK_PATH)
            st.success(f"Added {lift_choice} to Block {block_choice} ({day_choice})")

        if not custom_blocks.empty:
            st.dataframe(custom_blocks,use_container_width=True)
        else:
            st.info("No custom blocks yet. Add one above.")

# -------------------------------------------------
# Reset Tab
# -------------------------------------------------
with tabs[10]:
    st.header("⚙️ Reset Options")
    c1,c2,c3=st.columns(3)
    with c1:
        if st.button("🧹 Clear Logs"):
            save_csv(pd.DataFrame(columns=user_log.columns),LOG_PATH)
            st.success("Logs cleared.")
    with c2:
        if st.button("🗑️ Clear Blocks"):
            save_csv(pd.DataFrame(columns=custom_blocks.columns),BLOCK_PATH)
            st.success("Blocks cleared.")
    with c3:
        if st.button("🗑️ Clear Custom Days"):
            save_csv(pd.DataFrame(columns=plan_columns()),CUSTOM_DAY_PATH)
            st.success("Custom days cleared.")
