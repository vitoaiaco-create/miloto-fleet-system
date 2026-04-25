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

# --- 3. THE 5 BANKS (STATUSES) ---
BANKS = [
    "1. Due for Collection",
    "2. Pending Dispatch to Lab",
    "3. Sent to Lab (Pending Results)",
    "4. Results Received (Pending Intervention)",
    "5. Completed Interventions"
]

# --- 4. DATA FETCHING (WITH DEFENSIVE COLUMNS) ---
def fetch_pipeline():
    try:
        records = table.all()
        if not records:
            return pd.DataFrame()
            
        records.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        flat_data = []
        for r in records:
            row = r.get("fields", {})
            row["id"] = r["id"]
            flat_data.append(row)
            
        df = pd.DataFrame(flat_data)
        
        # Guarantee critical columns exist to prevent KeyError
        expected_cols = ["Date", "Truck", "Status", "Notes", "Logged By"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
                
        return df
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")
        return pd.DataFrame()

# --- 5. LOGIC FUNCTIONS ---
def log_new_sample():
    # Now expects a list of trucks from multiselect
    selected_trucks = st.session_state.new_trucks 
    status = st.session_state.new_status
    notes = st.session_state.new_notes
    
    if not selected_trucks:
        st.error("⚠️ Please select at least one truck.")
        return

    try:
        # Loop through and create a record for every selected truck
        for truck in selected_trucks:
            table.create({
                "Date": datetime.today().strftime("%Y-%m-%d"),
                "Truck": truck,
                "Status": status,
                "Notes": notes,
                "Logged By": st.session_state.get("role", "Unknown")
            })
            
        # Clear the multiselect box after successful entry
        st.session_state.new_trucks = []
        st.toast(f"✅ {len(selected_trucks)} truck(s) added to pipeline!")
    except Exception as e:
        st.error(f"❌ Could not create record: {e}")

def advance_pipeline():
    record_id = st.session_state.upd_record
    new_status = st.session_state.upd_status
    action_notes = st.session_state.upd_notes

    if not record_id:
        st.error("⚠️ Select a truck from the active pipeline to update.")
        return

    try:
        update_data = {
            "Status": new_status, 
            "Date": datetime.today().strftime("%Y-%m-%d"),
            "Logged By": st.session_state.get("role", "Unknown")
        }
        if action_notes:
            update_data["Notes"] = action_notes

        table.update(record_id, update_data)
        st.toast("✅ Truck advanced to new bank!")
    except Exception as e:
        st.error(f"❌ Update failed: {e}")

def delete_last_row():
    try:
        records = table.all()
        if records:
            records.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
            table.delete(records[0]["id"])
            st.toast("🗑️ Last entry deleted!")
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")

# --- 6. UI LAYOUT ---
st.title("🛢️ Condition-Based Oil Analysis Pipeline")
st.divider()

# --- ENTRY POINT: LOG NEW SAMPLE (BULK SELECT) ---
st.subheader("📥 1. Log New Sample Requirement")
col1, col2 = st.columns(2)
with col1:
    # Upgraded to Multiselect
    st.multiselect("Select Trucks (Bulk Entry)", LIST_OF_TRUCKS, key="new_trucks")
    st.selectbox("Initial Status", BANKS[:2], key="new_status")
with col2:
    st.text_input("Initial Notes (Optional)", key="new_notes")
    st.write("") 
    st.button("💾 Enter into Pipeline", use_container_width=True, on_click=log_new_sample, type="primary")

st.divider()

df_pipeline = fetch_pipeline()

# --- PIPELINE MANAGER: MOVE TRUCKS ---
st.subheader("🔄 2. Advance Truck in Pipeline")
st.caption("Update a truck's status when lab results arrive or interventions are completed.")

if not df_pipeline.empty:
    active_df = df_pipeline[df_pipeline["Status"] != BANKS[4]]
    
    if not active_df.empty:
        record_options = {row["id"]: f"{row['Truck']} ➔ {row['Status']}" for _, row in active_df.iterrows()}
        
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.selectbox(
                "Select Active Truck", 
                options=[""] + list(record_options.keys()), 
                format_func=lambda x: record_options.get(x, ""), 
                key="upd_record"
            )
            st.selectbox("Advance to New Bank", BANKS, index=2, key="upd_status")
        with m_col2:
            st.text_area("Lab Results / Intervention Notes to Append", height=110, key="upd_notes")
            
        st.button("🚀 Advance Status", use_container_width=True, on_click=advance_pipeline)
    else:
        st.info("No active trucks in the pipeline to advance.")
else:
    st.info("Pipeline is currently empty.")

st.divider()

# --- THE 5 BANKS DASHBOARD (WITH SELECT & DELETE) ---
st.subheader("📊 3. Pipeline Dashboard (The 5 Banks)")
st.caption("To fix mistakes: check the box next to a log in any tab to select it for deletion.")

if not df_pipeline.empty:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1️⃣ Due for Collection", 
        "2️⃣ Pending Dispatch", 
        "3️⃣ Sent to Lab", 
        "4️⃣ Pending Intervention", 
        "5️⃣ Completed"
    ])
    
    tabs = [tab1, tab2, tab3, tab4, tab5]
    cols_to_show = ["Select", "Date", "Truck", "Notes", "Logged By", "id"]
    
    for i, bank_name in enumerate(BANKS):
        with tabs[i]:
            df_bank = df_pipeline[df_pipeline["Status"] == bank_name].copy()
            
            if not df_bank.empty:
                # Insert Checkbox Column
                df_bank.insert(0, "Select", False)
                existing_cols = [c for c in cols_to_show if c in df_bank.columns]
                
                # Editable DataFrame for Deletion
                edited_df = st.data_editor(
                    df_bank[existing_cols], 
                    use_container_width=True, 
                    hide_index=True,
                    key=f"editor_{i}", # Unique key for each tab
                    column_config={
                        "id": None, 
                        "Select": st.column_config.CheckboxColumn("Select", default=False)
                    },
                    disabled=["Date", "Truck", "Notes", "Logged By"] # Prevent accidental text edits
                )
                
                # Deletion Logic
                selected_ids = edited_df[edited_df["Select"] == True]["id"].tolist()
                
                if len(selected_ids) > 0:
                    if st.button(f"🗑️ Delete {len(selected_ids)} Selected Log(s)", key=f"del_btn_{i}", type="primary"):
                        for del_id in selected_ids:
                            table.delete(del_id)
                        st.success("✅ Log(s) permanently deleted!")
                        st.rerun()
            else:
                st.write(f"No trucks currently in *{bank_name}*.")

# Global Undo Button
st.write("")
st.write("")
if st.button("⬅️ Undo/Delete Last Entry Globally", use_container_width=True):
    delete_last_row()
    st.rerun()
