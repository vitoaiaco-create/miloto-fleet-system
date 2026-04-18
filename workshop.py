import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SETUP & CONFIGURATION ---
# This creates a safe storage file for your data if it doesn't exist yet
DATA_FILE = "workshop_log.csv"
LIST_OF_TRUCKS = ["Truck 001", "Truck 002", "Truck 003", "Truck 004", "Truck 005"]

if not os.path.exists(DATA_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Trucks", "Reason", "Notes", "Logged By"])
    df_empty.to_csv(DATA_FILE, index=False)

# --- 2. HEADER ---
st.title("🛠️ Workshop & Downtime Log")
st.markdown("Log vehicles entering the workshop and manage historical downtime records.")
st.divider()

# --- 3. LOG NEW DOWNTIME (WITH AUTO-CLEAR) ---
st.subheader("📝 Log New Downtime")

col1, col2 = st.columns(2)

with col1:
    log_date = st.date_input("Date", datetime.today())
    # FIX 1: The 'key' connects this box to Streamlit's memory so we can empty it later
    selected_trucks = st.multiselect("Select Trucks", LIST_OF_TRUCKS, key="truck_selector")

with col2:
    reason = st.selectbox("Reason for Downtime", ["Routine Service", "Breakdown", "Tyre Change", "Accident/Repair"])
    notes = st.text_area("Mechanic Notes")

if st.button("💾 Save to Workshop Log", use_container_width=True):
    if len(selected_trucks) == 0:
        st.warning("⚠️ Please select at least one truck before saving.")
    else:
        # Format the new data
        new_data = {
            "Date": [log_date.strftime("%Y-%m-%d")],
            "Trucks": [", ".join(selected_trucks)],
            "Reason": [reason],
            "Notes": [notes],
            "Logged By": [st.session_state.get("role", "Unknown")]
        }
        df_new = pd.DataFrame(new_data)
        
        # Save it to the CSV file
        df_new.to_csv(DATA_FILE, mode='a', header=False, index=False)
        
        # FIX 1 (Continued): Empty the truck box memory and instantly refresh the page
        st.session_state.truck_selector = []
        st.rerun()

st.divider()

# --- 4. HISTORICAL LOG (WITH DELETION CAPABILITY) ---
st.subheader("📚 Historical Downtime Record")
st.caption("Tip: Click the checkbox on the far left of any row and press 'Delete' on your keyboard to remove mistakes.")

# Load the saved data
df_history = pd.read_csv(DATA_FILE)

# FIX 2: Using st.data_editor with num_rows="dynamic" turns the table into an editable spreadsheet
edited_history = st.data_editor(
    df_history,
    num_rows="dynamic",
    use_container_width=True,
    key="history_editor",
    hide_index=True
)

# Auto-Save Logic for the Historical Log: 
# If a checker deletes a row, this detects the change and automatically saves the new, shorter list.
if not edited_history.equals(df_history):
    edited_history.to_csv(DATA_FILE, index=False)
    st.success("🔄 Log updated successfully!")
    st.rerun()
