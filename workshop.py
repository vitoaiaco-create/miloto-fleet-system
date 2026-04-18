import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 1. SETUP & CONFIGURATION ---
DATA_FILE = "workshop_log.csv"

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

if not os.path.exists(DATA_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Trucks", "Status", "Logged By"])
    df_empty.to_csv(DATA_FILE, index=False)

# --- 2. LOGIC FUNCTIONS ---
def save_entry():
    selected = st.session_state.truck_selector
    date_val = st.session_state.date_holder
    shift_type = st.session_state.shift_holder
    
    if not selected:
        st.error("⚠️ Select trucks first!")
        return

    df = pd.read_csv(DATA_FILE)
    date_str = date_val.strftime("%Y-%m-%d")
    
    for truck in selected:
        mask = (df['Date'] == date_str) & (df['Trucks'] == truck)
        if mask.any() and shift_type == "Evening (Final)":
            df.loc[mask, 'Status'] = "Final"
        else:
            new_row = {"Date": date_str, "Trucks": truck, "Status": "Provisional" if "Morning" in shift_type else "Final", "Logged By": st.session_state.get("role", "User")}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.to_csv(DATA_FILE, index=False)
    st.session_state.truck_selector = []

def delete_last_row():
    df = pd.read_csv(DATA_FILE)
    if not df.empty:
        df = df.iloc[:-1] # Removes the very last line submitted
        df.to_csv(DATA_FILE, index=False)
        st.toast("🗑️ Last entry deleted!")

# --- 3. UI LAYOUT ---
st.title("🛠️ Workshop & Downtime Log")

col1, col2 = st.columns(2)
with col1:
    st.date_input("Date", datetime.today(), key="date_holder")
with col2:
    st.selectbox("Shift", ["Morning (Provisional)", "Evening (Final)"], key="shift_holder")

st.multiselect("Select Trucks", LIST_OF_TRUCKS, key="truck_selector")

# Action Buttons
st.button("💾 Submit Logs", use_container_width=True, on_click=save_entry, type="primary")

# --- 4. THE MISTAKE FIX (DEDICATED BUTTONS) ---
st.divider()
st.subheader("📋 Submitted Logs")

if os.path.exists(DATA_FILE):
    df_history = pd.read_csv(DATA_FILE)
    
    # Display the table (Editable for manual row deletion)
    edited_df = st.data_editor(df_history, use_container_width=True, num_rows="dynamic", hide_index=True)
    
    # Check for changes in the table (manual deletion)
    if len(edited_df) < len(df_history):
        edited_df.to_csv(DATA_FILE, index=False)
        st.rerun()

    # Rapid Delete Button for immediate mistakes
    if st.button("⬅️ Undo/Delete Last Entry", use_container_width=True):
        delete_last_row()
        st.rerun()
