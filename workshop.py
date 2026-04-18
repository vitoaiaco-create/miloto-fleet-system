import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SETUP & CONFIGURATION ---
DATA_FILE = "workshop_log.csv"

# GENERATED MILOTO HEAVY FLEET (01-127, excluding 30, 48, 107)
def generate_fleet():
    fleet = []
    excluded = {30, 48, 107}
    for i in range(1, 128):
        if i in excluded:
            continue
        num_str = f"{i:02d}"
        fleet.append(f"MILOTO-{num_str}(MTL{num_str})")
    return fleet

LIST_OF_TRUCKS = generate_fleet()

# Ensure the CSV exists
if not os.path.exists(DATA_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Trucks", "Logged By"])
    df_empty.to_csv(DATA_FILE, index=False)

# --- 2. THE LOGIC FUNCTION (The Fix) ---
def save_entry():
    # Pull the data from the widget state
    selected = st.session_state.truck_selector
    date_val = st.session_state.date_holder
    
    if not selected:
        st.error("⚠️ Please select at least one truck.")
        return

    # Create the row
    new_data = {
        "Date": [date_val.strftime("%Y-%m-%d")],
        "Trucks": [", ".join(selected)],
        "Logged By": [st.session_state.get("role", "Unknown")]
    }
    df_new = pd.DataFrame(new_data)
    
    # Save to CSV
    df_new.to_csv(DATA_FILE, mode='a', header=False, index=False)
    
    # CLEAR THE BOX: This is the safe way to do it
    st.session_state.truck_selector = []
    st.success("✅ Logged successfully!")

# --- 3. UI LAYOUT ---
st.title("🛠️ Workshop & Downtime Log")
st.markdown("Select trucks to log into the workshop system.")
st.divider()

# Inputs
st.date_input("Date", datetime.today(), key="date_holder")

st.multiselect(
    "Select Trucks", 
    LIST_OF_TRUCKS, 
    key="truck_selector"
)

# The Save Button now calls our function directly
st.button("💾 Save to Workshop Log", use_container_width=True, on_click=save_entry)

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

    # Save changes if a row is deleted
    if not edited_history.equals(df_history):
        edited_history.to_csv(DATA_FILE, index=False)
        st.rerun()
