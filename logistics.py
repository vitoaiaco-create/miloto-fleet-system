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

# --- 2. FETCH WORKSHOP LOGS (FROM AIRTABLE) ---
@st.cache_data(ttl=60)
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
        ws_counts = df_ws.groupby("Truck")["Date"].nunique().reset_index()
        ws_counts.columns = ["Truck", "Workshop Days"]
        return ws_counts
    except Exception as e:
        st.error(f"⚠️ Could not fetch Workshop Logs: {e}")
        return pd.DataFrame(columns=["Truck", "Workshop Days"])

# --- 3. MILEAGE PROCESSING ENGINE (UPGRADED ALGORITHM) ---
def process_mileage_data(df_mileage):
    """Calculates daily diffs to filter out typos (like 8,000,000 km jumps)."""
    dates_row = df_mileage.iloc[0].values
    col_to_date = {}
    
    # Extract valid dates from Row 0
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
            
            # Extract all daily readings
            readings = []
            for c, dt in col_to_date.items():
                try:
                    v = float(row.iloc[c])
                    if pd.notna(v) and v > 0:
                        readings.append((dt, v))
                except: pass
            
            # Sort chronologically to track day-to-day
            readings.sort(key=lambda x: x[0])
            
            truck_m_totals = {}
            # Calculate daily differences
            for i in range(1, len(readings)):
                prev_dt, prev_v = readings[i-1]
                curr_dt, curr_v = readings[i]
                
                diff = curr_v - prev_v
                
                # Automatically discard data-entry typos (e.g. diffs over 1,500km in a single day)
                if 0 <= diff <= 1500:
                    m_key = curr_dt.strftime("%Y-%m")
                    
                    if m_key not in monthly_totals:
                        monthly_totals[m_key] = 0
                    monthly_totals[m_key] += diff
                    
                    if m_key not in truck_m_totals:
                        truck_m_totals[m_key] = 0
                    truck_m_totals[m_key] += diff
                    
            truck_data = {"Truck": std_truck}
            truck_data.update(truck_m_totals)
            truck_mileage.append(truck_data)

    return pd.DataFrame(truck_mileage), monthly_totals

# --- 4. PDF GENERATOR ---
def generate_pdf_report(df_master, monthly_totals=None):
    """Generates the ZPC KILOMETRE & UTILIZATION REPORT."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # --- HEADER ---
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "ZAMBEZI PORTLAND CEMENT", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "FLEET UTILIZATION & KILOMETRE REPORT", ln=True, align="C")
    pdf.ln(5)

    # --- BAR CHART ---
    if monthly_totals:
        months_labels = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
        y_2025 = [monthly_totals.get(f"2025-{m}", 0) for m in months_labels]
        y_2026 = [monthly_totals.get(f"2026-{m}", 0) for m in months_labels]

        fig, ax = plt.subplots(figsize=(10, 4))
        bar_width = 0.35
        x = range(len(months_labels))
        
        ax.bar([i - bar_width/2 for i in x], y_2025, bar_width, label='2025', color='#2ca02c') # Green
        ax.bar([i + bar_width/2 for i in x], y_2026, bar_width, label='2026', color='#d62728') # Red
        
        ax.set_title('2026 vs 2025 Total kms')
        ax.set_xticks(x)
        ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'])
        
        # Stop scientific notation on Y-axis (1e6) so it prints normal numbers
        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val):,}"))
        
        ax.legend()
        plt.tight_layout()

        # Save plot to memory and embed in PDF
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        pdf.image(img_buffer, x=45, y=30, w=200)
        pdf.ln(95) # Move cursor below the image

    # --- MASTER DATA TABLE ---
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
    file_mileage = st.file_uploader("2. Upload Miloto Mileage File (.xlsx) (Optional for km Report)", type=["xlsx", "xls"])

if file_trips is not None:
    try:
        # Read Trips
        df_raw = pd.read_csv(file_trips) if file_trips.name.endswith('.csv') else pd.read_excel(file_trips)
            
        if "Identity" not in df_raw.columns:
            st.error("❌ The uploaded trips file must contain an 'Identity' column.")
        else:
            with st.spinner("Crunching data and syncing with Airtable..."):
                
                # --- NORMALIZE IDENTITY COLUMN ---
                def clean_identity(val):
                    val = str(val).strip()
                    if val.startswith("MTL") and "(MILOTO-" in val:
                        num = val.split('(')[0].replace('MTL', '')
                        return f"MILOTO-{num}(MTL{num})"
                    return val
                
                df_raw["Identity"] = df_raw["Identity"].apply(clean_identity)

                # --- AUTOMATICALLY CALCULATE AVAILABLE DAYS ---
                if "DOT" in df_raw.columns:
                    df_raw["DOT"] = pd.to_datetime(df_raw["DOT"], format="%d-%m-%Y", errors="coerce")
                    max_date = df_raw["DOT"].max()
                    total_days_in_month = max_date.day if pd.notna(max_date) else 30
                else:
                    total_days_in_month = 30
                
                # 1. Filter out externals, 30, 48, and 107
                df_miloto = df_raw[df_raw["Identity"].isin(LIST_OF_TRUCKS)]
                
                # 2. Count trips per Miloto truck
                trip_counts = df_miloto["Identity"].value_counts().reset_index()
                trip_counts.columns = ["Truck", "Total Trips"]
                
                # 3. Pull Workshop Days from Airtable
                df_workshop = get_workshop_downtime()
                
                # 4. Build the final Dashboard DataFrame
                df_dashboard = pd.DataFrame({"Truck": LIST_OF_TRUCKS})
                df_dashboard = df_dashboard.merge(trip_counts, on="Truck", how="left").fillna(0)
                df_dashboard = df_dashboard.merge(df_workshop, on="Truck", how="left").fillna(0)
                
                # Clean up numbers
                df_dashboard["Total Trips"] = df_dashboard["Total Trips"].astype(int)
                df_dashboard["Workshop Days"] = df_dashboard["Workshop Days"].astype(int)
                
                # 5. Calculations
                df_dashboard["Total Days Available"] = total_days_in_month
                df_dashboard["Net Available Days"] = df_dashboard.apply(lambda row: max(row["Total Days Available"] - row["Workshop Days"], 0), axis=1)
                df_dashboard["Avg Days per Trip"] = df_dashboard.apply(
                    lambda row: round(row["Net Available Days"] / row["Total Trips"], 2) if row["Total Trips"] > 0 else 0.0,
                    axis=1
                )
                
                # --- PROCESS MILEAGE (IF UPLOADED) ---
                monthly_totals = None
                if file_mileage is not None:
                    df_mil_raw = pd.read_excel(file_mileage, sheet_name='MILOTO')
                    df_truck_kms, monthly_totals = process_mileage_data(df_mil_raw)
                    # Merge KMS into the master dashboard
                    df_dashboard = df_dashboard.merge(df_truck_kms, on="Truck", how="left").fillna(0)

                # --- DISPLAY DASHBOARD ---
                st.success("✅ Analytics Engine Complete!")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Miloto Trips", df_dashboard["Total Trips"].sum())
                m2.metric("Active Trucks", len(df_dashboard[df_dashboard["Total Trips"] > 0]))
                m3.metric("Total WS Days", df_dashboard["Workshop Days"].sum())
                
                total_net = df_dashboard["Net Available Days"].sum()
                total_trips = df_dashboard["Total Trips"].sum()
                m4.metric("Fleet Avg Days/Trip", round(total_net / total_trips, 2) if total_trips > 0 else 0.0)
                
                st.divider()
                st.subheader("📊 Fleet Performance Table")
                st.dataframe(df_dashboard, use_container_width=True, hide_index=True)
                
                # --- GENERATE EXPORTS ---
                c_btn1, c_btn2 = st.columns(2)
                
                with c_btn1:
                    csv = df_dashboard.to_csv(index=False).encode('utf-8')
                    st.download_button(label="⬇️ Download CSV", data=csv, file_name="logistics_dashboard.csv", mime="text/csv", use_container_width=True)
                
                with c_btn2:
                    pdf_bytes = generate_pdf_report(df_dashboard, monthly_totals)
                    st.download_button(
                        label="📄 Generate ZPC PDF Report",
                        data=bytes(pdf_bytes),
                        file_name=f"ZPC_Report_{datetime.today().strftime('%b_%Y')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )
                
    except Exception as e:
        st.error(f"❌ Could not process the files. Error: {e}")
