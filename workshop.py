import streamlit as st
import pandas as pd
import os
from datetime import date

st.set_page_config(page_title="Workshop Log", layout="wide")
st.title("🛠️ Daily Workshop & Downtime Log")
st.info("Morning logs are provisional. Evening logs are final and will OVERRIDE any morning logs for the same date.")

# 1. Setup the Database File
WORKSHOP_FILE = "Workshop_Log.csv"

# Create the file if it doesn't exist yet
if not os.path.exists(WORKSHOP_FILE):
    df_empty = pd.DataFrame(columns=["Date", "Truck_ID", "Status", "Logged_By"])
    df_empty.to_csv(WORKSHOP_FILE, index=False)

# Load existing data
df_log = pd.read_csv(WORKSHOP_FILE)

# 2. The Input Form
st.subheader("📋 Log Daily Downtime")

# Generate a list of Miloto Trucks to pick from (excluding locals 30, 48, 107)
miloto_trucks = [f"MILOTO-{str(i).zfill(2)}(MTL{str(i).zfill(2)})" for i in range(1, 150) if i not in [30, 48, 107]]

with st.form("workshop_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        log_date = st.date_input("Select Date", date.today())
        logged_by = st.selectbox("Logged By", ["Morning Checker", "Evening Checker", "Workshop Manager"])
        
    with col2:
        st.markdown("Select **ALL** trucks currently parked in the workshop:")
        down_trucks = st.multiselect("Select Trucks", miloto_trucks)
        
    submit = st.form_submit_button("💾 Save to Workshop Log")

    if submit:
        # ==========================================
        # OVERRIDE LOGIC: Evening / Manager
        # ==========================================
        if logged_by in ["Evening Checker", "Workshop Manager"]:
            # 1. Delete all previous records for this specific date
            df_log = df_log[df_log['Date'] != str(log_date)]
            
            # 2. Add the new final list
            new_rows = []
            for truck in down_trucks:
                new_rows.append({
                    "Date": str(log_date), "Truck_ID": truck, 
                    "Status": "Lost Day (EOD Confirmed)", "Logged_By": logged_by
                })
            
            if new_rows:
                df_log = pd.concat([df_log, pd.DataFrame(new_rows)], ignore_index=True)
            
            df_log.to_csv(WORKSHOP_FILE, index=False)
            st.success(f"✅ Evening Reconciliation Complete! The log for {log_date} has been overwritten with these {len(down_trucks)} trucks.")
            st.rerun()

        # ==========================================
        # PROVISIONAL LOGIC: Morning
        # ==========================================
        elif logged_by == "Morning Checker":
            if not down_trucks:
                st.warning("⚠️ Please select at least one truck.")
            else:
                new_rows = []
                for truck in down_trucks:
                    # Only add if it doesn't already exist for this date
                    duplicate_check = df_log[(df_log['Date'] == str(log_date)) & (df_log['Truck_ID'] == truck)]
                    if duplicate_check.empty:
                        new_rows.append({
                            "Date": str(log_date), "Truck_ID": truck, 
                            "Status": "Provisional (Morning)", "Logged_By": logged_by
                        })
                
                if new_rows:
                    df_log = pd.concat([df_log, pd.DataFrame(new_rows)], ignore_index=True)
                    df_log.to_csv(WORKSHOP_FILE, index=False)
                    st.success(f"✅ Morning Log Saved! Added {len(new_rows)} trucks for {log_date}.")
                    st.rerun()
                else:
                    st.info("These trucks are already logged for this morning. No duplicates added.")

st.divider()

# 3. View the History
st.subheader("📚 Historical Downtime Record")
colA, colB = st.columns([3, 1])

with colA:
    # Display the log, sorted by newest first
    st.dataframe(df_log.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

with colB:
    st.markdown("**Total Days Lost per Truck**")
    if not df_log.empty:
        lost_days = df_log['Truck_ID'].value_counts().reset_index()
        lost_days.columns = ['Truck_ID', 'Days Lost']
        st.dataframe(lost_days, use_container_width=True, hide_index=True)
    else:
        st.write("No downtime recorded yet.")