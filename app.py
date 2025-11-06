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

# ----------------------------
# Page setup
# ----------------------------
st.set_page_config(page_title="Hemsworth Training System", layout="wide")
st.title("🦸 Hemsworth V5 Training System")
st.caption("Step 6 – Export to Excel & PDF")

DATA_PATH = Path("data") / "Hemsworth_Lift_Library.xlsx"
LOG_PATH = Path("data") / "user_logs.csv"

# ----------------------------
# Load lift library
# ----------------------------
def load_library(path: Path):
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

# ----------------------------
# Load logs
# ----------------------------
if LOG_PATH.exists():
    user_log = pd.read_csv(LOG_PATH)
else:
    user_log = pd.DataFrame(columns=["Date","DayTag","Lift / Exercise","Weight (lbs)","Reps","Notes","Mode"])

# ----------------------------
# Training mode toggle
# ----------------------------
mode = st.radio("Select Training Mode:", ["Standard","Hemsworth High Volume"], horizontal=True)
sets_col = "Standard Sets×Reps" if mode == "Standard" else "Hemsworth Sets×Reps"

# ----------------------------
# Tabs
# ----------------------------
days = ["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6","Core","📊 Progress"]
tabs = st.tabs(days)

# ----------------------------
# Training tabs
# ----------------------------
for day, tab in zip(days[:-1], tabs[:-1]):
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
        st.markdown("**Recent Logs for this Day**")
        st.dataframe(user_log[user_log["DayTag"]==day].tail(10), use_container_width=True)

# ----------------------------
# 📊 Progress Tab + PR Analytics + Exports
# ----------------------------
with tabs[-1]:
    st.subheader("📊 Progress Dashboard & PR Tracker")
    if user_log.empty:
        st.info("No logs yet — train and save some sets first!")
        st.stop()

    user_log["Date"]=pd.to_datetime(user_log["Date"],errors="coerce")
    user_log["Volume"]=user_log["Weight (lbs)"]*user_log["Reps"]

    # Filters
    c1,c2=st.columns(2)
    with c1:
        d_filter=st.selectbox("Select Day",["All"]+sorted(user_log["DayTag"].dropna().unique().tolist()))
    with c2:
        l_filter=st.selectbox("Select Lift",["All"]+sorted(user_log["Lift / Exercise"].dropna().unique().tolist()))
    f=user_log.copy()
    if d_filter!="All": f=f[f["DayTag"]==d_filter]
    if l_filter!="All": f=f[f["Lift / Exercise"]==l_filter]

    # Charts
    st.markdown("### 📈 Training Volume Trend")
    trend=f.groupby("Date",as_index=False)["Volume"].sum().sort_values("Date")
    st.plotly_chart(px.line(trend,x="Date",y="Volume",markers=True,
                            title="Total Training Volume per Session",
                            template="plotly_dark"),use_container_width=True)

    st.markdown("### 🏆 Personal Records")
    prs=(f.groupby("Lift / Exercise",as_index=False)
           .agg({"Weight (lbs)":"max","Reps":"max","Volume":"max"}))
    prs.columns=["Lift / Exercise","Max Weight","Max Reps","Max Volume"]
    st.dataframe(prs,use_container_width=True)

    st.markdown("### 💪 Top 5 Heaviest Lifts")
    heavy=prs.sort_values("Max Weight",ascending=False).head(5)
    st.dataframe(heavy,use_container_width=True)

    st.markdown("### 🔥 Highest Volume Days")
    volume_day=f.groupby("Date",as_index=False)["Volume"].sum().sort_values("Volume",ascending=False).head(5)
    st.dataframe(volume_day,use_container_width=True)

    # ----------------------------
    # Export options
    # ----------------------------
    st.markdown("## 📤 Export Reports")

    # Excel export
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        user_log.to_excel(writer, sheet_name="All Logs", index=False)
        prs.to_excel(writer, sheet_name="PRs", index=False)
        heavy.to_excel(writer, sheet_name="Top Lifts", index=False)
        volume_day.to_excel(writer, sheet_name="Volume Days", index=False)
    excel_buffer.seek(0)
    st.download_button("📘 Download Excel Report",
                       excel_buffer,
                       file_name=f"Hemsworth_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # PDF export
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph("Hemsworth Training Weekly Report", styles["Title"]), Spacer(1,12)]
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1,12))
    story.append(Paragraph("Top 5 Heaviest Lifts", styles["Heading2"]))
    data = [["Lift","Max Weight","Max Reps","Max Volume"]] + heavy.values.tolist()
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#333333")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey),
        ('ALIGN',(0,0),(-1,-1),'CENTER')
    ]))
    story.append(table)
    story.append(Spacer(1,12))
    story.append(Paragraph("Highest Volume Days", styles["Heading2"]))
    data2 = [["Date","Volume"]] + volume_day.values.tolist()
    table2 = Table(data2)
    table2.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#333333")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('GRID',(0,0),(-1,-1),0.5,colors.grey),
        ('ALIGN',(0,0),(-1,-1),'CENTER')
    ]))
    story.append(table2)
    doc.build(story)
    pdf_buffer.seek(0)

    st.download_button("📄 Download PDF Summary",
                       pdf_buffer,
                       file_name=f"Hemsworth_Report_{datetime.now().strftime('%Y-%m-%d')}.pdf",
                       mime="application/pdf")
