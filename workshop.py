import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SETUP & CONFIGURATION ---
DATA_FILE = "workshop_log.csv"

# 👇 UPDATE YOUR FLEET NUMBERS HERE 👇
# Change these numbers to match your actual Miloto fleet! 
# Make sure each truck is wrapped in "quotes" and separated by a comma.
LIST_OF_TRUCKS = [
    "101", "102", "103", "104", "105", 
    "201", "202", "203", "204", "205"
]

# Create the CSV if it doesn't exist (Removed the 'Reason' column)
if not os.path.exists(DATA_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Trucks", "Notes", "Logged By"])
    df_empty.to_csv(DATA_FILE, index=False)

# --- 2. HEADER ---
st.title("🛠️ Workshop & Downtime Log")
st.markdown("Log vehicles entering the workshop and manage historical downtime records.")
st.divider()

# --- 3. LOG NEW DOWNTIME ---
st.subheader("📝 Log New Downtime")

col1, col2 = st.columns(2)

with col1:
    log_date = st.date_input("Date", datetime.today())
    selected_trucks = st.multiselect("Select Trucks", LIST_OF_TRUCKS, key="truck_selector")

with col2:
    # Moved Notes up to take the space of the removed Reason box
    notes = st.text_area("Mechanic Notes", height=100)

if st.button("💾 Save to Workshop Log", use_container_width=True):
    if len(selected_trucks) == 0:
        st.warning("⚠️ Please select at least one truck before saving.")
    else:
        # Format the new data without the Reason column
        new_data = {
            "Date": [log_date.strftime("%Y-%m-%d")],
            "Trucks": [", ".join(selected_trucks)],
            "Notes": [notes],
            "Logged By": [st.session_state.get("role", "Unknown")]
        }
        df_new = pd.DataFrame(new_data)
        
        # Save it to the CSV file
        df_new.to_csv(DATA_FILE, mode='a', header=False, index=False)
        
        # Empty the truck box memory and instantly refresh the page
        st.session_state.truck_selector = []
        st.rerun()

st.divider()

# --- 4. HISTORICAL LOG ---
st.subheader("📚 Historical Downtime Record")
st.caption("Tip: Click the checkbox on the far left of any row and press 'Delete' on your keyboard to remove mistakes.")

# Load the saved data
df_history = pd.read_csv(DATA_FILE)

# Editable spreadsheet
edited_history = st.data_editor(
    df_history,
    num_rows="dynamic",
    use_container_width=True,
    key="history_editor",
    hide_index=True
)

# Auto-Save Logic for the Historical Log
if not edited_history.equals(df_history):
    edited_history.to_csv(DATA_FILE, index=False)
    st.success("🔄 Log updated successfully!")
    st.rerun()
