import streamlit as st
import pandas as pd
from pyairtable import Api
from datetime import datetime
import re

# --- 1. AIRTABLE CONNECTION ---
api = Api(st.secrets["AIRTABLE_TOKEN"])
table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Oil & Servicing")

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

# --- 4. AIRTABLE DATA FETCHING ---
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
        expected_cols = ["Date", "Truck", "Status", "Notes", "Logged By"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"❌ Airtable Error: {e}")
        return pd.DataFrame()

# --- 5. LOGIC FUNCTIONS (PIPELINE) ---
def log_new_sample():
    selected_trucks = st.session_state.new_trucks 
    status = st.session_state.new_status
    notes = st.session_state.new_notes
    if not selected_trucks:
        st.error("⚠️ Please select at least one truck.")
        return
    try:
        for truck in selected_trucks:
            table.create({
                "Date": datetime.today().strftime("%Y-%m-%d"),
                "Truck": truck,
                "Status": status,
                "Notes": notes,
                "Logged By": st.session_state.get("role", "Unknown")
            })
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

# --- 6. ANALYTICS ENGINE (THE TWO CLOCKS) ---
def process_analytics(df_oil, df_mileage, df_samples):
    results = []
    
    # 1. Extract Dates array from Mileage File securely using REGEX
    dates_array = []
    for col in df_mileage.columns:
        dates_array.append(str(col))
        
    has_real_dates = any(re.search(r'202\d-', d) for d in dates_array)
    
    if not has_real_dates:
        # Scan the first 5 rows to find the true dates header
        for i in range(min(5, len(df_mileage))):
            row_vals = df_mileage.iloc[i].astype(str).tolist()
            if any(re.search(r'202\d-', val) for val in row_vals):
                dates_array = row_vals
                break
                
    for truck in LIST_OF_TRUCKS:
        mtl_code = truck.split("(")[1].replace(")", "") # e.g. MTL01
        
        # 2. Get Mileage History & Latest KM
        truck_row = df_mileage[df_mileage.apply(lambda r: r.astype(str).str.contains(mtl_code).any(), axis=1)]
        latest_km = 0
        truck_km_history = {}
        
        if not truck_row.empty:
            row_data = truck_row.iloc[0].astype(str).str.replace(",", "")
            numeric_vals = pd.to_numeric(row_data, errors='coerce').dropna()
            latest_km = numeric_vals.max() if not numeric_vals.empty else 0
            
            for idx, val in enumerate(row_data):
                if idx < len(dates_array):
                    d_str = str(dates_array[idx]).strip()
                    if re.search(r'202\d-', d_str):
                        km_val = pd.to_numeric(val, errors='coerce')
                        if pd.notna(km_val):
                            truck_km_history[d_str] = km_val
                            
        # 3. Get Last Sample KM (Clock B)
        sample_km = 0
        sample_row = df_samples[df_samples.iloc[:, 0].astype(str).str.contains(mtl_code, na=False)]
        if not sample_row.empty:
            sample_km = pd.to_numeric(sample_row.iloc[0, 1], errors='coerce')
            if pd.isna(sample_km): sample_km = 0
            
        # 4. Check for Full Replenishment (Clock A)
        replenish_km = 0
        truck_oil = df_oil[df_oil["Identity No"].astype(str).str.contains(mtl_code, na=False)]
        
        for _, row in truck_oil.iterrows():
            mat = str(row.get("Material Name", ""))
            qty = pd.to_numeric(row.get("Quantity", 0), errors='coerce')
            outward_date_raw = str(row.get("Outward Date", "")).strip()
            
            is_full = False
            if "15W40" in mat and qty >= 40: is_full = True
            elif "80W90" in mat and qty >= 20: is_full = True
            elif "85W140" in mat and qty in [22, 26, 48]: is_full = True
            
            if is_full and outward_date_raw:
                try:
                    parsed_date = pd.to_datetime(outward_date_raw, format="%d-%m-%Y", errors="coerce")
                    if pd.isna(parsed_date):
                        parsed_date = pd.to_datetime(outward_date_raw, errors="coerce")
                        
                    if pd.notna(parsed_date):
                        target_d_str = parsed_date.strftime("%Y-%m-%d")
                        found_km = 0
                        
                        if target_d_str in truck_km_history:
                            found_km = truck_km_history[target_d_str]
                        else:
                            history_dates = []
                            for d_str, km in truck_km_history.items():
                                try:
                                    dt = pd.to_datetime(d_str, errors="coerce")
                                    if pd.notna(dt): history_dates.append((dt, km))
                                except: pass
                                
                            if history_dates:
                                closest = min(history_dates, key=lambda x: abs((x[0] - parsed_date).days))
                                found_km = closest[1]
                                
                        if found_km > replenish_km:
                            replenish_km = found_km
                except Exception:
                    pass
                    
        # 5. Final Calculation
        starting_km = max(sample_km, replenish_km)
        
        running_km = latest_km - starting_km
        if running_km < 0: running_km = 0 
        
        status = "⚪ No Baseline Data"
        if starting_km > 0: 
            if running_km >= 12000: status = "🔴 Overdue"
            elif running_km >= 10000: status = "🟡 Due Soon"
            else: status = "🟢 Healthy"
            
        results.append({
            "Truck": truck,
            "Latest Odo": latest_km,
            "Starting KM": starting_km,
            "Running KM": running_km,
            "Health": status
        })
        
    return pd.DataFrame(results)

# --- 7. UI LAYOUT ---
st.title("🛢️ Condition-Based Oil Analysis System")
st.divider()

# --- PART A: FLEET HEALTH DASHBOARDS ---
st.subheader("📈 1. Fleet Health Analytics & Forecasting")
st.markdown("Upload the three core files to calculate running KMs and identify trucks needing samples.")

c1, c2, c3 = st.columns(3)
with c1: file_oil = st.file_uploader("Oil Top-ups & Servicing", type=['csv', 'xlsx'])
with c2: file_mileage = st.file_uploader("Miloto Mileage", type=['csv', 'xlsx'])
with c3: file_samples = st.file_uploader("Miloto Last Sample KM", type=['csv', 'xlsx'])

if file_oil and file_mileage and file_samples:
    with st.spinner("Calculating the Two Clocks and Running KMs..."):
        try:
            df_oil = pd.read_csv(file_oil) if file_oil.name.endswith('.csv') else pd.read_excel(file_oil)
            df_mileage = pd.read_csv(file_mileage) if file_mileage.name.endswith('.csv') else pd.read_excel(file_mileage)
            df_samples = pd.read_csv(file_samples) if file_samples.name.endswith('.csv') else pd.read_excel(file_samples)
            
            health_df = process_analytics(df_oil, df_mileage, df_samples)
            
            st.success("✅ Fleet Health Calculated!")
            
            t_over, t_soon, t_health = st.tabs(["🔴 Overdue (12,000+)", "🟡 Due Soon (10k - 12k)", "🟢 Healthy (< 10k)"])
            
            with t_over:
                st.dataframe(health_df[health_df["Health"] == "🔴 Overdue"], use_container_width=True, hide_index=True)
            with t_soon:
                st.dataframe(health_df[health_df["Health"] == "🟡 Due Soon"], use_container_width=True, hide_index=True)
            with t_health:
                st.dataframe(health_df[health_df["Health"] == "🟢 Healthy"], use_container_width=True, hide_index=True)
                
        except Exception as e:
            st.error(f"❌ Error processing files. Please ensure the formats are correct. Details: {e}")

st.divider()

# --- PART B: ENTRY POINT (BULK SELECT) ---
st.subheader("📥 2. Log New Sample Requirement")
st.markdown("Select trucks from the **Overdue** or **Due Soon** lists above and enter them into the Pipeline.")

col1, col2 = st.columns(2)
with col1:
    st.multiselect("Select Trucks (Bulk Entry)", LIST_OF_TRUCKS, key="new_trucks")
    st.selectbox("Initial Status", BANKS[:2], key="new_status")
with col2:
    st.text_input("Initial Notes (Optional)", key="new_notes")
    st.write("") 
    st.button("💾 Enter into Pipeline", use_container_width=True, on_click=log_new_sample, type="primary")

st.divider()

df_pipeline = fetch_pipeline()

# --- PART C: PIPELINE MANAGER ---
st.subheader("🔄 3. Advance Truck in Pipeline")
st.caption("Update a truck's status when lab results arrive or interventions are completed.")

if not df_pipeline.empty:
    active_df = df_pipeline[df_pipeline["Status"] != BANKS[4]]
    if not active_df.empty:
        record_options = {row["id"]: f"{row['Truck']} ➔ {row['Status']}" for _, row in active_df.iterrows()}
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.selectbox("Select Active Truck", options=[""] + list(record_options.keys()), format_func=lambda x: record_options.get(x, ""), key="upd_record")
            st.selectbox("Advance to New Bank", BANKS, index=2, key="upd_status")
        with m_col2:
            st.text_area("Lab Results / Intervention Notes to Append", height=110, key="upd_notes")
        st.button("🚀 Advance Status", use_container_width=True, on_click=advance_pipeline)
    else:
        st.info("No active trucks in the pipeline to advance.")
else:
    st.info("Pipeline is currently empty.")

st.divider()

# --- PART D: THE 5 BANKS DASHBOARD ---
st.subheader("📊 4. Pipeline Dashboard (The 5 Banks)")
st.caption("To fix mistakes: check the box next to a log in any tab to select it for deletion.")

if not df_pipeline.empty:
    tabs = st.tabs(["1️⃣ Due for Coll.", "2️⃣ Pend. Dispatch", "3️⃣ Sent to Lab", "4️⃣ Pend. Interv.", "5️⃣ Completed"])
    cols_to_show = ["Select", "Date", "Truck", "Notes", "Logged By", "id"]
    
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
                    key=f"editor_{i}",
                    column_config={"id": None, "Select": st.column_config.CheckboxColumn("Select", default=False)},
                    disabled=["Date", "Truck", "Notes", "Logged By"]
                )
                
                selected_ids = edited_df[edited_df["Select"] == True]["id"].tolist()
                if len(selected_ids) > 0:
                    if st.button(f"🗑️ Delete {len(selected_ids)} Selected Log(s)", key=f"del_btn_{i}", type="primary"):
                        for del_id in selected_ids:
                            table.delete(del_id)
                        st.success("✅ Log(s) permanently deleted!")
                        st.rerun()
            else:
                st.write(f"No trucks currently in *{bank_name}*.")

st.write("")
if st.button("⬅️ Undo/Delete Last Entry Globally", use_container_width=True):
    delete_last_row()
    st.rerun()
