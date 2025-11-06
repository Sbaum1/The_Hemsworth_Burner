import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import plotly.express as px
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# -------------------------------------------------
# Setup
# -------------------------------------------------
st.set_page_config(page_title="Hemsworth Training System", layout="wide")
st.title("🦸 Hemsworth V6 Training System")
st.caption("Full Control Edition — Auto Summaries, Block Builder, and Reset Options")

DATA_PATH = Path("data") / "Hemsworth_Lift_Library.xlsx"
LOG_PATH = Path("data") / "user_logs.csv"
BLOCK_PATH = Path("data") / "custom_blocks.csv"

# -------------------------------------------------
# Load Lift Library
# -------------------------------------------------
def load_library(path):
    if not path.exists():
        st.error(f"File not found: {path}")
        return None
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        if "rest" in c.lower():
            df.rename(columns={c: "Rest"}, inplace=True)
            break
    return df

df = load_library(DATA_PATH)
if df is None:
    st.stop()

# -------------------------------------------------
# Load User Logs
# -------------------------------------------------
if LOG_PATH.exists():
    user_log = pd.read_csv(LOG_PATH)
else:
    user_log = pd.DataFrame(columns=["Date","DayTag","Lift / Exercise","Weight (lbs)","Reps","Notes","Mode"])

# -------------------------------------------------
# Load Custom Blocks
# -------------------------------------------------
if BLOCK_PATH.exists():
    custom_blocks = pd.read_csv(BLOCK_PATH)
else:
    custom_blocks = pd.DataFrame(columns=["Lift / Exercise","BlockGroup","DayTag","Purpose / Role"])

# -------------------------------------------------
# Training Mode Toggle
# -------------------------------------------------
mode = st.radio("Select Training Mode:", ["Standard","Hemsworth High Volume"], horizontal=True)
sets_col = "Standard Sets×Reps" if mode == "Standard" else "Hemsworth Sets×Reps"

# -------------------------------------------------
# Tabs
# -------------------------------------------------
days = ["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6","Core","📊 Progress","🧩 Block Builder","⚙️ Reset"]
tabs = st.tabs(days)

# -------------------------------------------------
# Training Tabs
# -------------------------------------------------
for day, tab in zip(days[:-3], tabs[:-3]):
    with tab:
        st.subheader(f"🏋️ {day}")
        dday = df[df["DayTag"].astype(str).str.lower() == day.lower()]
        if dday.empty:
            st.info(f"No lifts tagged for {day}.")
            continue
        for idx, row in dday.iterrows():
            c1,c2,c3,c4,c5,c6 = st.columns([3,1.3,1,1.5,2,1])
            with c1:
                st.markdown(f"**{row['Lift / Exercise']}**")
                st.caption(f"{row['Purpose / Role']} | {row['Region / Muscle Focus']}")
            with c2:
                st.markdown(f"**{mode}**")
                st.write(row[sets_col] if pd.notna(row[sets_col]) else "-")
            with c3:
                w = st.number_input("Weight", 0, None, 0, 5, key=f"w_{day}_{idx}")
            with c4:
                r = st.number_input("Reps", 0, None, 0, 1, key=f"r_{day}_{idx}")
            with c5:
                n = st.text_input("Notes (optional)", key=f"n_{day}_{idx}")
            with c6:
                if st.button("💾 Save", key=f"s_{day}_{idx}"):
                    new = {"Date":datetime.now().strftime("%Y-%m-%d %H:%M"),
                           "DayTag":day,"Lift / Exercise":row["Lift / Exercise"],
                           "Weight (lbs)":w,"Reps":r,"Notes":n,"Mode":mode}
                    user_log.loc[len(user_log)] = new
                    user_log.to_csv(LOG_PATH, index=False)
                    st.success(f"Saved {row['Lift / Exercise']}")
        st.markdown("---")
        st.dataframe(user_log[user_log["DayTag"]==day].tail(10), use_container_width=True)

# -------------------------------------------------
# 📊 Progress Dashboard + PRs + Weekly Summary
# -------------------------------------------------
with tabs[-3]:
    st.header("📊 Progress Dashboard")
    if user_log.empty:
        st.info("No training data yet — log some sets first.")
        st.stop()

    user_log["Date"]=pd.to_datetime(user_log["Date"],errors="coerce")
    user_log["Volume"]=user_log["Weight (lbs)"]*user_log["Reps"]
    user_log["Week"]=user_log["Date"].dt.isocalendar().week

    c1,c2=st.columns(2)
    with c1:
        d_filter=st.selectbox("Select Day",["All"]+sorted(user_log["DayTag"].dropna().unique().tolist()))
    with c2:
        l_filter=st.selectbox("Select Lift",["All"]+sorted(user_log["Lift / Exercise"].dropna().unique().tolist()))
    f=user_log.copy()
    if d_filter!="All": f=f[f["DayTag"]==d_filter]
    if l_filter!="All": f=f[f["Lift / Exercise"]==l_filter]

    st.markdown("### 📈 Volume Trend")
    trend=f.groupby("Date",as_index=False)["Volume"].sum().sort_values("Date")
    st.plotly_chart(px.line(trend,x="Date",y="Volume",markers=True,template="plotly_dark"),use_container_width=True)

    st.markdown("### 🏆 Personal Records")
    prs=(f.groupby("Lift / Exercise",as_index=False)
         .agg({"Weight (lbs)":"max","Reps":"max","Volume":"max"}))
    prs.columns=["Lift / Exercise","Max Weight","Max Reps","Max Volume"]
    st.dataframe(prs,use_container_width=True)

    # Weekly summary
    st.markdown("### 📅 Weekly Summary")
    week_summary=f.groupby(["Week","DayTag"],as_index=False)[["Weight (lbs)","Reps","Volume"]].sum()
    st.dataframe(week_summary,use_container_width=True)
    st.plotly_chart(px.bar(week_summary,x="Week",y="Volume",color="DayTag",barmode="group",template="plotly_dark"))

    # Export section
    excel_buffer=BytesIO()
    with pd.ExcelWriter(excel_buffer,engine="openpyxl") as writer:
        user_log.to_excel(writer,sheet_name="All Logs",index=False)
        prs.to_excel(writer,sheet_name="PRs",index=False)
        week_summary.to_excel(writer,sheet_name="Weekly Summary",index=False)
    excel_buffer.seek(0)
    st.download_button("📘 Download Excel Report",excel_buffer,file_name=f"Hemsworth_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -------------------------------------------------
# 🧩 Block Builder
# -------------------------------------------------
with tabs[-2]:
    st.header("🧩 Custom Block Builder")
    lift_choice = st.selectbox("Select Lift", sorted(df["Lift / Exercise"].unique().tolist()))
    block_choice = st.selectbox("Block", ["A","B","C","D","E"])
    day_choice = st.selectbox("Assign to Day", ["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6"])
    purpose = st.text_input("Purpose / Role")

    if st.button("➕ Add to Custom Block"):
        new_row = {"Lift / Exercise":lift_choice,"BlockGroup":block_choice,"DayTag":day_choice,"Purpose / Role":purpose}
        custom_blocks.loc[len(custom_blocks)] = new_row
        custom_blocks.to_csv(BLOCK_PATH, index=False)
        st.success(f"Added {lift_choice} to Block {block_choice} ({day_choice})")

    st.markdown("### Current Custom Blocks")
    if not custom_blocks.empty:
        st.dataframe(custom_blocks,use_container_width=True)
    else:
        st.info("No custom blocks yet. Add some using the form above.")

# -------------------------------------------------
# ⚙️ Reset Options
# -------------------------------------------------
with tabs[-1]:
    st.header("⚙️ Data Reset Options")
    st.warning("⚠️ Be careful — deleted data cannot be recovered!")

    col1,col2=st.columns(2)
    with col1:
        if st.button("🧹 Clear All Logs"):
            user_log = pd.DataFrame(columns=["Date","DayTag","Lift / Exercise","Weight (lbs)","Reps","Notes","Mode"])
            user_log.to_csv(LOG_PATH, index=False)
            st.success("All user logs cleared.")
    with col2:
        if st.button("🗑️ Clear Custom Blocks"):
            custom_blocks = pd.DataFrame(columns=["Lift / Exercise","BlockGroup","DayTag","Purpose / Role"])
            custom_blocks.to_csv(BLOCK_PATH, index=False)
            st.success("All custom blocks cleared.")
