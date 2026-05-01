import streamlit as st
import pandas as pd
from pyairtable import Api
import re
import io
from datetime import datetime
import matplotlib.pyplot as plt
from fpdf import FPDF

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

# --- 2. FETCH WORKSHOP LOGS (RAW DATA FOR TIME-SERIES) ---
@st.cache_data(ttl=60)
def get_raw_workshop_logs():
    """Fetches all workshop logs and returns a raw dataframe to allow month-by-month grouping."""
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
            return pd.DataFrame(columns=["Truck", "Date"])
            
        return pd.DataFrame(ws_data)
    except Exception as e:
        st.error(f"⚠️ Could not fetch Workshop Logs: {e}")
        return pd.DataFrame(columns=["Truck", "Date"])

# --- 3. MILEAGE PROCESSING ENGINE ---
def process_mileage_data(df_mileage):
    dates_row = df_mileage.iloc[0].values
    col_to_date = {}
    
    for i, val in enumerate(dates_row):
        if isinstance(val, (pd.Timestamp, datetime)):
            col_to_date[i] = val
        elif isinstance(val, str):
            try: col_to_date[i] = pd.to_datetime(val)
            except: pass

    monthly_totals = {}
    truck_mileage = []

    for idx, row in df_mileage.iterrows():
        truck_id_raw = str(row.iloc[0]).strip()
        if truck_id_raw.startswith("MTL"):
            num = truck_id_raw.replace("MTL", "")
            std_truck = f"MILOTO-{num}(MTL{num})"
            
            readings = []
            for c, dt in col_to_date.items():
                try:
                    v = float(row.iloc[c])
                    if pd.notna(v) and v > 0: readings.append((dt, v))
                except: pass
            
            readings.sort(key=lambda x: x[0])
            
            truck_m_totals = {}
            for i in range(1, len(readings)):
                prev_dt, prev_v = readings[i-1]
                curr_dt, curr_v = readings[i]
                
                diff = curr_v - prev_v
                
                # Filter out typos (max 1500km/day)
                if 0 <= diff <= 1500:
                    m_key = curr_dt.strftime("%Y-%m")
                    
                    if m_key not in monthly_totals: monthly_totals[m_key] = 0
                    monthly_totals[m_key] += diff
                    
                    if m_key not in truck_m_totals: truck_m_totals[m_key] = 0
                    truck_m_totals[m_key] += diff
                    
            truck_data = {"Truck": std_truck}
            truck_data.update(truck_m_totals)
            truck_mileage.append(truck_data)

    return pd.DataFrame(truck_mileage), monthly_totals

# --- 4. PDF GENERATOR ---
def generate_pdf_report(df_master, monthly_totals=None):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "ZAMBEZI PORTLAND CEMENT", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "FLEET UTILIZATION & KILOMETRE REPORT", ln=True, align="C")
    pdf.ln(5)

    if monthly_totals:
        months_labels = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
        y_2025 = [monthly_totals.get(f"2025-{m}", 0) for m in months_labels]
        y_2026 = [monthly_totals.get(f"2026-{m}", 0) for m in months_labels]

        fig, ax = plt.subplots(figsize=(10, 4))
        bar_width = 0.35
        x = range(len(months_labels))
        
        ax.bar([i - bar_width/2 for i in x], y_2025, bar_width, label='2025', color='#2ca02c')
        ax.bar([i + bar_width/2 for i in x], y_2026, bar_width, label='2026', color='#d62728')
        
        ax.set_title('2026 vs 2025 Total kms')
        ax.set_xticks(x)
        ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'])
        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val):,}"))
        ax.legend()
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        pdf.image(img_buffer, x=45, y=30, w=200)
        pdf.ln(95) 

    pdf.set_font("Helvetica", "B", 9)
    data_cols = ["Truck", "Total Trips", "Workshop Days", "Net Available Days", "Avg Days per Trip"]
    display_cols = ["Truck", "Total Trips", "WS Days", "Net Days", "Avg Days/Trip"]
    km_cols = [c for c in df_master.columns if "2026-" in c or "2025-" in c][-3:] 
    
    data_cols.extend(km_cols)
    display_cols.extend(km_cols)
    
    col_widths = [40, 25, 25, 25, 30] + [30] * len(km_cols)
    
    for i, col_name in enumerate(display_cols):
        pdf.cell(col_widths[i], 8, str(col_name), border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for idx, row in df_master.iterrows():
        for i, col_name in enumerate(data_cols):
            val = row[col_name]
            if isinstance(val, (int, float)):
                val = f"{val:.1f}" if "Avg" in col_name else f"{int(val)}"
            pdf.cell(col_widths[i], 6, str(val), border=1, align="C")
        pdf.ln()

    return pdf.output()

# --- 5. UI & FILE UPLOAD ---
st.title("🚛 Logistics & Kilometre Dashboard")
st.divider()

st.markdown("Upload your operational files to calculate fleet performance and generate the **ZPC Monthly PDF Report**.")

col1, col2 = st.columns(2)
with col1:
    file_trips = st.file_uploader("1. Upload Miloto Trips (.xlsx/.csv)", type=["xlsx", "xls", "csv"])
with col2:
    file_mileage = st.file_uploader("2. Upload Miloto Mileage File (.xlsx) (Optional)", type=["xlsx", "xls"])

if file_trips is not None:
    try:
        df_raw = pd.read_csv(file_trips) if file_trips.name.endswith('.csv') else pd.read_excel(file_trips)
            
        if "Identity" not in df_raw.columns:
            st.error("❌ The uploaded trips file must contain an 'Identity' column.")
        else:
            with st.spinner("Crunching historical and current month data..."):
                
                # --- NORMALIZE IDENTITY COLUMN ---
                def clean_identity(val):
                    val = str(val).strip()
                    if val.startswith("MTL") and "(MILOTO-" in val:
                        num = val.split('(')[0].replace('MTL', '')
                        return f"MILOTO-{num}(MTL{num})"
                    return val
                df_raw["Identity"] = df_raw["Identity"].apply(clean_identity)

                # --- DETERMINE CURRENT MONTH & AVAILABLE DAYS ---
                current_month_str = datetime.today().strftime("%Y-%m")
                if "DOT" in df_raw.columns:
                    df_raw["DOT"] = pd.to_datetime(df_raw["DOT"], format="%d-%m-%Y", errors="coerce")
                    max_date = df_raw["DOT"].max()
                    if pd.notna(max_date):
                        total_days_in_month = max_date.day
                        current_month_str = max_date.strftime("%Y-%m")
                    else:
                        total_days_in_month = 30
                else:
                    total_days_in_month = 30
                
                # --- CALCULATE CURRENT MONTH TRIPS ---
                df_miloto = df_raw[df_raw["Identity"].isin(LIST_OF_TRUCKS)]
                trip_counts = df_miloto["Identity"].value_counts().reset_index()
                trip_counts.columns = ["Truck", "Total Trips"]
                current_total_trips = trip_counts["Total Trips"].sum()
                
                # --- FETCH & PROCESS WORKSHOP LOGS ---
                df_ws_raw = get_raw_workshop_logs()
                
                # A. Current Month Workshop Data
                df_ws_current = df_ws_raw[df_ws_raw['Date'].str.startswith(current_month_str)] if not df_ws_raw.empty else pd.DataFrame()
                if not df_ws_current.empty:
                    ws_counts = df_ws_current.groupby("Truck")["Date"].nunique().reset_index()
                    ws_counts.columns = ["Truck", "Workshop Days"]
                else:
                    ws_counts = pd.DataFrame(columns=["Truck", "Workshop Days"])
                    
                # B. Historical Workshop Data (Grouped by YYYY-MM)
                ws_monthly_totals = {}
                if not df_ws_raw.empty:
                    df_ws_raw['Month'] = df_ws_raw['Date'].str[:7]
                    ws_monthly_totals = df_ws_raw.groupby(['Month', 'Truck'])['Date'].nunique().groupby('Month').sum().to_dict()

                # --- PROCESS MILEAGE ---
                monthly_totals = {}
                df_truck_kms = pd.DataFrame()
                if file_mileage is not None:
                    df_mil_raw = pd.read_excel(file_mileage, sheet_name='MILOTO')
                    df_truck_kms, monthly_totals = process_mileage_data(df_mil_raw)

                # --- BUILD MASTER DATAFRAME (FOR PDF) ---
                df_dashboard = pd.DataFrame({"Truck": LIST_OF_TRUCKS})
                df_dashboard = df_dashboard.merge(trip_counts, on="Truck", how="left").fillna(0)
                df_dashboard = df_dashboard.merge(ws_counts, on="Truck", how="left").fillna(0)
                
                df_dashboard["Total Trips"] = df_dashboard["Total Trips"].astype(int)
                df_dashboard["Workshop Days"] = df_dashboard["Workshop Days"].astype(int)
                df_dashboard["Total Days Available"] = total_days_in_month
                df_dashboard["Net Available Days"] = df_dashboard.apply(lambda row: max(row["Total Days Available"] - row["Workshop Days"], 0), axis=1)
                df_dashboard["Avg Days per Trip"] = df_dashboard.apply(
                    lambda row: round(row["Net Available Days"] / row["Total Trips"], 2) if row["Total Trips"] > 0 else 0.0,
                    axis=1
                )
                
                # Merge historical KMS into master (used for PDF generation)
                if not df_truck_kms.empty:
                    df_dashboard = df_dashboard.merge(df_truck_kms, on="Truck", how="left").fillna(0)

                # --- BUILD STRICT CURRENT MONTH DATAFRAME (FOR TAB 1) ---
                tab1_cols = ["Truck", "Total Trips", "Workshop Days", "Net Available Days", "Avg Days per Trip"]
                df_tab1 = df_dashboard[tab1_cols].copy()
                if current_month_str in df_dashboard.columns:
                    df_tab1["Current Month KM"] = df_dashboard[current_month_str].astype(int)
                else:
                    df_tab1["Current Month KM"] = 0
                    
                current_net_days = df_tab1["Net Available Days"].sum()
                current_fleet_avg = round(current_net_days / current_total_trips, 2) if current_total_trips > 0 else 0.0
                current_total_kms = df_tab1["Current Month KM"].sum()

                # --- BUILD YEARLY SUMMARY DATAFRAME (FOR TAB 2) ---
                all_months = sorted(list(set(list(monthly_totals.keys()) + list(ws_monthly_totals.keys()) + [current_month_str])))
                yearly_data = []
                
                for m in all_months:
                    kms = monthly_totals.get(m, 0)
                    ws_days = ws_monthly_totals.get(m, 0)
                    
                    trips = current_total_trips if m == current_month_str else 0
                    net_days = current_net_days if m == current_month_str else 0
                    avg_days = current_fleet_avg if m == current_month_str else 0.0
                    
                    yearly_data.append({
                        "Month": m,
                        "Total Mileage (km)": f"{int(kms):,}",
                        "Total Trips": int(trips),
                        "Workshop Days": int(ws_days),
                        "Net Available Days": int(net_days),
                        "Avg Days/Trip": float(avg_days)
                    })
                    
                df_yearly = pd.DataFrame(yearly_data)

                # --- RENDER UI TABS ---
                st.success("✅ Analytics Engine Complete!")
                
                tab1, tab2 = st.tabs(["📅 Current Month Overview", "📈 Yearly Historical Trends"])
                
                # --- TAB 1: CURRENT MONTH ---
                with tab1:
                    st.subheader(f"Operations for {current_month_str}")
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total Trips", int(current_total_trips))
                    m2.metric("Total WS Days", int(df_tab1["Workshop Days"].sum()))
                    m3.metric("Net Available Days", int(current_net_days))
                    m4.metric("Avg Days/Trip", current_fleet_avg)
                    m5.metric("Total Fleet KM", f"{int(current_total_kms):,}")
                    
                    # Display the strictly filtered dataframe
                    st.dataframe(df_tab1, use_container_width=True, hide_index=True)
                    
                    c_btn1, c_btn2 = st.columns(2)
                    with c_btn1:
                        csv = df_tab1.to_csv(index=False).encode('utf-8')
                        st.download_button(label="⬇️ Download Monthly CSV", data=csv, file_name=f"logistics_{current_month_str}.csv", mime="text/csv", use_container_width=True)
                    with c_btn2:
                        pdf_bytes = generate_pdf_report(df_dashboard, monthly_totals)
                        st.download_button(label="📄 Generate ZPC PDF Report", data=bytes(pdf_bytes), file_name=f"ZPC_Report_{current_month_str}.pdf", mime="application/pdf", use_container_width=True, type="primary")

                # --- TAB 2: YEARLY TRENDS ---
                with tab2:
                    st.subheader("Fleet-Wide Monthly Aggregation")
                    st.markdown("*(Note: Historical Trips and Net Days are tracked from the current month onward.)*")
                    
                    if monthly_totals:
                        months_labels = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
                        y_2025 = [monthly_totals.get(f"2025-{m}", 0) for m in months_labels]
                        y_2026 = [monthly_totals.get(f"2026-{m}", 0) for m in months_labels]

                        fig, ax = plt.subplots(figsize=(10, 3.5))
                        bar_width = 0.35
                        x = range(len(months_labels))
                        
                        ax.bar([i - bar_width/2 for i in x], y_2025, bar_width, label='2025', color='#2ca02c')
                        ax.bar([i + bar_width/2 for i in x], y_2026, bar_width, label='2026', color='#d62728')
                        
                        ax.set_title('2026 vs 2025 Total kms')
                        ax.set_xticks(x)
                        ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'])
                        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val):,}"))
                        ax.legend()
                        st.pyplot(fig)
                    
                    st.dataframe(df_yearly, use_container_width=True, hide_index=True)
                    
                    csv_yearly = df_yearly.to_csv(index=False).encode('utf-8')
                    st.download_button(label="⬇️ Download Yearly Aggregation CSV", data=csv_yearly, file_name="yearly_fleet_aggregation.csv", mime="text/csv")
                
    except Exception as e:
        st.error(f"❌ Could not process the files. Error: {e}")
