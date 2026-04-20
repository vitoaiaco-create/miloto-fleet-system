import streamlit as st
import pandas as pd
from pyairtable import Api
from datetime import datetime

# --- 1. AIRTABLE CONNECTION ---
api = Api(st.secrets["AIRTABLE_TOKEN"])
table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Logistics Trips")

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
def save_trip_entry():
    truck = st.session_state.log_truck
    destination = st.session_state.log_dest
    cargo = st.session_state.log_cargo
    driver = st.session_state.log_driver
    status = st.session_state.log_status
    
    if not truck:
        st.error("⚠️ Please select a truck.")
        return

    new_record = {
        "Date": datetime.today().strftime("%Y-%m-%d"),
        "Truck": truck,
        "Destination": destination,
        "Cargo Weight": str(cargo),
        "Driver": driver,
        "Status": status,
        "Logged By": st.session_state.get("role", "Unknown")
    }
    
    try:
        table.create(new_record)
        st.toast("✅ Trip dispatched and saved!")
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")

def delete_last_row():
    try:
        records = table.all()
        if records:
            records.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
            table.delete(records[0]["id"])
            st.toast("🗑️ Last entry deleted!")
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")

# --- 4. UI LAYOUT ---
st.title("🚛 Logistics & Dispatch")
st.divider()

col1, col2 = st.columns(2)
with col1:
    st.selectbox("Select Truck", [""] + LIST_OF_TRUCKS, key="log_truck")
    st.text_input("Destination / Route", key="log_dest")
    st.text_input("Driver Name", key="log_driver")
with col2:
    st.text_input("Cargo Details (e.g., Cement Tons)", key="log_cargo")
    st.selectbox("Trip Status", ["Dispatched", "In Transit", "Delivered", "Delayed"], key="log_status")

st.button("💾 Submit Logistics Trip", use_container_width=True, on_click=save_trip_entry, type="primary")

# --- 5. SUBMITTED LOGS ---
st.divider()
st.subheader("📋 Active & Historical Trips")

try:
    live_records = table.all()
    if live_records:
        live_records.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        
        flat_data = []
        for r in live_records:
            row = r.get("fields", {})
            row["id"] = r["id"]
            flat_data.append(row)
            
        df_history = pd.DataFrame(flat_data)
        cols_to_show = ["Date", "Truck", "Destination", "Cargo Weight", "Driver", "Status", "Logged By", "id"]
        existing_cols = [c for c in cols_to_show if c in df_history.columns]
        
        edited_df = st.data_editor(
            df_history[existing_cols], 
            use_container_width=True, 
            num_rows="dynamic", 
            hide_index=True,
            column_config={"id": None}
        )
        
        if len(edited_df) < len(df_history):
            deleted_ids = set(df_history["id"]) - set(edited_df["id"])
            for del_id in deleted_ids:
                table.delete(del_id)
            st.toast("🗑️ Record deleted!")
            st.rerun()

    if st.button("⬅️ Undo/Delete Last Entry", use_container_width=True):
        delete_last_row()
        st.rerun()

except Exception as e:
    st.error(f"❌ Cannot connect to Airtable. Ensure your table is named exactly 'Logistics Trips'. Error: {e}")
