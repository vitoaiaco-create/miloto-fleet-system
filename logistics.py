import streamlit as st
import pandas as pd
from pyairtable import Api
import re  # <--- Added to help clean the text

# --- 1. FLEET SETUP ---
def generate_fleet():
    fleet = []
    excluded = {30, 48, 107}
    for i in range(1, 128):
        if i in excluded: continue
        num_str = f"{i:02d}"
        fleet.append(f"MILOTO-{num_str}(MTL{num_str})")
    return fleet

LIST_OF_TRUCKS = generate_fleet()

# --- 2. FETCH WORKSHOP LOGS (FROM AIRTABLE) ---
@st.cache_data(ttl=60) # Caches the data for 60 seconds to keep the app fast
def get_workshop_downtime():
    try:
        api = Api(st.secrets["AIRTABLE_TOKEN"])
        ws_table = api.table(st.secrets["AIRTABLE_BASE_ID"], "Workshop Logs")
        records = ws_table.all()
        
        ws_data = []
        for r in records:
            fields = r.get("fields", {})
            truck = fields.get("Trucks")
            date_val = fields.get("Date")
            if truck and date_val:
                ws_data.append({"Truck": truck, "Date": date_val})
                
        if not ws_data:
            return pd.DataFrame(columns=["Truck", "Workshop Days"])
            
        df_ws = pd.DataFrame(ws_data)
        
        # Count unique days each truck was logged in the workshop
        ws_counts = df_ws.groupby("Truck")["Date"].nunique().reset_index()
        ws_counts.columns = ["Truck", "Workshop Days"]
        return ws_counts
    except Exception as e:
        st.error(f"⚠️ Could not fetch Workshop Logs from Airtable: {e}")
        return pd.DataFrame(columns=["Truck", "Workshop Days"])

# --- 3. UI & FILE UPLOAD ---
st.title("🚛 Logistics Trips Dashboard")
st.divider()

st.markdown("Upload the **Miloto Trips** Excel/CSV file to calculate fleet performance. This dashboard automatically syncs with your **Workshop Logs** to calculate net available days.")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("Upload Miloto Trips File (.xlsx or .csv)", type=["xlsx", "xls", "csv"])
with col2:
    st.write("") 
    st.write("") 
    st.info("📅 Available days are calculated automatically based on the latest trip date in your uploaded file.")

# --- 4. ANALYTICS LOGIC ---
if uploaded_file is not None:
    try:
        # Read the file
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
            
        # Ensure the Identity column exists
        if "Identity" not in df_raw.columns:
            st.error("❌ The uploaded file must contain an 'Identity' column to count the trucks.")
        else:
            with st.spinner("Crunching data and syncing with Airtable Workshop Logs..."):
                
                # --- NEW: NORMALIZE IDENTITY COLUMN ---
                # This fixes errors where staff typed "MTL108(MILOTO-108)" instead of "MILOTO-108(MTL108)"
                def clean_identity(val):
                    val = str(val).strip()
                    if val.startswith("MTL") and "(MILOTO-" in val:
                        num = val.split('(')[0].replace('MTL', '')
                        return f"MILOTO-{num}(MTL{num})"
                    return val
                
                df_raw["Identity"] = df_raw["Identity"].apply(clean_identity)
                # --------------------------------------

                # --- AUTOMATICALLY CALCULATE AVAILABLE DAYS ---
                if "DOT" in df_raw.columns:
                    df_raw["DOT"] = pd.to_datetime(df_raw["DOT"], format="%d-%m-%Y", errors="coerce")
                    max_date = df_raw["DOT"].max()
                    
                    if pd.notna(max_date):
                        total_days_in_month = max_date.day
                    else:
                        st.warning("⚠️ Could not read dates in 'DOT' column. Defaulting to 30 days.")
                        total_days_in_month = 30
                else:
                    st.warning("⚠️ 'DOT' column not found in the uploaded file. Defaulting to 30 days.")
                    total_days_in_month = 30
                # ---------------------------------------------------
                
                # 1. Filter out externals, 30, 48, and 107
                df_miloto = df_raw[df_raw["Identity"].isin(LIST_OF_TRUCKS)]
                
                # 2. Count trips per Miloto truck
                trip_counts = df_miloto["Identity"].value_counts().reset_index()
                trip_counts.columns = ["Truck", "Total Trips"]
                
                # 3. Pull Workshop Days from Airtable
                df_workshop = get_workshop_downtime()
                
                # 4. Build the final Dashboard DataFrame
                df_dashboard = pd.DataFrame({"Truck": LIST_OF_TRUCKS})
                
                # Merge the trips and workshop days into the master list
                df_dashboard = df_dashboard.merge(trip_counts, on="Truck", how="left").fillna(0)
                df_dashboard = df_dashboard.merge(df_workshop, on="Truck", how="left").fillna(0)
                
                # Clean up numbers
                df_dashboard["Total Trips"] = df_dashboard["Total Trips"].astype(int)
                df_dashboard["Workshop Days"] = df_dashboard["Workshop Days"].astype(int)
                
                # 5. Calculations
                df_dashboard["Total Days Available"] = total_days_in_month
                
                # Net Available Days = Total - Workshop
                df_dashboard["Net Available Days"] = df_dashboard["Total Days Available"] - df_dashboard["Workshop Days"]
                df_dashboard["Net Available Days"] = df_dashboard["Net Available Days"].apply(lambda x: max(x, 0))
                
                # Average Days per Trip
                df_dashboard["Avg Days per Trip"] = df_dashboard.apply(
                    lambda row: round(row["Net Available Days"] / row["Total Trips"], 2) if row["Total Trips"] > 0 else 0.0,
                    axis=1
                )
                
                # --- 6. DISPLAY DASHBOARD ---
                st.success("✅ Dashboard Generated Successfully!")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Miloto Trips", df_dashboard["Total Trips"].sum())
                m2.metric("Active Trucks (1+ Trip)", len(df_dashboard[df_dashboard["Total Trips"] > 0]))
                m3.metric("Total Workshop Days", df_dashboard["Workshop Days"].sum())
                
                total_net_days = df_dashboard["Net Available Days"].sum()
                total_fleet_trips = df_dashboard["Total Trips"].sum()
                fleet_avg = round(total_net_days / total_fleet_trips, 2) if total_fleet_trips > 0 else 0.0
                m4.metric("Fleet Avg Days/Trip", fleet_avg)
                
                st.divider()
                st.subheader("📊 Individual Truck Performance")
                st.dataframe(df_dashboard, use_container_width=True, hide_index=True)
                
                csv = df_dashboard.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Download Dashboard as CSV",
                    data=csv,
                    file_name=f"logistics_dashboard.csv",
                    mime="text/csv",
                )
                
    except Exception as e:
        st.error(f"❌ Could not process the file. Error: {e}")
