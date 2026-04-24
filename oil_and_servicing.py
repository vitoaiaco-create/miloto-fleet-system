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

# --- 4. DATA FETCHING ---
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
        return pd.DataFrame(flat_data)
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")
        return pd.DataFrame()

# --- 5. LOGIC FUNCTIONS ---
def log_new_sample():
    truck = st.session_state.new_truck
    status = st.session_state.new_status
    notes = st.session_state.new_notes
    
    if not truck:
        st.error("⚠️ Please select a truck.")
        return

    try:
        table.create({
            "Date": datetime.today().strftime("%Y-%m-%d"),
            "Truck": truck,
            "Status": status,
            "Notes": notes,
            "Logged By": st.session_state.get("role", "Unknown")
        })
        st.toast("✅ Added to oil analysis pipeline!")
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
            "Date": datetime.today().strftime("%Y-%m-%d"), # Updates date to when it moved banks
            "Logged By": st.session_state.get("role", "Unknown")
        }
        if action_notes:
            update_data["Notes"] = action_notes

        table.update(record_id, update_data)
        st.toast("✅ Truck advanced to new bank!")
    except Exception as e:
        st.error(f"❌ Update failed: {e}")

# --- 6. UI LAYOUT ---
st.title("🛢️ Condition-Based Oil Analysis Pipeline")
st.divider()

# --- ENTRY POINT: LOG NEW SAMPLE ---
st.subheader("📥 1. Log New Sample Requirement")
col1, col2 = st.columns(2)
with col1:
    st.selectbox("Select Truck", [""] + LIST_OF_TRUCKS, key="new_truck")
    # Only allow entering at Bank 1 or 2
    st.selectbox("Initial Status", BANKS[:2], key="new_status")
with col2:
    st.text_input("Initial Notes (Optional)", key="new_notes")
    st.write("") # Spacing
    st.button("💾 Enter into Pipeline", use_container_width=True, on_click=log_new_sample, type="primary")

st.divider()

# Fetch data for the rest of the app
df_pipeline = fetch_pipeline()

# --- PIPELINE MANAGER: MOVE TRUCKS ---
st.subheader("🔄 2. Advance Truck in Pipeline")
st.caption("Update a truck's status when lab results arrive or interventions are completed.")

if not df_pipeline.empty:
    # Filter only active trucks (not in Bank 5)
    active_df = df_pipeline[df_pipeline["Status"] != BANKS[4]]
    
    if not active_df.empty:
        # Create a dictionary to map Airtable ID to a readable label: "MILOTO-01 - 3. Sent to Lab"
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

# --- THE 5 BANKS DASHBOARD ---
st.subheader("📊 3. Pipeline Dashboard (The 5 Banks)")

if not df_pipeline.empty:
    # Create the visual tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1️⃣ Due for Collection", 
        "2️⃣ Pending Dispatch", 
        "3️⃣ Sent to Lab", 
        "4️⃣ Pending Intervention", 
        "5️⃣ Completed"
    ])
    
    tabs = [tab1, tab2, tab3, tab4, tab5]
    cols_to_show = ["Date", "Truck", "Notes", "Logged By"]
    
    # Loop through the 5 banks and place the right trucks into the right tabs
    for i, bank_name in enumerate(BANKS):
        with tabs[i]:
            df_bank = df_pipeline[df_pipeline["Status"] == bank_name]
            if not df_bank.empty:
                existing_cols = [c for c in cols_to_show if c in df_bank.columns]
                st.dataframe(df_bank[existing_cols], use_container_width=True, hide_index=True)
            else:
                st.write(f"No trucks currently in *{bank_name}*.")
