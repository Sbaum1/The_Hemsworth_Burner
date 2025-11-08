# 🦸 Hemsworth V6.3 — Two-Week System + Per-Day Editor (Stable)
# - Week 1 (Main) + Week 2 (Variation) always available
# - Edit Day Layout per week (Keep / Replace / Remove / Reorder)
# - Safe loaders (fix PyArrow "Rest" errors; robust CSV handling)
# - Logging includes Week; Progress filters by Week/Day/Lift
# - Optional from-scratch Day Builder when a week's day is empty

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import plotly.express as px
from io import BytesIO

# Optional (you already had these installed; kept for continuity)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# -------------------------------------------------
# Setup & Paths
# -------------------------------------------------
st.set_page_config(page_title="Hemsworth Training System", layout="wide")
st.title("🦸 Hemsworth V6.3 — Two-Week System")
st.caption("Week 1 (Main) + Week 2 (Variation) • Per-Day Editor • Stable Loaders")

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

W1_PATH = DATA_DIR / "Hemsworth_Lift_Library.xlsx"
W2_PATH = DATA_DIR / "Hemsworth_Lift_Library_Week2.xlsx"
LOG_PATH = DATA_DIR / "user_logs.csv"
CUSTOM_DAY_PATH = DATA_DIR / "Hemsworth_Custom_Days.csv"
UNDO_PATH = DATA_DIR / "undo_last_save.csv"   # used for bulk save undo (optional)

# -------------------------------------------------
# Helpers (robust, Arrow-safe)
# -------------------------------------------------
REQUIRED_PLAN_COLS = [
    "Week","DayTag","Order","Lift / Exercise","Purpose / Role",
    "Region / Muscle Focus","Standard Sets×Reps","Hemsworth Sets×Reps","Rest"
]
LOG_COLS = ["Date","Week","DayTag","Lift / Exercise","Weight (lbs)","Reps","Notes","Mode"]

def _normalize_cols_str(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _coerce_rest_to_str(df: pd.DataFrame) -> pd.DataFrame:
    for c in list(df.columns):
        if "rest" in c.lower() and c != "Rest":
            df.rename(columns={c: "Rest"}, inplace=True)
    if "Rest" in df.columns:
        df["Rest"] = df["Rest"].astype(str)
    return df

def load_excel_as_str(path: Path) -> pd.DataFrame:
    """Load Excel with dtype=str; normalize columns; Rest->str. Empty df if missing."""
    if not path.exists():
        # Return empty shell with common columns so UI still works (user can build from scratch)
        return pd.DataFrame(columns=[
            "DayTag","Lift / Exercise","Purpose / Role","Region / Muscle Focus",
            "Standard Sets×Reps","Hemsworth Sets×Reps","Rest"
        ])
    df = pd.read_excel(path, dtype=str)
    df = _normalize_cols_str(df)
    df = _coerce_rest_to_str(df)
    return df

def load_logs(path: Path) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in LOG_COLS:
            if c not in df.columns:
                df[c] = ""
        df = df[LOG_COLS]
    else:
        df = pd.DataFrame(columns=LOG_COLS)
    return df

def load_custom_days(path: Path) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=REQUIRED_PLAN_COLS)
    # Ensure required columns exist, correct order
    for c in REQUIRED_PLAN_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[REQUIRED_PLAN_COLS]
    # Types & order
    df["Order"] = pd.to_numeric(df["Order"], errors="coerce").fillna(1).astype(int)
    df["Week"] = df["Week"].astype(str)
    df["DayTag"] = df["DayTag"].astype(str)
    return df

def save_csv(df: pd.DataFrame, path: Path):
    df.to_csv(path, index=False)

def normalize_order(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.sort_values("Order").reset_index(drop=True)
    df["Order"] = range(1, len(df)+1)
    return df

def plan_row_from_master(day: str, week: str, order: int, src: pd.Series) -> dict:
    return {
        "Week": week,
        "DayTag": day,
        "Order": int(order),
        "Lift / Exercise": src.get("Lift / Exercise",""),
        "Purpose / Role": src.get("Purpose / Role",""),
        "Region / Muscle Focus": src.get("Region / Muscle Focus",""),
        "Standard Sets×Reps": src.get("Standard Sets×Reps",""),
        "Hemsworth Sets×Reps": src.get("Hemsworth Sets×Reps",""),
        "Rest": str(src.get("Rest","")),
    }

def get_master_row(dfW1: pd.DataFrame, dfW2: pd.DataFrame, lift_name: str) -> dict:
    """Lookup lift metadata from Week1 first, then Week2."""
    for source in (dfW1, dfW2):
        if not source.empty and "Lift / Exercise" in source.columns:
            row = source[source["Lift / Exercise"] == lift_name]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "Purpose / Role": r.get("Purpose / Role",""),
                    "Region / Muscle Focus": r.get("Region / Muscle Focus",""),
                    "Standard Sets×Reps": r.get("Standard Sets×Reps",""),
                    "Hemsworth Sets×Reps": r.get("Hemsworth Sets×Reps",""),
                    "Rest": str(r.get("Rest","")),
                }
    return {"Purpose / Role":"","Region / Muscle Focus":"","Standard Sets×Reps":"","Hemsworth Sets×Reps":"","Rest":""}

def combine_master_lifts(dfW1: pd.DataFrame, dfW2: pd.DataFrame) -> list:
    lifts = set()
    for d in (dfW1, dfW2):
        if not d.empty and "Lift / Exercise" in d.columns:
            lifts.update(d["Lift / Exercise"].dropna().astype(str).tolist())
    return sorted(lifts)

def get_day_plan(day: str, week: str, dfW: pd.DataFrame, custom_days: pd.DataFrame) -> pd.DataFrame:
    """Return the effective plan for a given day+week (custom override > base)."""
    # Prefer custom override:
    cd = custom_days[(custom_days["Week"] == week) & (custom_days["DayTag"] == day)]
    if not cd.empty:
        # enforce safe types
        cd = cd.copy()
        cd["Order"] = pd.to_numeric(cd["Order"], errors="coerce").fillna(1).astype(int)
        return normalize_order(cd)

    # Build from base Excel for selected week:
    if dfW.empty:
        return pd.DataFrame(columns=REQUIRED_PLAN_COLS)

    base = dfW.copy()
    base["DayTag"] = base["DayTag"].astype(str).str.strip()
    base = base[base["DayTag"].str.lower() == day.lower()]
    if base.empty:
        return pd.DataFrame(columns=REQUIRED_PLAN_COLS)

    out = []
    for order, (_, r) in enumerate(base.iterrows(), start=1):
        out.append(plan_row_from_master(day, week, order, r))
    plan = pd.DataFrame(out, columns=REQUIRED_PLAN_COLS)
    return plan

# -------------------------------------------------
# Load both weeks on startup (always present)
# -------------------------------------------------
dfW1 = load_excel_as_str(W1_PATH)  # Week 1 (Main)
dfW2 = load_excel_as_str(W2_PATH)  # Week 2 (Variation)
user_log = load_logs(LOG_PATH)
custom_days = load_custom_days(CUSTOM_DAY_PATH)

# -------------------------------------------------
# Week & Mode selectors
# -------------------------------------------------
week_choice = st.radio("Select Training Week:", ["Week 1","Week 2"], horizontal=True)
week_num = "1" if week_choice == "Week 1" else "2"
mode = st.radio("Select Training Mode:", ["Standard","Hemsworth High Volume"], horizontal=True)
sets_col = "Standard Sets×Reps" if mode == "Standard" else "Hemsworth Sets×Reps"

# pick active week dataframe for this view
dfW_active = dfW1 if week_num == "1" else dfW2
master_lifts_all = combine_master_lifts(dfW1, dfW2)

# -------------------------------------------------
# Tabs
# -------------------------------------------------
tab_names = ["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6","Core","📊 Progress","⚙️ Reset"]
tabs = st.tabs(tab_names)

# -------------------------------------------------
# Training Tabs (Days + Core)
# -------------------------------------------------
for day, tab in zip(tab_names[:7], tabs[:7]):
    with tab:
        st.subheader(f"🏋️ {day} — {week_choice}")

        plan = get_day_plan(day, week_num, dfW_active, custom_days)

        # ---------- Edit Day Layout ----------
        with st.expander("✏️ Edit Day Layout (Keep / Replace / Remove / Reorder)", expanded=False):
            if plan.empty:
                st.info("No lifts found for this day/week. Add lifts below and Save.")
                # Minimal day builder when empty:
                add_rows = st.number_input(
    "How many lifts to add?",
    min_value=1,
    max_value=40,
    value=5,
    step=1,
    key=f"add_rows_{day}_{week_num}"
)
                new_entries = []
                for i in range(1, add_rows+1):
                    c1,c2,c3,c4 = st.columns([3,2,2,2])
                    with c1:
                        Lift = st.selectbox(f"Lift (row {i})", master_lifts_all, key=f"builder_lift_{day}_{week_num}_{i}")
                    meta = get_master_row(dfW1, dfW2, Lift)
                    with c2:
                        std_sr = st.text_input("Standard Sets×Reps", value=meta["Standard Sets×Reps"], key=f"builder_std_{day}_{week_num}_{i}")
                    with c3:
                        hv_sr = st.text_input("Hemsworth Sets×Reps", value=meta["Hemsworth Sets×Reps"], key=f"builder_hv_{day}_{week_num}_{i}")
                    with c4:
                        purpose = st.text_input("Purpose / Role", value=meta["Purpose / Role"], key=f"builder_purp_{day}_{week_num}_{i}")
                    new_entries.append({
                        "Week": week_num, "DayTag": day, "Order": i, "Lift / Exercise": Lift,
                        "Purpose / Role": purpose, "Region / Muscle Focus": meta["Region / Muscle Focus"],
                        "Standard Sets×Reps": std_sr, "Hemsworth Sets×Reps": hv_sr, "Rest": meta["Rest"]
                    })
                if st.button(f"💾 Save New {day} Layout for {week_choice}", key=f"save_new_{day}_{week_num}"):
                    # Remove existing custom rows for this day/week and write new
                    updated = custom_days[~((custom_days["Week"]==week_num) & (custom_days["DayTag"]==day))].copy()
                    out = pd.DataFrame(new_entries, columns=REQUIRED_PLAN_COLS)
                    out = normalize_order(out)
                    custom_days = pd.concat([updated, out], ignore_index=True)
                    save_csv(custom_days, CUSTOM_DAY_PATH)
                    st.success(f"Saved new custom layout for {day} — {week_choice}.")
            else:
                st.caption("Edits persist to data/Hemsworth_Custom_Days.csv (week-specific).")
                edited_rows = []
                for i, row in plan.iterrows():
                    c1,c2,c3,c4,c5 = st.columns([3,1.2,3,1.2,1.8])
                    with c1:
                        st.markdown(f"**{int(row['Order'])}. {row['Lift / Exercise']}**")
                        st.caption(f"{row.get('Purpose / Role','')} | {row.get('Region / Muscle Focus','')}")
                    with c2:
                        action = st.selectbox("Action", ["Keep","Replace","Remove"], key=f"act_{day}_{week_num}_{i}", index=0)
                    with c3:
                        replace_with = None
                        if action == "Replace":
                            replace_with = st.selectbox("Replace with", master_lifts_all, key=f"repl_{day}_{week_num}_{i}")
                    with c4:
                        new_order = st.number_input("Order", 1, 999, int(row["Order"]), step=1, key=f"ord_{day}_{week_num}_{i}")
                    with c5:
                        new_sets = st.text_input("Sets×Reps (override for selected mode)", value="", key=f"sets_{day}_{week_num}_{i}")

                    if action == "Remove":
                        continue
                    elif action == "Replace" and replace_with:
                        meta = get_master_row(dfW1, dfW2, replace_with)
                        base_std = meta["Standard Sets×Reps"]
                        base_hv  = meta["Hemsworth Sets×Reps"]
                        edited_rows.append({
                            "Week": week_num, "DayTag": day, "Order": int(new_order),
                            "Lift / Exercise": replace_with,
                            "Purpose / Role": meta["Purpose / Role"],
                            "Region / Muscle Focus": meta["Region / Muscle Focus"],
                            "Standard Sets×Reps": (new_sets if sets_col=="Standard Sets×Reps" and new_sets!="" else base_std),
                            "Hemsworth Sets×Reps": (new_sets if sets_col=="Hemsworth Sets×Reps" and new_sets!="" else base_hv),
                            "Rest": meta["Rest"]
                        })
                    else:
                        r = row.to_dict()
                        r["Order"] = int(new_order)
                        # Allow quick set override for active mode only
                        if new_sets != "":
                            if sets_col == "Standard Sets×Reps":
                                r["Standard Sets×Reps"] = new_sets
                            else:
                                r["Hemsworth Sets×Reps"] = new_sets
                        edited_rows.append(r)

                cA, cB = st.columns(2)
                with cA:
                    if st.button(f"💾 Save {day} Layout — {week_choice}", key=f"save_layout_{day}_{week_num}"):
                        updated = custom_days[~((custom_days["Week"]==week_num) & (custom_days["DayTag"]==day))].copy()
                        new_day_df = pd.DataFrame(edited_rows, columns=REQUIRED_PLAN_COLS)
                        new_day_df = normalize_order(new_day_df)
                        custom_days = pd.concat([updated, new_day_df], ignore_index=True)
                        save_csv(custom_days, CUSTOM_DAY_PATH)
                        st.success(f"Saved custom layout for {day} — {week_choice}.")
                with cB:
                    if st.button(f"↩️ Reset {day} to Default ({week_choice})", key=f"reset_layout_{day}_{week_num}"):
                        custom_days = custom_days[~((custom_days["Week"]==week_num) & (custom_days["DayTag"]==day))].copy()
                        save_csv(custom_days, CUSTOM_DAY_PATH)
                        st.success(f"Reset {day} to default for {week_choice}.")

        # ---------- Show Plan ----------
        plan = get_day_plan(day, week_num, dfW_active, custom_days)
        if plan.empty:
            st.info("No lifts configured yet. Use the editor above to add lifts.")
            continue

        view = plan[["Order","Lift / Exercise","Purpose / Role","Region / Muscle Focus",sets_col,"Rest"]].copy()
        view["Rest"] = view["Rest"].astype(str)
        st.markdown("### 📋 Today's Plan")
        st.dataframe(view.rename(columns={sets_col:"Sets×Reps"}), use_container_width=True)

        # ---------- Logging ----------
        st.markdown("### 🧰 Log Sets")
        bulk_rows = []
        for i, row in plan.iterrows():
            c1,c2,c3,c4,c5 = st.columns([3,1.2,1,2,1.2])
            with c1:
                st.markdown(f"**{row['Lift / Exercise']}**")
                st.caption(f"{row.get('Purpose / Role','')} | {row.get('Region / Muscle Focus','')}")
            with c2:
                w = st.number_input("Weight", 0, 9999, 0, 5, key=f"w_{day}_{week_num}_{i}")
            with c3:
                r = st.number_input("Reps", 0, 500, 0, 1, key=f"r_{day}_{week_num}_{i}")
            with c4:
                n = st.text_input("Notes", key=f"n_{day}_{week_num}_{i}")
            with c5:
                if st.button("💾 Save", key=f"s_{day}_{week_num}_{i}"):
                    new = {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Week": week_num,
                        "DayTag": day,
                        "Lift / Exercise": row["Lift / Exercise"],
                        "Weight (lbs)": w,
                        "Reps": r,
                        "Notes": n,
                        "Mode": mode
                    }
                    user_log.loc[len(user_log)] = new
                    save_csv(user_log, LOG_PATH)
                    st.success("Saved.")
            bulk_rows.append({
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Week": week_num,
                "DayTag": day,
                "Lift / Exercise": row["Lift / Exercise"],
                "Weight (lbs)": w,
                "Reps": r,
                "Notes": n,
                "Mode": mode
            })

        c_bulk1, c_bulk2 = st.columns([1,1])
        with c_bulk1:
            if st.button(f"💾 Save ALL for {day} — {week_choice}", key=f"bulk_save_{day}_{week_num}"):
                if bulk_rows:
                    # keep a copy for undo
                    save_csv(pd.DataFrame(bulk_rows, columns=LOG_COLS), UNDO_PATH)
                    user_log = pd.concat([user_log, pd.DataFrame(bulk_rows, columns=LOG_COLS)], ignore_index=True)
                    save_csv(user_log, LOG_PATH)
                    st.success(f"Saved {len(bulk_rows)} entries.")
        with c_bulk2:
            if st.button("↩️ Undo Last Bulk Save", key=f"undo_bulk_{day}_{week_num}"):
                if UNDO_PATH.exists():
                    undo_df = pd.read_csv(UNDO_PATH, dtype=str, keep_default_na=False)
                    if not undo_df.empty:
                        key_cols = LOG_COLS
                        merged = user_log.merge(undo_df[key_cols].assign(_flag=1), on=key_cols, how="left")
                        user_log = merged[merged["_flag"] != 1].drop(columns=["_flag"])
                        save_csv(user_log, LOG_PATH)
                        UNDO_PATH.unlink(missing_ok=True)
                        st.success("Last bulk save undone.")
                else:
                    st.info("No undo data found.")

        st.markdown("---")
        st.markdown("**Recent Logs for this Day & Week**")
        st.dataframe(user_log[(user_log["DayTag"]==day) & (user_log["Week"]==week_num)].tail(12), use_container_width=True)

# -------------------------------------------------
# 📊 Progress Dashboard
# -------------------------------------------------
with tabs[7]:
    st.header("📊 Progress & PRs")
    if user_log.empty:
        st.info("No logs yet.")
        st.stop()

    # safe numeric
    user_log["Date"] = pd.to_datetime(user_log["Date"], errors="coerce")
    user_log["Weight (lbs)"] = pd.to_numeric(user_log["Weight (lbs)"], errors="coerce").fillna(0)
    user_log["Reps"] = pd.to_numeric(user_log["Reps"], errors="coerce").fillna(0)
    user_log["Volume"] = user_log["Weight (lbs)"] * user_log["Reps"]

    c0,c1,c2 = st.columns(3)
    with c0:
        wk_filter = st.selectbox("Week", ["All","1","2"], index=0)
    with c1:
        d_filter = st.selectbox("Day", ["All"] + sorted(user_log["DayTag"].dropna().unique().tolist()))
    with c2:
        l_filter = st.selectbox("Lift", ["All"] + sorted(user_log["Lift / Exercise"].dropna().unique().tolist()))

    f = user_log.copy()
    if wk_filter != "All":
        f = f[f["Week"] == wk_filter]
    if d_filter != "All":
        f = f[f["DayTag"] == d_filter]
    if l_filter != "All":
        f = f[f["Lift / Exercise"] == l_filter]

    st.markdown("### 📈 Volume Trend")
    trend = f.groupby("Date", as_index=False)["Volume"].sum().sort_values("Date")
    st.plotly_chart(px.line(trend, x="Date", y="Volume", markers=True, template="plotly_dark"), use_container_width=True)

    st.markdown("### 🏆 Personal Records")
    prs = (f.groupby("Lift / Exercise", as_index=False)
           .agg({"Weight (lbs)":"max","Reps":"max","Volume":"max"}))
    prs.columns = ["Lift / Exercise","Max Weight","Max Reps","Max Volume"]
    st.dataframe(prs, use_container_width=True)

    st.markdown("### 📅 Weekly Summary (ISO Week)")
    f["WeekISO"] = f["Date"].dt.isocalendar().week
    week_summary = f.groupby(["WeekISO","DayTag"], as_index=False)[["Weight (lbs)","Reps","Volume"]].sum()
    st.dataframe(week_summary, use_container_width=True)
    st.plotly_chart(px.bar(week_summary, x="WeekISO", y="Volume", color="DayTag", barmode="group", template="plotly_dark"), use_container_width=True)

    # Export
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        user_log.to_excel(writer, sheet_name="All Logs", index=False)
        prs.to_excel(writer, sheet_name="PRs", index=False)
        week_summary.to_excel(writer, sheet_name="Weekly Summary", index=False)
    excel_buffer.seek(0)
    st.download_button("📘 Download Excel Report",
        excel_buffer,
        file_name=f"Hemsworth_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -------------------------------------------------
# ⚙️ Reset
# -------------------------------------------------
with tabs[8]:
    st.header("⚙️ Data Reset Options")
    st.warning("⚠️ Be careful — deleted data cannot be recovered!")

    c1,c2,c3 = st.columns(3)
    with c1:
        if st.button("🧹 Clear All Logs"):
            save_csv(pd.DataFrame(columns=LOG_COLS), LOG_PATH)
            st.success("All user logs cleared.")
    with c2:
        if st.button("🗑️ Clear Custom Days (All Weeks)"):
            save_csv(pd.DataFrame(columns=REQUIRED_PLAN_COLS), CUSTOM_DAY_PATH)
            st.success("All custom day layouts cleared.")
    with c3:
        if st.button("🧽 Clear Undo Buffer"):
            UNDO_PATH.unlink(missing_ok=True)
            st.success("Cleared undo buffer.")
