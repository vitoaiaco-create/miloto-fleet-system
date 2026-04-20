import streamlit as st
import pandas as pd
from pyairtable import Api
from datetime import datetime

# --- 1. AIRTABLE CONNECTION ---
# This securely pulls the keys we just put in Streamlit Secrets
api = Api(st.secrets["AIRTABLE_TOKEN"])
table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Workshop Logs")

# --- 2. FLEET SETUP ---
def generate_fleet():
    fleet = []
    excluded = {30, 48, 107}
    for i in range(1, 128):
        if i in excluded: continue
            
        num_str = f"{i:02d}"
        fleet.append(f"MILOTO-{num_str}(MTL{num_str})")
    return fleet

LIST_OF_TRUCKS = generate_fleet()

# --- 3. LOGIC FUNCTIONS ---
def save_entry():
    selected = st.session_state.truck_selector
    date_val = st.session_state.date_holder
    shift_type = st.session_state.shift_holder
    
    if not selected:
        st.error("⚠️ Select trucks first!")
        return

    date_str = date_val.strftime("%Y-%m-%d")
    logged_by = st.session_state.get("role", "User")
    
    # Pull all records to check for Morning/Evening overrides
    records = table.all()
    
    for truck in selected:
        # Search Airtable for an existing record for this truck today
        existing_record_id = None
        for r in records:
            fields = r.get("fields", {})
            if fields.get("Date") == date_str and fields.get("Trucks") == truck:
                existing_record_id = r.get("id")
                break
                
        status_val = "Provisional" if "Morning" in shift_type else "Final"

        if existing_record_id and shift_type == "Evening (Final)":
            # Override to Final
            table.update(existing_record_id, {"Status": "Final", "Logged By": logged_by})
        elif not existing_record_id:
            # Create a brand new record in Airtable
            table.create({"Date": date_str, "Trucks": truck, "Status": status_val, "Logged By": logged_by})

    # Clear the box
    st.session_state.truck_selector = []

def delete_last_row():
    # Grabs the most recently created record in Airtable and deletes it
    records = table.all(sort=["-createdTime"])
    if records:
        table.delete(records[0]["id"])
        st.toast("🗑️ Last entry deleted!")

# --- 4. UI LAYOUT ---
st.title("🛠️ Workshop & Downtime Log")

col1, col2 = st.columns(2)
with col1:
    st.date_input("Date", datetime.today(), key="date_holder")
with col2:
    st.selectbox("Shift", ["Morning (Provisional)", "Evening (Final)"], key="shift_holder")

st.multiselect("Select Trucks", LIST_OF_TRUCKS, key="truck_selector")
st.button("💾 Submit Logs", use_container_width=True, on_click=save_entry, type="primary")

# --- 5. SUBMITTED LOGS ---
st.divider()
st.subheader("📋 Submitted Logs")

# Pull live data directly from Airtable
live_records = table.all(sort=["-createdTime"])

if live_records:
    # Convert Airtable JSON format into a clean Pandas table for the screen
    flat_data = [r["fields"] for r in live_records]
    df_history = pd.DataFrame(flat_data)
    
    # Ensure columns display in the right order
    cols_to_show = [col for col in ["Date", "Trucks", "Status", "Logged By"] if col in df_history.columns]
    
    st.dataframe(df_history[cols_to_show], use_container_width=True, hide_index=True)

if st.button("⬅️ Undo/Delete Last Entry", use_container_width=True):
    delete_last_row()
    st.rerun()
