import streamlit as st
import pandas as pd
from pyairtable import Api
from datetime import datetime

# --- 1. AIRTABLE CONNECTION ---
api = Api(st.secrets["AIRTABLE_TOKEN"])
table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Oil & Servicing")

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
def save_service_entry():
    truck = st.session_state.os_truck
    service_type = st.session_state.os_type
    odometer = st.session_state.os_odo
    notes = st.session_state.os_notes
    
    if not truck:
        st.error("⚠️ Please select a truck.")
        return

    new_record = {
        "Date": datetime.today().strftime("%Y-%m-%d"),
        "Truck": truck,
        "Service Type": service_type,
        "Odometer": str(odometer),
        "Notes": notes,
        "Logged By": st.session_state.get("role", "Unknown")
    }
    
    table.create(new_record)
    st.toast("✅ Service record saved to Airtable!")

def delete_last_row():
    records = table.all(sort=["-createdTime"])
    if records:
        table.delete(records[0]["id"])
        st.toast("🗑️ Last entry deleted!")

# --- 4. UI LAYOUT ---
st.title("🛢️ Oil & Servicing Log")
st.divider()

col1, col2 = st.columns(2)
with col1:
    st.selectbox("Select Truck", [""] + LIST_OF_TRUCKS, key="os_truck")
    st.selectbox("Service Type", ["Oil Change", "Filter Replacement", "Full Service", "Tyre Replacement"], key="os_type")
with col2:
    st.text_input("Odometer Reading (km)", key="os_odo")
    st.text_input("Mechanic Notes", key="os_notes")

st.button("💾 Submit Service Record", use_container_width=True, on_click=save_service_entry, type="primary")

# --- 5. SUBMITTED LOGS ---
st.divider()
st.subheader("📋 Historical Service Records")

live_records = table.all(sort=["-createdTime"])

if live_records:
    # Extract data and keep the Airtable ID hidden for deletion logic
    flat_data = []
    for r in live_records:
        row = r.get("fields", {})
        row["id"] = r["id"]
        flat_data.append(row)
        
    df_history = pd.DataFrame(flat_data)
    cols_to_show = ["Date", "Truck", "Service Type", "Odometer", "Notes", "Logged By", "id"]
    existing_cols = [c for c in cols_to_show if c in df_history.columns]
    
    # Hide the 'id' column from the user
    edited_df = st.data_editor(
        df_history[existing_cols], 
        use_container_width=True, 
        num_rows="dynamic", 
        hide_index=True,
        column_config={"id": None}
    )
    
    # Airtable Sync: If a row is deleted manually in the table
    if len(edited_df) < len(df_history):
        deleted_ids = set(df_history["id"]) - set(edited_df["id"])
        for del_id in deleted_ids:
            table.delete(del_id)
        st.toast("🗑️ Record permanently deleted from Airtable!")
        st.rerun()

if st.button("⬅️ Undo/Delete Last Entry", use_container_width=True):
    delete_last_row()
    st.rerun()
