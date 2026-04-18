import streamlit as st
import pandas as pd
import numpy as np
import re
import os
from datetime import datetime


# --- INITIALIZE DIRECTORIES & LOCAL DATABASE ---
DATA_DIR = "saved_data"
os.makedirs(DATA_DIR, exist_ok=True)

MILEAGE_CACHE = os.path.join(DATA_DIR, "mileage_cache.pkl")
OIL_CACHE = os.path.join(DATA_DIR, "oil_cache.pkl")
SAMPLE_CACHE = os.path.join(DATA_DIR, "sample_cache.pkl")
WORKFLOW_FILE = "Sample_Workflow_Log.csv"

if not os.path.exists(WORKFLOW_FILE):
    df_empty = pd.DataFrame(columns=[
        "Ticket_ID", "Date_Created", "Truck_ID", "Component", "Sample_Mileage",
        "Status", "Lab_Notes", "Required_Intervention", "Mechanic_Action", "Last_Updated"
    ])
    df_empty.to_csv(WORKFLOW_FILE, index=False)

st.title("🚛 Fleet Condition-Based Maintenance Dashboard")

# --- SMART SIDEBAR (With Memory) ---
st.sidebar.header("Data Uploads")
st.sidebar.markdown("*Upload new files to update the system. Leave blank to use saved memory.*")

mileage_file = st.sidebar.file_uploader("1. Daily Mileage (.csv/.xlsx)", type=["csv", "xlsx"])
oil_file = st.sidebar.file_uploader("2. Oil Servicing (.csv/.xlsx)", type=["csv", "xlsx"])
sample_file = st.sidebar.file_uploader("3. Last Sample KM (.csv/.xlsx)", type=["csv", "xlsx"])
interval = st.sidebar.selectbox("Sampling Interval (km)", [10000, 12000], index=0)

st.sidebar.divider()
st.sidebar.markdown("**💾 System Memory Status:**")
st.sidebar.markdown(f"{'✅ Saved' if os.path.exists(MILEAGE_CACHE) else '❌ Missing'} - Daily Mileage")
st.sidebar.markdown(f"{'✅ Saved' if os.path.exists(OIL_CACHE) else '❌ Missing'} - Oil Servicing")
st.sidebar.markdown(f"{'✅ Saved' if os.path.exists(SAMPLE_CACHE) else '❌ Missing'} - Last Sample KM")

# --- DATA HANDLING LOGIC ---
def extract_mtl(val):
    if pd.isna(val): return None
    match = re.search(r'(MTL\d+)', str(val).upper().replace(" ", ""))
    if match: return match.group(1)
    return str(val).upper().replace(" ", "")

def clean_num(val):
    try:
        if pd.isna(val) or val == "Unknown": return "Unknown"
        return int(float(val))
    except: return "Unknown"

def load_and_cache_data(uploaded_file, cache_path, is_mileage=False):
    if uploaded_file is not None:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, header=None if is_mileage else 'infer')
        else:
            df = pd.read_excel(uploaded_file, header=None if is_mileage else 0)
        df.to_pickle(cache_path)
        return df
    elif os.path.exists(cache_path):
        return pd.read_pickle(cache_path)
    return None

df_mil_raw = load_and_cache_data(mileage_file, MILEAGE_CACHE, is_mileage=True)
df_oil_raw = load_and_cache_data(oil_file, OIL_CACHE)
df_sample_raw = load_and_cache_data(sample_file, SAMPLE_CACHE)

if df_mil_raw is not None and df_oil_raw is not None and df_sample_raw is not None:
    with st.spinner("Processing Fleet Data..."):
        try:
            # --- LOAD WORKFLOW DATABASE EARLY FOR MASTER CALCS ---
            df_wf = pd.read_csv(WORKFLOW_FILE)
            if 'Required_Intervention' not in df_wf.columns: df_wf['Required_Intervention'] = "None"
            if 'Sample_Mileage' not in df_wf.columns: df_wf['Sample_Mileage'] = "Unknown"

            # --- PROCESS DATA ---
            df_sample = df_sample_raw.copy()
            df_sample.columns = ['Fleet_No', 'Last_Sample_KM']
            df_sample['Std_ID'] = df_sample['Fleet_No'].astype(str).str.upper().str.replace(" ", "")
            df_sample['Last_Sample_KM'] = pd.to_numeric(df_sample['Last_Sample_KM'], errors='coerce')

            df_mil_copy = df_mil_raw.copy()
            dates_row = df_mil_copy.iloc[1].values[1:]
            trucks_col = df_mil_copy.iloc[3:, 0].values
            mileages = df_mil_copy.iloc[3:, 1:].values
            df_mil = pd.DataFrame(mileages, index=trucks_col, columns=dates_row).reset_index()
            df_mil.rename(columns={'index': 'Std_ID'}, inplace=True)
            df_mil['Std_ID'] = df_mil['Std_ID'].astype(str).str.upper().str.replace(" ", "")
            df_mil_melt = df_mil.melt(id_vars='Std_ID', var_name='Date', value_name='Mileage')
            df_mil_melt['Date'] = pd.to_datetime(df_mil_melt['Date'], errors='coerce')
            df_mil_melt['Mileage'] = pd.to_numeric(df_mil_melt['Mileage'], errors='coerce')
            df_mil_melt = df_mil_melt.dropna(subset=['Date', 'Mileage', 'Std_ID'])
            latest_mileage = df_mil_melt.loc[df_mil_melt.groupby('Std_ID')['Date'].idxmax()][['Std_ID', 'Mileage']]
            latest_mileage.rename(columns={'Mileage': 'Current_Mileage'}, inplace=True)

            df_oil = df_oil_raw.copy()
            df_oil['Std_ID'] = df_oil['Identity No'].apply(extract_mtl)
            df_oil['Date'] = pd.to_datetime(df_oil['Outward Date'], format='%d-%m-%Y', errors='coerce')
            
            def get_comp(row):
                mat = str(row['Material Name'])
                qty = pd.to_numeric(row['Quantity'], errors='coerce')
                if '15W40' in mat and qty >= 40: return 'Engine'
                if '80W90' in mat and qty >= 20: return 'Gearbox'
                if '85W140' in mat and qty >= 22: return 'Differential'
                return None
            
            df_oil['Component'] = df_oil.apply(get_comp, axis=1)
            df_oil_full = df_oil.dropna(subset=['Component', 'Date', 'Std_ID'])
            df_oil_latest = df_oil_full.sort_values('Date').groupby(['Std_ID', 'Component']).tail(1)

            df_mil_melt_renamed = df_mil_melt.rename(columns={'Date': 'Mileage_Date'}).sort_values('Mileage_Date')
            df_oil_latest = df_oil_latest.sort_values('Date')
            merged_oil = pd.merge_asof(df_oil_latest, df_mil_melt_renamed, left_on='Date', right_on='Mileage_Date', by='Std_ID', direction='nearest')

            sampling_results, oil_age_results = [], []
            for truck in latest_mileage['Std_ID'].unique():
                if not truck.startswith('MTL'): continue 
                
                curr_km_raw = latest_mileage[latest_mileage['Std_ID'] == truck]['Current_Mileage'].values[0]
                curr_km = clean_num(curr_km_raw)
                
                sample_km_row = df_sample[df_sample['Std_ID'] == truck]
                base_sample_km = sample_km_row['Last_Sample_KM'].values[0] if not sample_km_row.empty else 0
                
                # --- NEW LOGIC: FIND HIGHEST WORKFLOW MILEAGE FOR THIS TRUCK ---
                wf_engine_tickets = df_wf[(df_wf['Truck_ID'] == truck) & (df_wf['Component'] == 'Engine') & (df_wf['Status'] != '1. Pending Collection')]
                wf_sample_km = 0
                if not wf_engine_tickets.empty:
                    for val in wf_engine_tickets['Sample_Mileage']:
                        c_val = clean_num(val)
                        if c_val != "Unknown" and c_val > wf_sample_km:
                            wf_sample_km = c_val
                
                engine_rep_km = 0
                for comp in ['Engine', 'Gearbox', 'Differential']:
                    rep_row = merged_oil[(merged_oil['Std_ID'] == truck) & (merged_oil['Component'] == comp)]
                    rep_km = rep_row['Mileage'].values[0] if not rep_row.empty else 0
                    if comp == 'Engine': engine_rep_km = rep_km
                    oil_age_raw = curr_km_raw - rep_km if rep_km > 0 else "Unknown"
                    oil_age_results.append({"Truck ID": truck, "Component": comp, "Current KM": curr_km, "Replenishment KM": clean_num(rep_km) if rep_km > 0 else "Unknown", "Oil Age (KM)": clean_num(oil_age_raw)})
                
                # Baseline now tests 3 things: Excel Sample, Oil Issue, and Workflow Tickets!
                calc_baseline = max(base_sample_km, engine_rep_km, wf_sample_km) 
                
                next_sample_raw = calc_baseline + interval if calc_baseline > 0 else "Unknown"
                next_sample = clean_num(next_sample_raw)
                km_to_sample = next_sample - curr_km if next_sample != "Unknown" and curr_km != "Unknown" else "Unknown"
                
                status = "Healthy"
                if km_to_sample != "Unknown":
                    if km_to_sample < 0: status = "🚨 OVERDUE"
                    elif km_to_sample <= 1500: status = "⚠️ DUE SOON"
                    
                sampling_results.append({"Truck ID": truck, "Current KM": curr_km, "Engine Oil Age": clean_num(curr_km_raw - engine_rep_km) if engine_rep_km > 0 else "Unknown", "Next Sample Due": next_sample, "KM to Sample": km_to_sample, "Status": status})
                    
            df_sampling = pd.DataFrame(sampling_results)
            df_oil_age = pd.DataFrame(oil_age_results)
            
            # --- UI TABS ---
            tab1, tab2, tab3 = st.tabs(["🎯 Master Sampling Schedule", "🛢️ Component Oil Age Tracker", "📋 Lab & Workflow Tracker"])
            
            def color_status(val):
                color = '#ff4b4b' if 'OVERDUE' in str(val) else '#ffa500' if 'SOON' in str(val) else '#2ecc71' if 'Healthy' in str(val) else ''
                return f'background-color: {color}; color: white; font-weight: bold;'
            
            with tab1:
                st.subheader("Master Sampling Trigger (Engine Basis)")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total MTL Trucks", len(df_sampling['Truck ID'].unique()))
                col2.metric("🚨 Overdue", len(df_sampling[df_sampling['Status'] == "🚨 OVERDUE"]))
                col3.metric("⚠️ Due Soon", len(df_sampling[df_sampling['Status'] == "⚠️ DUE SOON"]))
                col4.metric("✅ Healthy (Running)", len(df_sampling[df_sampling['Status'] == "Healthy"]))
                st.divider()
                st.dataframe(df_sampling.style.map(color_status, subset=['Status']), use_container_width=True, hide_index=True)
                
            with tab2:
                st.subheader("Total Distance Covered by Current Oil")
                comp_filter = st.selectbox("Filter by Component:", ["All", "Engine", "Gearbox", "Differential"])
                display_df = df_oil_age if comp_filter == "All" else df_oil_age[df_oil_age["Component"] == comp_filter]
                st.dataframe(display_df, use_container_width=True, hide_index=True)

            # --- TAB 3: WORKFLOW TRACKER ---
            with tab3:
                st.header("🔧 Oil Sample & Lab Workflow")
                
                # --- VISUAL KANBAN BOARD ---
                st.markdown("### Active Tickets")
                k1, k2, k3, k4 = st.columns(4)
                
                pend_coll = df_wf[df_wf['Status'] == '1. Pending Collection']
                pend_disp = df_wf[df_wf['Status'] == '2. Pending Lab Dispatch']
                lab_pend = df_wf[df_wf['Status'] == '3. Lab Results Pending']
                mech_int = df_wf[df_wf['Status'] == '4. Pending Intervention']
                
                disp_cols = ['Truck_ID', 'Component', 'Sample_Mileage']
                
                k1.info(f"🚚 To Collect ({len(pend_coll)})")
                k1.dataframe(pend_coll[disp_cols], hide_index=True)
                k2.warning(f"📦 To Dispatch ({len(pend_disp)})")
                k2.dataframe(pend_disp[disp_cols], hide_index=True)
                k3.success(f"🧪 At Lab ({len(lab_pend)})")
                k3.dataframe(lab_pend[disp_cols], hide_index=True)
                k4.error(f"🔧 Action Req ({len(mech_int)})")
                k4.dataframe(mech_int[disp_cols], hide_index=True)

                st.divider()

                # --- SMART DATA ENTRY FORM ---
                colA, colB = st.columns(2)
                
                with colA:
                    st.subheader("➕ Create Bulk Request")
                    with st.form("new_ticket_form"):
                        st.markdown("Select trucks below. Tickets will be created instantly (Mileage will freeze when moving to Dispatch).")
                        selected_trucks = st.multiselect("Tick Fleet Numbers:", df_sampling['Truck ID'].unique())
                        submit_new = st.form_submit_button("Request Bulk Sample Collection")
                        
                        if submit_new:
                            if not selected_trucks:
                                st.warning("⚠️ Please select at least one truck from the list.")
                            else:
                                new_rows = []
                                timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
                                display_time = datetime.now().strftime('%Y-%m-%d %H:%M')
                                
                                for truck in selected_trucks:
                                    for comp in ["Engine", "Gearbox", "Differential"]:
                                        ticket_id = f"TKT-{timestamp_str}-{truck}-{comp[:3].upper()}"
                                        new_rows.append({
                                            "Ticket_ID": ticket_id, "Date_Created": display_time,
                                            "Truck_ID": truck, "Component": comp, "Sample_Mileage": "Unknown", 
                                            "Status": "1. Pending Collection", "Lab_Notes": "None", 
                                            "Required_Intervention": "None", "Mechanic_Action": "None", "Last_Updated": display_time
                                        })
                                        
                                df_wf = pd.concat([df_wf, pd.DataFrame(new_rows)], ignore_index=True)
                                df_wf.to_csv(WORKFLOW_FILE, index=False)
                                st.success(f"✅ Successfully generated {len(new_rows)} collection tickets!")
                                st.rerun()

                with colB:
                    st.subheader("🔄 Bulk Update & Revert Tickets")
                    active_tickets = df_wf[df_wf['Status'] != '5. Completed']
                    
                    if active_tickets.empty:
                        st.info("No active tickets to update.")
                    else:
                        ticket_options = active_tickets.apply(lambda x: f"{x['Truck_ID']} - {x['Component']} ({x['Status']}) --- ID:{x['Ticket_ID']}", axis=1).tolist()
                        selected_options = st.multiselect("Tick Tickets to Update", ticket_options)
                        
                        if selected_options:
                            sel_ids = [opt.split("--- ID:")[1].strip() for opt in selected_options]
                            selected_df = active_tickets[active_tickets['Ticket_ID'].isin(sel_ids)]
                            unique_statuses = selected_df['Status'].unique()
                            
                            if len(unique_statuses) > 1:
                                st.warning("⚠️ Bulk Update Rule: All selected tickets must have the SAME current status to update them together.")
                            else:
                                curr_status = unique_statuses[0]
                                st.markdown(f"**Current Status:** {curr_status} ({len(sel_ids)} tickets selected)")
                                
                                with st.form("bulk_update_form"):
                                    update_status = curr_status
                                    lab_notes_input = req_interv_input = mech_notes_input = ""
                                    
                                    col_fwd, col_rev = st.columns([3, 1])

                                    if curr_status == '1. Pending Collection':
                                        st.write("Have the mechanics collected these samples? **(This will freeze their exact current mileage).**")
                                        if col_fwd.form_submit_button("✅ Mark Collected (Move forward)"): update_status = '2. Pending Lab Dispatch'
                                    
                                    elif curr_status == '2. Pending Lab Dispatch':
                                        st.write("Has the courier taken these samples to the lab?")
                                        if col_fwd.form_submit_button("✅ Mark Sent (Move forward)"): update_status = '3. Lab Results Pending'
                                        if col_rev.form_submit_button("⏪ Undo"): update_status = '1. Pending Collection'
                                            
                                    elif curr_status == '3. Lab Results Pending':
                                        st.write("Applying these findings to ALL selected tickets:")
                                        lab_notes_input = st.text_area("1. Enter Lab Findings (e.g., 'High Iron')")
                                        req_interv_input = st.text_area("2. Enter Required Intervention (e.g., 'Drain oil & change filters')")
                                        
                                        col_b1, col_b2 = col_fwd.columns(2)
                                        if col_b1.form_submit_button("🚨 Send to Mechanics"): update_status = '4. Pending Intervention'
                                        if col_b2.form_submit_button("✅ Healthy (Close Tickets)"): update_status = '5. Completed'
                                        if col_rev.form_submit_button("⏪ Undo"): update_status = '2. Pending Lab Dispatch'
                                        
                                    elif curr_status == '4. Pending Intervention':
                                        st.write("Applying this action to ALL selected tickets:")
                                        mech_notes_input = st.text_area("Enter Action Taken by Mechanic")
                                        if col_fwd.form_submit_button("✅ Mark Jobs Complete"): update_status = '5. Completed'
                                        if col_rev.form_submit_button("⏪ Undo"): update_status = '3. Lab Results Pending'

                                    # --- BULLETPROOF SAVE LOGIC ---
                                    if update_status != curr_status:
                                        df_wf['Sample_Mileage'] = df_wf['Sample_Mileage'].astype(object)
                                        
                                        for sel_id in sel_ids:
                                            df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Status'] = update_status
                                            df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Last_Updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                                            
                                            if update_status == '2. Pending Lab Dispatch' and curr_status == '1. Pending Collection':
                                                truck_id = df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Truck_ID'].values[0]
                                                try:
                                                    frozen_m = df_sampling[df_sampling['Truck ID'] == truck_id]['Current KM'].values[0]
                                                    df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Sample_Mileage'] = str(clean_num(frozen_m))
                                                except:
                                                    df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Sample_Mileage'] = "Unknown"
                                            elif update_status == '1. Pending Collection':
                                                df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Sample_Mileage'] = "Unknown"

                                            if lab_notes_input: df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Lab_Notes'] = lab_notes_input
                                            if req_interv_input: df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Required_Intervention'] = req_interv_input
                                            if mech_notes_input: df_wf.loc[df_wf['Ticket_ID'] == sel_id, 'Mechanic_Action'] = mech_notes_input
                                        
                                        df_wf.to_csv(WORKFLOW_FILE, index=False)
                                        st.success(f"✅ {len(sel_ids)} tickets updated successfully!")
                                        st.rerun()

                st.divider()
                st.subheader("📚 Historical Report (Completed Interventions)")
                completed_df = df_wf[df_wf['Status'] == '5. Completed']
                st.dataframe(completed_df, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Error processing files: {e}.")
else:
    st.info("👈 Please upload all three files once to initialize the system's memory.")