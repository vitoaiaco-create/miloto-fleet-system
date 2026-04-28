import streamlit as st
import pandas as pd
from pyairtable import Api
from datetime import datetime
import re
import io

# --- 1. AIRTABLE CONNECTIONS ---
api = Api(st.secrets["AIRTABLE_TOKEN"])
pipeline_table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Oil & Servicing")
profiles_table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Truck Profiles")

# --- 2. FLEET SETUP (ALL 127 INCLUDED) ---
def generate_fleet():
    fleet = []
    for i in range(1, 128):
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

# --- 4. AIRTABLE DATA FETCHING (CACHED) ---
@st.cache_data(ttl=60, show_spinner=False)
def fetch_pipeline():
    try:
        records = pipeline_table.all()
        if not records:
            return pd.DataFrame()
        records.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        flat_data = []
        for r in records:
            row = r.get("fields", {})
            row["id"] = r["id"]
            flat_data.append(row)
        df = pd.DataFrame(flat_data)
        expected_cols = ["Date", "Truck", "Status", "Odometer", "Notes", "Logged By"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"❌ Airtable Pipeline Error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_truck_profiles():
    try:
        records = profiles_table.all()
        if not records:
            return pd.DataFrame(columns=["id", "Truck", "Last Sample KM", "Last Sample Date"])
        flat_data = []
        for r in records:
            row = r.get("fields", {})
            row["id"] = r["id"]
            flat_data.append(row)
        return pd.DataFrame(flat_data)
    except Exception as e:
        st.error(f"❌ Airtable Profiles Error: {e}")
        return pd.DataFrame(columns=["id", "Truck", "Last Sample KM", "Last Sample Date"])

# --- 5. LOGIC FUNCTIONS (PIPELINE) ---
def log_new_sample():
    selected_trucks = st.session_state.new_trucks 
    status = st.session_state.new_status
    notes = st.session_state.new_notes
    
    if not selected_trucks:
        st.error("⚠️ Please select at least one truck.")
        return
        
    current_fleet_kms = st.session_state.get("current_fleet_kms", {})
    
    try:
        for truck in selected_trucks:
            truck_odo = int(current_fleet_kms.get(truck, 0))
            pipeline_table.create({
                "Date": datetime.today().strftime("%Y-%m-%d"),
                "Truck": truck,
                "Status": status,
                "Odometer": str(truck_odo) if truck_odo > 0 else "Unknown",
                "Notes": notes,
                "Logged By": st.session_state.get("role", "Unknown")
            })
        st.session_state.new_trucks = []
        st.toast(f"✅ {len(selected_trucks)} truck(s) added to pipeline with Odometers!")
        fetch_pipeline.clear()
    except Exception as e:
        st.error(f"❌ Could not create record: {e}")

def advance_pipeline():
    record_ids = st.session_state.get("upd_records", [])
    new_status = st.session_state.upd_status
    action_notes = st.session_state.upd_notes
    
    record_new_sample = st.session_state.get("upd_new_sample", False)
    sample_date_val = st.session_state.get("upd_sample_date", datetime.today())
    target_d_str = sample_date_val.strftime("%Y-%m-%d")
    
    if not record_ids:
        st.error("⚠️ Select at least one truck from the checklist to advance.")
        return
        
    try:
        df_pipe = fetch_pipeline()
        
        for rec_id in record_ids:
            truck_name = df_pipe.loc[df_pipe['id'] == rec_id, 'Truck'].values[0] if not df_pipe.empty else None

            # 1. Update the Pipeline Status
            update_data = {
                "Status": new_status, 
                "Date": datetime.today().strftime("%Y-%m-%d"),
                "Logged By": st.session_state.get("role", "Unknown")
            }
            if action_notes:
                update_data["Notes"] = action_notes
            pipeline_table.update(rec_id, update_data)

            # 2. Automate the Last Sample KM Profile Update
            if record_new_sample and truck_name:
                fleet_history = st.session_state.get("fleet_history_kms", {})
                truck_history = fleet_history.get(truck_name, {})
                current_km = 0
                
                if target_d_str in truck_history:
                    current_km = truck_history[target_d_str]
                else:
                    history_dates = []
                    for d_str, km in truck_history.items():
                        try:
                            dt = pd.to_datetime(d_str, errors="coerce")
                            if pd.notna(dt): history_dates.append((dt, km))
                        except: pass
                    
                    if history_dates:
                        closest = min(history_dates, key=lambda x: abs((x[0] - pd.to_datetime(sample_date_val)).days))
                        current_km = closest[1]
                
                if current_km > 0:
                    profiles_df = fetch_truck_profiles()
                    existing_profile = profiles_df[profiles_df['Truck'] == truck_name] if not profiles_df.empty else pd.DataFrame()
                    
                    if not existing_profile.empty:
                        prof_id = existing_profile.iloc[0]['id']
                        profiles_table.update(prof_id, {"Last Sample KM": int(current_km), "Last Sample Date": target_d_str})
                    else:
                        profiles_table.create({"Truck": truck_name, "Last Sample KM": int(current_km), "Last Sample Date": target_d_str})
                        
        st.toast(f"✅ {len(record_ids)} Truck(s) advanced successfully!")
        
        # Clear Caches
        fetch_pipeline.clear()
        fetch_truck_profiles.clear()
        process_analytics.clear() # Clear analytics cache so the pipeline interception triggers instantly

    except Exception as e:
        st.error(f"❌ Update failed: {e}")

def delete_last_row():
    try:
        records = pipeline_table.all()
        if records:
            records.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
            pipeline_table.delete(records[0]["id"])
            st.toast("🗑️ Last entry deleted!")
            fetch_pipeline.clear()
            process_analytics.clear()
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")

# --- 6. FILE PARSING & ANALYTICS ENGINE (CACHED) ---
@st.cache_data(show_spinner=False)
def parse_files(oil_bytes, oil_name, mileage_bytes, mileage_name):
    df_oil = pd.read_csv(io.BytesIO(oil_bytes)) if oil_name.endswith('.csv') else pd.read_excel(io.BytesIO(oil_bytes))
    df_mileage = pd.read_csv(io.BytesIO(mileage_bytes)) if mileage_name.endswith('.csv') else pd.read_excel(io.BytesIO(mileage_bytes))
    return df_oil, df_mileage

@st.cache_data(show_spinner=False)
def process_analytics(df_oil, df_mileage, df_samples, df_pipeline):
    results = []
    
    # NEW INTERCEPTOR: Get list of active trucks in the pipeline (Banks 1-4)
    active_pipeline_trucks = []
    if not df_pipeline.empty:
        active_pipeline_trucks = df_pipeline[df_pipeline["Status"] != BANKS[4]]["Truck"].tolist()
    
    dates_array = [str(col) for col in df_mileage.columns]
    has_real_dates = any(re.search(r'202\d-', d) for d in dates_array)
    
    if not has_real_dates:
        for i in range(min(5, len(df_mileage))):
            row_vals = [str(x) for x in df_mileage.iloc[i]]
            if any(re.search(r'202\d-', val) for val in row_vals):
                dates_array = row_vals
                break
                
    global_parsed_dates = {}
    for d in dates_array:
        d_str = str(d).strip()
        if re.search(r'202\d-', d_str):
            parsed = pd.to_datetime(d_str, errors="coerce")
            if pd.notna(parsed):
                global_parsed_dates[d_str] = parsed

    df_mileage_str = df_mileage.astype(str)
    
    fleet_historical_kms = {}
    fleet_latest_kms = {}

    for truck in LIST_OF_TRUCKS:
        mtl_code = truck.split("(")[1].replace(")", "") 
        
        mask_mileage = df_mileage_str.apply(lambda col: col.str.contains(mtl_code, na=False, regex=False)).any(axis=1)
        truck_row = df_mileage[mask_mileage]
        
        latest_km = 0
        truck_km_history = {}
        parsed_history_dates = [] 
        
        if not truck_row.empty:
            row_data = [str(x).replace(",", "").strip() for x in truck_row.iloc[0]]
            numeric_vals = []
            for val in row_data:
                try:
                    num = float(val)
                    if pd.notna(num): numeric_vals.append(num)
                except: pass
                    
            latest_km = max(numeric_vals) if numeric_vals else 0
            fleet_latest_kms[truck] = latest_km
            
            for idx, val in enumerate(row_data):
                if idx < len(dates_array):
                    d_str = str(dates_array[idx]).strip()
                    if d_str in global_parsed_dates:
                        try:
                            km_val = float(val)
                            if pd.notna(km_val): 
                                truck_km_history[d_str] = km_val
                                parsed_history_dates.append((global_parsed_dates[d_str], km_val))
                        except: pass
        
        fleet_historical_kms[truck] = truck_km_history
                            
        sample_km = 0
        if not df_samples.empty and "Truck" in df_samples.columns:
            mask_samples = df_samples["Truck"].apply(lambda x: mtl_code in str(x))
            sample_row = df_samples[mask_samples]
            if not sample_row.empty:
                try:
                    sample_km = float(sample_row.iloc[0].get("Last Sample KM", 0))
                    if pd.isna(sample_km): sample_km = 0
                except:
                    sample_km = 0
            
        replenish_km = 0
        if "Identity No" in df_oil.columns:
            mask_oil = df_oil["Identity No"].apply(lambda x: mtl_code in str(x))
            truck_oil = df_oil[mask_oil]
            
            for _, row in truck_oil.iterrows():
                mat = str(row.get("Material Name", ""))
                try: qty = float(row.get("Quantity", 0))
                except: qty = 0
                    
                outward_date_raw = str(row.get("Outward Date", "")).strip()
                
                is_full = False
                if "15W40" in mat and qty >= 40: is_full = True
                elif "80W90" in mat and qty >= 20: is_full = True
                elif "85W140" in mat and qty in [22, 26, 48]: is_full = True
                
                if is_full and outward_date_raw and outward_date_raw.lower() != 'nan':
                    try:
                        parsed_date = pd.to_datetime(outward_date_raw, format="%d-%m-%Y", errors="coerce")
                        if pd.isna(parsed_date): parsed_date = pd.to_datetime(outward_date_raw, errors="coerce")
                            
                        if pd.notna(parsed_date):
                            target_d_str = parsed_date.strftime("%Y-%m-%d")
                            found_km = 0
                            
                            if target_d_str in truck_km_history: 
                                found_km = truck_km_history[target_d_str]
                            else:
                                if parsed_history_dates:
                                    closest = min(parsed_history_dates, key=lambda x: abs((x[0] - parsed_date).days))
                                    found_km = closest[1]
                                    
                            if found_km > replenish_km: replenish_km = found_km
                    except: pass
                        
        starting_km = max(sample_km, replenish_km)
        running_km = latest_km - starting_km
        if running_km < 0: running_km = 0 
        
        status = "⚪ No Baseline Data"
        
        # --- THE INTERCEPTOR LOGIC ---
        if truck in active_pipeline_trucks:
            status = "🔄 In Pipeline"
        elif starting_km > 0: 
            if running_km >= 12000: status = "🔴 Overdue"
            elif running_km >= 10000: status = "🟡 Due Soon"
            else: status = "🟢 Healthy"
            
        results.append({
            "Truck": truck,
            "Latest Odo": int(latest_km),
            "Starting KM": int(starting_km),
            "Running KM": int(running_km),
            "Health": status
        })
    
    return pd.DataFrame(results), fleet_historical_kms, fleet_latest_kms

# --- 7. UI LAYOUT ---
st.title("🛢️ Condition-Based Oil Analysis System")
st.divider()

# --- FETCH LIVE PIPELINE BEFORE ANALYTICS ---
# We fetch this first so the Analytics engine knows who is already being processed
df_pipeline = fetch_pipeline()

# --- PART A: FLEET HEALTH DASHBOARDS ---
st.subheader("📈 1. Fleet Health Analytics & Forecasting")
st.markdown("Upload your two core tracking files. *Trucks actively in the pipeline are automatically hidden from the Overdue list to prevent double-booking.*")

c1, c2 = st.columns(2)
with c1: file_oil = st.file_uploader("Oil Top-ups & Servicing", type=['csv', 'xlsx'])
with c2: file_mileage = st.file_uploader("Miloto Mileage", type=['csv', 'xlsx'])

if file_oil and file_mileage:
    with st.spinner("Crunching data and syncing with Airtable..."):
        try:
            df_oil, df_mileage = parse_files(file_oil.getvalue(), file_oil.name, file_mileage.getvalue(), file_mileage.name)
            df_samples = fetch_truck_profiles()
            
            # Pass the df_pipeline into process_analytics so it intercepts active trucks
            health_df, hist_kms, latest_kms = process_analytics(df_oil, df_mileage, df_samples, df_pipeline)
            
            st.session_state.fleet_history_kms = hist_kms
            st.session_state.current_fleet_kms = latest_kms
            
            st.success("✅ Fleet Health Calculated!")
            
            # Added the 4th Tab for visibility
            t_over, t_soon, t_health, t_pipe = st.tabs(["🔴 Overdue (12,000+)", "🟡 Due Soon (10k - 12k)", "🟢 Healthy (< 10k)", "🔄 In Pipeline"])
            
            with t_over: st.dataframe(health_df[health_df["Health"] == "🔴 Overdue"], use_container_width=True, hide_index=True)
            with t_soon: st.dataframe(health_df[health_df["Health"] == "🟡 Due Soon"], use_container_width=True, hide_index=True)
            with t_health: st.dataframe(health_df[health_df["Health"] == "🟢 Healthy"], use_container_width=True, hide_index=True)
            with t_pipe: st.dataframe(health_df[health_df["Health"] == "🔄 In Pipeline"], use_container_width=True, hide_index=True)
                
        except Exception as e:
            st.error(f"❌ Error processing files. Details: {e}")

st.divider()

# --- PART B: ENTRY POINT (BULK SELECT) ---
st.subheader("📥 2. Log New Sample Requirement")
col1, col2 = st.columns(2)
with col1:
    st.multiselect("Select Trucks (Bulk Entry)", LIST_OF_TRUCKS, key="new_trucks")
    st.selectbox("Initial Status", BANKS[:2], key="new_status")
with col2:
    st.text_input("Initial Notes (Optional)", key="new_notes")
    st.write("") 
    st.button("💾 Enter into Pipeline", use_container_width=True, on_click=log_new_sample, type="primary")

st.divider()

# --- PART C: PIPELINE MANAGER (BULK UPGRADE) ---
st.subheader("🔄 3. Advance Truck(s) in Pipeline")
st.caption("Select a bank, check the trucks you want to move, and advance them in bulk.")

if not df_pipeline.empty:
    active_df = df_pipeline[df_pipeline["Status"] != BANKS[4]]
    
    if not active_df.empty:
        current_bank_filter = st.selectbox("1. Filter by Current Status (Bank)", BANKS[:4], key="filter_bank")
        df_filtered = active_df[active_df["Status"] == current_bank_filter].copy()
        
        if not df_filtered.empty:
            df_filtered.insert(0, "Select", False)
            cols_to_show = ["Select", "Date", "Truck", "Odometer", "Notes", "Logged By", "id"]
            existing_cols = [c for c in cols_to_show if c in df_filtered.columns]
            
            edited_advance_df = st.data_editor(
                df_filtered[existing_cols], 
                use_container_width=True, 
                hide_index=True,
                key="editor_advance",
                column_config={"id": None, "Select": st.column_config.CheckboxColumn("Select", default=False)},
                disabled=["Date", "Truck", "Odometer", "Notes", "Logged By"]
            )
            
            selected_ids = edited_advance_df[edited_advance_df["Select"] == True]["id"].tolist()
            st.session_state.upd_records = selected_ids
            
            st.write("---")
            
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                next_idx = min(BANKS.index(current_bank_filter) + 1, 4)
                st.selectbox("2. Advance Selected Trucks To", BANKS, index=next_idx, key="upd_status")
                
                st.write("")
                record_new_sample = st.checkbox("♻️ Record New Sample (Updates Baseline KM)", key="upd_new_sample")
                if record_new_sample:
                    st.date_input("Select Date Sample Was Drawn", datetime.today(), key="upd_sample_date")
                    
            with m_col2:
                st.text_area("Lab Results / Notes to Append", height=130, key="upd_notes")
                
            st.button(
                f"🚀 Advance {len(selected_ids)} Selected Truck(s)", 
                use_container_width=True, 
                on_click=advance_pipeline, 
                type="primary"
            )
        else:
            st.info(f"No trucks currently sitting in: {current_bank_filter}.")
    else:
        st.info("No active trucks in the pipeline to advance.")
else:
    st.info("Pipeline is currently empty.")

st.divider()

# --- PART D: THE 5 BANKS DASHBOARD ---
st.subheader("📊 4. Pipeline Dashboard (The 5 Banks)")

if not df_pipeline.empty:
    tabs = st.tabs(["1️⃣ Due for Coll.", "2️⃣ Pend. Dispatch", "3️⃣ Sent to Lab", "4️⃣ Pend. Interv.", "5️⃣ Completed"])
    cols_to_show = ["Select", "Date", "Truck", "Odometer", "Notes", "Logged By", "id"]
    
    for i, bank_name in enumerate(BANKS):
        with tabs[i]:
            df_bank = df_pipeline[df_pipeline["Status"] == bank_name].copy()
            if not df_bank.empty:
                df_bank.insert(0, "Select", False)
                existing_cols = [c for c in cols_to_show if c in df_bank.columns]
                
                edited_df = st.data_editor(
                    df_bank[existing_cols], 
                    use_container_width=True, 
                    hide_index=True,
                    key=f"editor_delete_{i}",
                    column_config={"id": None, "Select": st.column_config.CheckboxColumn("Select", default=False)},
                    disabled=["Date", "Truck", "Odometer", "Notes", "Logged By"]
                )
                
                selected_ids = edited_df[edited_df["Select"] == True]["id"].tolist()
                if len(selected_ids) > 0:
                    if st.button(f"🗑️ Delete {len(selected_ids)} Selected Log(s)", key=f"del_btn_{i}", type="primary"):
                        for del_id in selected_ids:
                            pipeline_table.delete(del_id)
                        st.success("✅ Log(s) permanently deleted!")
                        fetch_pipeline.clear()
                        process_analytics.clear()
                        st.rerun()
            else:
                st.write(f"No trucks currently in *{bank_name}*.")

st.write("")
if st.button("⬅️ Undo/Delete Last Entry Globally", use_container_width=True):
    delete_last_row()
    st.rerun()
