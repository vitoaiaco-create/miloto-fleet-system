import streamlit as st
import pandas as pd
from pyairtable import Api
from datetime import datetime

# --- 1. AIRTABLE CONNECTION ---
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
    logged_by = st.session_state.get("role", "Unknown")
    
    try:
        records = table.all()
        for truck in selected:
            existing_record_id = None
            for r in records:
                fields = r.get("fields", {})
                if fields.get("Date") == date_str and fields.get("Trucks") == truck:
                    existing_record_id = r.get("id")
                    break
                    
            status_val = "Provisional" if "Morning" in shift_type else "Final"

            if existing_record_id and shift_type == "Evening (Final)":
                table.update(existing_record_id, {"Status": "Final", "Logged By": logged_by})
            elif not existing_record_id:
                table.create({"Date": date_str, "Trucks": truck, "Status": status_val, "Logged By": logged_by})

        st.session_state.truck_selector = []
        st.success("✅ Logs submitted successfully!")
    except Exception as e:
        st.error(f"❌ Airtable Error: Could not save. Please check your Table Name and Token. Details: {e}")

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
st.title("🛠️ Workshop & Downtime Log")
st.divider()

col1, col2 = st.columns(2)
with col1:
    st.date_input("Date", datetime.today(), key="date_holder")
with col2:
    st.selectbox("Shift", ["Morning (Provisional)", "Evening (Final)"], key="shift_holder")

st.multiselect("Select Trucks", LIST_OF_TRUCKS, key="truck_selector")
st.button("💾 Submit Logs", use_container_width=True, on_click=save_entry, type="primary")

# --- 5. SUBMITTED LOGS (UPGRADED UI) ---
st.divider()
st.subheader("📋 Submitted Logs")
st.caption("Check the box next to any log to select it for deletion.")

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
        
        # Insert the Checkbox column at the very front
        df_history.insert(0, "Select", False)
        
        cols_to_show = ["Select", "Date", "Trucks", "Status", "Logged By", "id"]
        existing_cols = [c for c in cols_to_show if c in df_history.columns]
        
        # Display the table with only the Select column being editable
        edited_df = st.data_editor(
            df_history[existing_cols], 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "id": None, # Hide the Airtable ID
                "Select": st.column_config.CheckboxColumn("Select", default=False)
            },
            disabled=["Date", "Trucks", "Status", "Logged By"] # Lock the text so it can't be messed up
        )
        
        # Check if any boxes were ticked
        selected_ids = edited_df[edited_df["Select"] == True]["id"].tolist()
        
        # If a box is checked, reveal the Delete Button!
        if len(selected_ids) > 0:
            if st.button(f"🗑️ Delete {len(selected_ids)} Selected Log(s)", type="primary", use_container_width=True):
                for del_id in selected_ids:
                    table.delete(del_id)
                st.success("✅ Logs permanently deleted!")
                st.rerun()

    st.write("") # Add a little space
    if st.button("⬅️ Undo/Delete Last Entry", use_container_width=True):
        delete_last_row()
        st.rerun()

except Exception as e:
    st.error(f"❌ Cannot connect to Airtable. Ensure your table is named exactly 'Workshop Logs'. Error: {e}")
