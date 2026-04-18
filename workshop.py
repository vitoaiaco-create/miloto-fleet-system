import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SETUP & CONFIGURATION ---
DATA_FILE = "workshop_log.csv"

# GENERATED MILOTO HEAVY FLEET (01-127, excluding 30, 48, 107)
# Format: MILOTO-XX(MTLXX)
def generate_fleet():
    fleet = []
    excluded = {30, 48, 107}
    for i in range(1, 128):
        if i in excluded:
            continue
        # Format with leading zero for 1-9
        num_str = f"{i:02d}"
        fleet.append(f"MILOTO-{num_str}(MTL{num_str})")
    return fleet

LIST_OF_TRUCKS = generate_fleet()

# Ensure the CSV exists with correct columns
if not os.path.exists(DATA_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Trucks", "Logged By"])
    df_empty.to_csv(DATA_FILE, index=False)

# --- 2. HEADER ---
st.title("🛠️ Workshop & Downtime Log")
st.markdown("Select trucks to log into the workshop system.")
st.divider()

# --- 3. LOG NEW ENTRY ---
log_date = st.date_input("Date", datetime.today())

# Dropdown with the exact MILOTO-XX(MTLXX) format
selected_trucks = st.multiselect(
    "Select Trucks", 
    LIST_OF_TRUCKS, 
    key="truck_selector"
)

if st.button("💾 Save to Workshop Log", use_container_width=True):
    if not selected_trucks:
        st.warning("⚠️ Please select at least one truck.")
    else:
        new_data = {
            "Date": [log_date.strftime("%Y-%m-%d")],
            "Trucks": [", ".join(selected_trucks)],
            "Logged By": [st.session_state.get("role", "Unknown")]
        }
        df_new = pd.DataFrame(new_data)
        df_new.to_csv(DATA_FILE, mode='a', header=False, index=False)
        
        # Clear selection and refresh
        st.session_state.truck_selector = []
        st.rerun()

st.divider()

# --- 4. HISTORICAL LOG ---
st.subheader("📚 Historical Record")
if os.path.exists(DATA_FILE):
    df_history = pd.read_csv(DATA_FILE)
    
    # Editable table for deletions
    edited_history = st.data_editor(
        df_history,
        num_rows="dynamic",
        use_container_width=True,
        key="history_editor",
        hide_index=True
    )

    if not edited_history.equals(df_history):
        edited_history.to_csv(DATA_FILE, index=False)
        st.success("🔄 Log updated!")
        st.rerun()
