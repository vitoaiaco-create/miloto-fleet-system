import streamlit as st
import pandas as pd
from pyairtable import Api
import re
import io
import itertools
from calendar import monthrange
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

# --- 2. FETCH WORKSHOP LOGS ---
@st.cache_data(ttl=60)
def get_raw_workshop_logs():
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

# --- CHART HELPER FUNCTION ---
def add_bar_labels(ax, bars):
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.annotate(f'{height:,.0f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=7, rotation=90)

# --- 4. PDF GENERATORS ---
def generate_monthly_pdf(df_master, current_month_str):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "ZAMBEZI PORTLAND CEMENT", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"FLEET UTILIZATION REPORT - {current_month_str}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 9)
    data_cols = ["Truck", "Total Trips", "Workshop Days", "Net Available Days", "Avg Days per Trip", "Current Month KM"]
    display_cols = ["Truck", "Total Trips", "WS Days", "Net Days", "Avg Days/Trip", "Current Month KM"]
    col_widths = [50, 35, 35, 35, 35, 40]
    
    for i, col_name in enumerate(display_cols):
        pdf.cell(col_widths[i], 8, str(col_name), border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for idx, row in df_master.iterrows():
        for i, col_name in enumerate(data_cols):
            val = row[col_name]
            
            fill = False
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(0, 0, 0)
            
            if col_name == "Avg Days per Trip":
                try:
                    v = float(val)
                    if v == 0.0:
                        pdf.set_fill_color(248, 215, 218); pdf.set_text_color(114, 28, 36); fill = True
                    elif v < 1.7:
                        pdf.set_fill_color(212, 237, 218); pdf.set_text_color(21, 87, 36); fill = True
                    elif 1.7 <= v < 1.9:
                        pdf.set_fill_color(255, 243, 205); pdf.set_text_color(133, 100, 4); fill = True
                    else:
                        pdf.set_fill_color(248, 215, 218); pdf.set_text_color(114, 28, 36); fill = True
                except: pass

            if isinstance(val, (int, float)):
                val = f"{val:.2f}" if "Avg" in col_name else f"{int(val)}"
                
            pdf.cell(col_widths[i], 6, str(val), border=1, align="C", fill=fill)
        pdf.ln()

    return pdf.output()

def generate_yearly_pdf(df_yearly, monthly_totals):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "ZAMBEZI PORTLAND CEMENT", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "YEARLY FLEET AGGREGATION & KILOMETRE REPORT", ln=True, align="C")
    pdf.ln(5)

    if monthly_totals:
        months_labels = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
        y_2025 = [monthly_totals.get(f"2025-{m}", 0) for m in months_labels]
        y_2026 = [monthly_totals.get(f"2026-{m}", 0) for m in months_labels]

        fig, ax = plt.subplots(figsize=(10, 4.5))
        bar_width = 0.35
        x = range(len(months_labels))
        
        bars1 = ax.bar([i - bar_width/2 for i in x], y_2025, bar_width, label='2025', color='#2ca02c')
        bars2 = ax.bar([i + bar_width/2 for i in x], y_2026, bar_width, label='2026', color='#d62728')
        
        add_bar_labels(ax, bars1)
        add_bar_labels(ax, bars2)
        
        ax.set_title('2026 vs 2025 Total kms')
        ax.set_xticks(x)
        ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'])
        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val):,}"))
        ax.margins(y=0.2) 
        ax.legend()
        plt.tight_layout()

        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        pdf.image(img_buffer, x=45, y=30, w=200)
        pdf.ln(105) 

    pdf.set_font("Helvetica", "B", 9)
    cols = ["Month", "Total Trips", "WS Days", "Net Days", "Avg Days/Trip", "Total Mileage (km)"]
    col_widths = [30, 30, 30, 30, 40, 50]
    
    for i, col_name in enumerate(cols):
        pdf.cell(col_widths[i], 8, str(col_name), border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for idx, row in df_yearly.iterrows():
        pdf.cell(col_widths[0], 6, str(row["Month"]), border=1, align="C")
        pdf.cell(col_widths[1], 6, str(int(row["Total Trips"])), border=1, align="C")
        pdf.cell(col_widths[2], 6, str(int(row["Workshop Days"])), border=1, align="C")
        pdf.cell(col_widths[3], 6, str(int(row["Net Available Days"])), border=1, align="C")
        pdf.cell(col_widths[4], 6, f'{row["Avg Days/Trip"]:.2f}', border=1, align="C")
        pdf.cell(col_widths[5], 6, str(row["Total Mileage (km)"]), border=1, align="C")
        pdf.ln()

    return pdf.output()

def generate_ytd_tracker_pdf(df_multi, current_month_str):
    pdf = FPDF(orientation="L", unit="mm", format=(420, 594))
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 15, "ZAMBEZI PORTLAND CEMENT", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, f"YTD FLEET TRACKER - {current_month_str}", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 9)
    
    pdf.cell(40, 8, "Truck Details", border=1, align="C")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in month_names:
        pdf.cell(38, 8, m, border=1, align="C") 
    pdf.cell(72, 8, "YTD Averages", border=1, align="C") 
    pdf.ln()

    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(40, 8, "Truck ID", border=1, align="C")
    for _ in range(12):
        pdf.cell(9.5, 8, "KM", border=1, align="C")
        pdf.cell(9.5, 8, "Trp", border=1, align="C")
        pdf.cell(9.5, 8, "WS", border=1, align="C")
        pdf.cell(9.5, 8, "Avg", border=1, align="C")
        
    pdf.cell(18, 8, "KM/mo", border=1, align="C")
    pdf.cell(18, 8, "Trips/mo", border=1, align="C")
    pdf.cell(18, 8, "WS/mo", border=1, align="C")
    pdf.cell(18, 8, "Days/Trip", border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    col_widths = [40] + [9.5]*48 + [18]*4
    
    for idx, row in df_multi.iterrows():
        for i, col in enumerate(df_multi.columns):
            val = str(row[col])
            
            fill = False
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(0, 0, 0)
            
            if "Avg Days/Trip" in col[1] and val != "":
                try:
                    v = float(val)
                    if v == 0.0:
                        pdf.set_fill_color(248, 215, 218); pdf.set_text_color(114, 28, 36); fill = True
                    elif v < 1.7:
                        pdf.set_fill_color(212, 237, 218); pdf.set_text_color(21, 87, 36); fill = True
                    elif 1.7 <= v < 1.9:
                        pdf.set_fill_color(255, 243, 205); pdf.set_text_color(133, 100, 4); fill = True
                    else:
                        pdf.set_fill_color(248, 215, 218); pdf.set_text_color(114, 28, 36); fill = True
                except: pass

            pdf.cell(col_widths[i], 6, val, border=1, align="C", fill=fill)
        pdf.ln()

    return pdf.output()

def generate_destinations_pdf(df_dest, current_month_str):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "ZAMBEZI PORTLAND CEMENT", ln=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"MONTHLY DESTINATION ANALYTICS - {current_month_str}", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 9)
    cols = ["Truck", "Month KM", "Total Trips", "WS Days", "Destination Breakdown"]
    col_widths = [40, 25, 25, 25, 155]
    
    for i, col_name in enumerate(cols):
        pdf.cell(col_widths[i], 8, str(col_name), border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for idx, row in df_dest.iterrows():
        text = str(row["Destination Breakdown"])
        
        # PRE-CALCULATE HEIGHT to stop the infinite page-break loop
        text_width = pdf.get_string_width(text)
        lines = int(text_width / 150) + 1  # 150mm is the safe width inside the 155mm cell
        line_height = 6
        row_height = lines * line_height
        
        # Manually trigger a clean page break if we are near the bottom of the A4 page
        if pdf.get_y() + row_height > 185:
            pdf.add_page()
            
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # Print left-hand columns using dynamic row_height so borders perfectly match the text height
        pdf.cell(col_widths[0], row_height, str(row["Truck"]), border=1, align="C")
        pdf.cell(col_widths[1], row_height, str(row["Current Month KM"]), border=1, align="C")
        pdf.cell(col_widths[2], row_height, str(row["Total Trips"]), border=1, align="C")
        pdf.cell(col_widths[3], row_height, str(row["Workshop Days"]), border=1, align="C")
        
        # Print MultiCell text 
        pdf.set_xy(x_start + sum(col_widths[:4]), y_start)
        pdf.multi_cell(col_widths[4], line_height, text, border=1, align="L")
        
        # Reset the Y coordinate to the absolute bottom of this newly rendered row to prep for the next row
        actual_bottom = max(pdf.get_y(), y_start + row_height)
        pdf.set_xy(pdf.l_margin, actual_bottom)
        
    return pdf.output()

# --- 5. UI & FILE UPLOAD ---
st.title(":material/route: Logistics & Kilometre Dashboard")
st.caption("🟢 App Update: v8.2 (PDF MultiCell Page Break Loop Fixed)")
st.divider()

col1, col2 = st.columns(2)
with col1: file_trips = st.file_uploader("1. Upload Miloto Trips (.xlsx/.csv)", type=["xlsx", "xls", "csv"])
with col2: file_mileage = st.file_uploader("2. Upload Miloto Mileage File (.xlsx) (Optional)", type=["xlsx", "xls"])

if file_trips is not None:
    try:
        df_raw = pd.read_csv(file_trips) if file_trips.name.endswith('.csv') else pd.read_excel(file_trips)
        if "Identity" not in df_raw.columns:
            st.error("❌ The uploaded trips file must contain an 'Identity' column.")
        else:
            with st.spinner("Crunching massive historical data arrays & geographics..."):
                def clean_identity(val):
                    val = str(val).strip()
                    if val.startswith("MTL") and "(MILOTO-" in val:
                        num = val.split('(')[0].replace('MTL', '')
                        return f"MILOTO-{num}(MTL{num})"
                    return val
                df_raw["Identity"] = df_raw["Identity"].apply(clean_identity)

                current_month_str = datetime.today().strftime("%Y-%m")
                if "DOT" in df_raw.columns:
                    df_raw["DOT"] = pd.to_datetime(df_raw["DOT"], format="%d-%m-%Y", errors="coerce")
                    max_date = df_raw["DOT"].max()
                    if pd.notna(max_date):
                        total_days_in_month = max_date.day
                        current_month_str = max_date.strftime("%Y-%m")
                        df_raw["Month_Str"] = df_raw["DOT"].dt.strftime("%Y-%m")
                    else: 
                        total_days_in_month = 30
                        df_raw["Month_Str"] = current_month_str
                else: 
                    total_days_in_month = 30
                    df_raw["Month_Str"] = current_month_str
                
                df_miloto = df_raw[df_raw["Identity"].isin(LIST_OF_TRUCKS)]
                monthly_trip_counts = df_miloto.groupby(['Month_Str', 'Identity']).size().reset_index(name='Total Trips')
                
                df_current_trips_raw = df_miloto[df_miloto["Month_Str"] == current_month_str].copy()
                trip_counts = df_current_trips_raw["Identity"].value_counts().reset_index()
                trip_counts.columns = ["Truck", "Total Trips"]
                current_total_trips = trip_counts["Total Trips"].sum()
                
                dest_col_name = None
                for col in ["Destination", "Location", "Site", "Route", "Customer", "To"]:
                    if col in df_current_trips_raw.columns:
                        dest_col_name = col
                        break
                        
                dest_breakdown_dict = {}
                if dest_col_name:
                    for truck in LIST_OF_TRUCKS:
                        truck_trips = df_current_trips_raw[df_current_trips_raw["Identity"] == truck]
                        if not truck_trips.empty:
                            dest_counts = truck_trips[dest_col_name].value_counts()
                            dest_str = " | ".join([f"{str(k).title()}: {v}" for k, v in dest_counts.items()])
                            dest_breakdown_dict[truck] = dest_str
                        else:
                            dest_breakdown_dict[truck] = "No Trips"
                else:
                    for truck in LIST_OF_TRUCKS:
                        dest_breakdown_dict[truck] = "Destination column missing in Excel"
                
                df_ws_raw = get_raw_workshop_logs()
                df_ws_current = df_ws_raw[df_ws_raw['Date'].str.startswith(current_month_str)] if not df_ws_raw.empty else pd.DataFrame()
                if not df_ws_current.empty:
                    ws_counts = df_ws_current.groupby("Truck")["Date"].nunique().reset_index()
                    ws_counts.columns = ["Truck", "Workshop Days"]
                else:
                    ws_counts = pd.DataFrame(columns=["Truck", "Workshop Days"])
                    
                ws_monthly_totals = {}
                df_ws_truck_m = pd.DataFrame(columns=["Truck", "Month", "Workshop Days"])
                if not df_ws_raw.empty:
                    df_ws_raw['Month'] = df_ws_raw['Date'].str[:7]
                    ws_monthly_totals = df_ws_raw.groupby(['Month', 'Truck'])['Date'].nunique().groupby('Month').sum().to_dict()
                    df_ws_truck_m = df_ws_raw.groupby(['Truck', 'Month'])['Date'].nunique().reset_index(name='Workshop Days')

                monthly_totals = {}
                df_truck_kms = pd.DataFrame()
                if file_mileage is not None:
                    df_mil_raw = pd.read_excel(file_mileage, sheet_name='MILOTO')
                    df_truck_kms, monthly_totals = process_mileage_data(df_mil_raw)

                df_dashboard = pd.DataFrame({"Truck": LIST_OF_TRUCKS})
                df_dashboard = df_dashboard.merge(trip_counts, on="Truck", how="left").fillna(0)
                df_dashboard = df_dashboard.merge(ws_counts, on="Truck", how="left").fillna(0)
                
                df_dashboard["Total Trips"] = df_dashboard["Total Trips"].astype(int)
                df_dashboard["Workshop Days"] = df_dashboard["Workshop Days"].astype(int)
                df_dashboard["Total Days Available"] = total_days_in_month
                df_dashboard["Net Available Days"] = df_dashboard.apply(lambda row: max(row["Total Days Available"] - row["Workshop Days"], 0), axis=1)
                df_dashboard["Avg Days per Trip"] = df_dashboard.apply(
                    lambda row: round(row["Net Available Days"] / row["Total Trips"], 2) if row["Total Trips"] > 0 else 0.0, axis=1)
                
                if not df_truck_kms.empty:
                    df_dashboard = df_dashboard.merge(df_truck_kms, on="Truck", how="left").fillna(0)

                tab1_cols = ["Truck", "Total Trips", "Workshop Days", "Net Available Days", "Avg Days per Trip"]
                df_tab1 = df_dashboard[tab1_cols].copy()
                df_tab1["Current Month KM"] = df_dashboard[current_month_str].astype(int) if current_month_str in df_dashboard.columns else 0
                    
                current_net_days = df_tab1["Net Available Days"].sum()
                current_fleet_avg = round(current_net_days / current_total_trips, 2) if current_total_trips > 0 else 0.0
                current_total_kms = df_tab1["Current Month KM"].sum()

                # --- PREPARE DATA FOR TAB 4 ---
                df_tab4 = pd.DataFrame({
                    "Truck": LIST_OF_TRUCKS,
                    "Current Month KM": df_tab1["Current Month KM"],
                    "Total Trips": df_tab1["Total Trips"],
                    "Workshop Days": df_tab1["Workshop Days"],
                    "Destination Breakdown": [dest_breakdown_dict.get(t, "") for t in LIST_OF_TRUCKS]
                })

                all_months = sorted(list(set(list(monthly_totals.keys()) + list(ws_monthly_totals.keys()) + list(monthly_trip_counts['Month_Str'].unique()) + [current_month_str])))
                
                yearly_data = []
                for m in all_months:
                    m_trips = monthly_trip_counts[monthly_trip_counts['Month_Str'] == m]['Total Trips'].sum()
                    yearly_data.append({
                        "Month": m,
                        "Total Mileage (km)": f"{int(monthly_totals.get(m, 0)):,}",
                        "Total Trips": int(m_trips),
                        "Workshop Days": int(ws_monthly_totals.get(m, 0)),
                        "Net Available Days": max(0, (monthrange(int(m[:4]), int(m[5:7]))[1] * len(LIST_OF_TRUCKS)) - ws_monthly_totals.get(m, 0)) if m != current_month_str else int(current_net_days),
                        "Avg Days/Trip": round(max(0, (monthrange(int(m[:4]), int(m[5:7]))[1] * len(LIST_OF_TRUCKS)) - ws_monthly_totals.get(m, 0)) / m_trips, 2) if m_trips > 0 else 0.0
                    })
                df_yearly = pd.DataFrame(yearly_data)

                grid = pd.DataFrame(list(itertools.product(LIST_OF_TRUCKS, all_months)), columns=["Truck", "Month"])
                df_kms_melt = df_truck_kms.melt(id_vars=["Truck"], var_name="Month", value_name="Mileage") if not df_truck_kms.empty else pd.DataFrame(columns=["Truck", "Month", "Mileage"])
                df_history = grid.merge(df_kms_melt, on=["Truck", "Month"], how="left").fillna({"Mileage": 0})
                df_history = df_history.merge(df_ws_truck_m, on=["Truck", "Month"], how="left").fillna({"Workshop Days": 0})
                
                df_historical_trips_renamed = monthly_trip_counts.rename(columns={"Identity": "Truck", "Month_Str": "Month"})
                df_history = df_history.merge(df_historical_trips_renamed, on=["Truck", "Month"], how="left").fillna({"Total Trips": 0})
                
                def get_days_in_month(m_str):
                    try:
                        if m_str == current_month_str and total_days_in_month != 30: return total_days_in_month
                        return monthrange(int(m_str[:4]), int(m_str[5:7]))[1]
                    except: return 30
                        
                df_history["Total Days"] = df_history["Month"].apply(get_days_in_month)
                df_history["Net Available Days"] = df_history.apply(lambda r: max(0, r["Total Days"] - r["Workshop Days"]), axis=1)
                df_history["Avg Days/Trip"] = df_history.apply(lambda r: round(r["Net Available Days"] / r["Total Trips"], 2) if r["Total Trips"] > 0 else 0.0, axis=1)

                curr_yr = int(current_month_str[:4])
                curr_mo = int(current_month_str[5:7])

                # --- FUTURE-PROOF TRI-DIVISOR LOGIC ---
                km_divisor = curr_mo if curr_yr == 2026 else (curr_mo if curr_yr > 2026 else 12)
                
                if curr_yr == 2026:
                    trips_divisor = max(1, curr_mo - 3)
                    ws_divisor = max(1, curr_mo - 4)
                elif curr_yr > 2026:
                    trips_divisor = curr_mo
                    ws_divisor = curr_mo
                else:
                    trips_divisor = 12
                    ws_divisor = 12 

                df_history_year = df_history[df_history["Month"].str.startswith(str(curr_yr))].copy()
                months_strs = [f"{curr_yr}-{str(i).zfill(2)}" for i in range(1, 13)]
                month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                
                col_tuples = [("Truck Details", "Truck ID")]
                for m in month_names:
                    col_tuples.extend([(m, "Total KM"), (m, "Total Trips"), (m, "WS Days"), (m, "Avg Days/Trip")])
                col_tuples.extend([
                    ("YTD Averages", "Avg KM/mo"),
                    ("YTD Averages", "Avg Trips/mo"),
                    ("YTD Averages", "Avg WS/mo"),
                    ("YTD Averages", "TRUE Avg Days/Trip")
                ])
                mi = pd.MultiIndex.from_tuples(col_tuples)
                df_multi = pd.DataFrame(columns=mi, index=range(len(LIST_OF_TRUCKS)))

                for i, truck in enumerate(LIST_OF_TRUCKS):
                    truck_data = df_history_year[df_history_year["Truck"] == truck]
                    df_multi.at[i, ("Truck Details", "Truck ID")] = truck
                    
                    ytd_km, ytd_trips_for_avg, ytd_ws, ytd_net = 0, 0, 0, 0
                    ytd_trips_for_true_net = 0 
                    
                    for j, m_str in enumerate(months_strs):
                        m_name = month_names[j]
                        m_yr = curr_yr
                        m_mo = j + 1
                        
                        row_data = truck_data[truck_data["Month"] == m_str]
                        
                        if m_yr > curr_yr or (m_yr == curr_yr and m_mo > curr_mo):
                            df_multi.at[i, (m_name, "Total KM")] = ""
                            df_multi.at[i, (m_name, "Total Trips")] = ""
                            df_multi.at[i, (m_name, "WS Days")] = ""
                            df_multi.at[i, (m_name, "Avg Days/Trip")] = ""
                        else:
                            if not row_data.empty:
                                r = row_data.iloc[0]
                                df_multi.at[i, (m_name, "Total KM")] = int(r["Mileage"])
                                df_multi.at[i, (m_name, "Total Trips")] = int(r["Total Trips"])
                                df_multi.at[i, (m_name, "WS Days")] = int(r["Workshop Days"])
                                df_multi.at[i, (m_name, "Avg Days/Trip")] = f"{r['Avg Days/Trip']:.2f}"
                                
                                ytd_km += int(r["Mileage"])
                                
                                if m_yr > 2026 or (m_yr == 2026 and m_mo >= 4):
                                    ytd_trips_for_avg += int(r["Total Trips"])
                                    
                                if m_yr > 2026 or (m_yr == 2026 and m_mo >= 5):
                                    ytd_ws += int(r["Workshop Days"])
                                    ytd_net += int(r["Net Available Days"])
                                    ytd_trips_for_true_net += int(r["Total Trips"])
                            else:
                                df_multi.at[i, (m_name, "Total KM")] = 0
                                df_multi.at[i, (m_name, "Total Trips")] = 0
                                df_multi.at[i, (m_name, "WS Days")] = 0
                                df_multi.at[i, (m_name, "Avg Days/Trip")] = "0.00"

                    true_avg_days_trip = ytd_net / ytd_trips_for_true_net if ytd_trips_for_true_net > 0 else 0.0
                    
                    df_multi.at[i, ("YTD Averages", "Avg KM/mo")] = f"{ytd_km/km_divisor:,.0f}" if km_divisor > 0 else "0"
                    df_multi.at[i, ("YTD Averages", "Avg Trips/mo")] = f"{ytd_trips_for_avg/trips_divisor:.1f}" if trips_divisor > 0 else "0.0"
                    df_multi.at[i, ("YTD Averages", "Avg WS/mo")] = f"{ytd_ws/ws_divisor:.1f}" if ws_divisor > 0 else "0.0"
                    df_multi.at[i, ("YTD Averages", "TRUE Avg Days/Trip")] = f"{true_avg_days_trip:.2f}"

                st.success("✅ Analytics Engine Complete!")
                
                # --- NEW TAB LAYOUT ---
                tab1, tab2, tab3, tab4 = st.tabs(["📅 Current Month", "📈 Yearly Trends", "🗓️ YTD Tracker", "📍 Destination Analytics"])
                
                # --- TAB 1 ---
                with tab1:
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total Trips", int(current_total_trips))
                    m2.metric("Total WS Days", int(df_tab1["Workshop Days"].sum()))
                    m3.metric("Net Available Days", int(current_net_days))
                    m4.metric("Avg Days/Trip", current_fleet_avg)
                    m5.metric("Total Fleet KM", f"{int(current_total_kms):,}")
                    
                    st.write("---")
                    sc1, sc2 = st.columns([2, 1])
                    with sc1: sort_col_tab1 = st.selectbox("Sort Table By:", df_tab1.columns.tolist(), index=df_tab1.columns.tolist().index("Avg Days per Trip"))
                    with sc2: sort_asc_tab1 = st.radio("Order:", ["Ascending", "Descending"], horizontal=True, key="sort1") == "Ascending"
                    
                    df_tab1 = df_tab1.sort_values(by=sort_col_tab1, ascending=sort_asc_tab1)
                    
                    def color_traffic_light(val):
                        try:
                            v = float(val)
                            if v == 0.0: return 'background-color: #f8d7da; color: #721c24;'
                            elif v < 1.7: return 'background-color: #d4edda; color: #155724;'
                            elif 1.7 <= v < 1.9: return 'background-color: #fff3cd; color: #856404;'
                            else: return 'background-color: #f8d7da; color: #721c24;'
                        except: return ''

                    try:
                        styled_df = df_tab1.style.map(color_traffic_light, subset=["Avg Days per Trip"]).format({"Avg Days per Trip": "{:.2f}"})
                    except AttributeError:
                        styled_df = df_tab1.style.applymap(color_traffic_light, subset=["Avg Days per Trip"]).format({"Avg Days per Trip": "{:.2f}"})
                        
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    
                    c_btn1, c_btn2 = st.columns(2)
                    with c_btn1: st.download_button("⬇️ Download Monthly CSV", data=df_tab1.to_csv(index=False).encode('utf-8'), file_name=f"logistics_{current_month_str}.csv", mime="text/csv", use_container_width=True)
                    with c_btn2: st.download_button("📄 Generate Monthly PDF Report", data=bytes(generate_monthly_pdf(df_tab1, current_month_str)), file_name=f"ZPC_Report_{current_month_str}.pdf", mime="application/pdf", use_container_width=True, type="primary")

                # --- TAB 2 ---
                with tab2:
                    if monthly_totals:
                        months_labels = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
                        y_2025 = [monthly_totals.get(f"2025-{m}", 0) for m in months_labels]
                        y_2026 = [monthly_totals.get(f"2026-{m}", 0) for m in months_labels]

                        fig, ax = plt.subplots(figsize=(10, 4))
                        bar_width = 0.35
                        x = range(len(months_labels))
                        bars1 = ax.bar([i - bar_width/2 for i in x], y_2025, bar_width, label='2025', color='#2ca02c')
                        bars2 = ax.bar([i + bar_width/2 for i in x], y_2026, bar_width, label='2026', color='#d62728')
                        add_bar_labels(ax, bars1)
                        add_bar_labels(ax, bars2)
                        ax.set_title('2026 vs 2025 Total kms')
                        ax.set_xticks(x)
                        ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec'])
                        ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda val, loc: f"{int(val):,}"))
                        ax.margins(y=0.2) 
                        ax.legend()
                        st.pyplot(fig)
                    
                    st.dataframe(df_yearly.style.format({"Avg Days/Trip": "{:.2f}"}), use_container_width=True, hide_index=True)
                    
                    c_btn3, c_btn4 = st.columns(2)
                    with c_btn3: st.download_button("⬇️ Download Yearly CSV", data=df_yearly.to_csv(index=False).encode('utf-8'), file_name="yearly_fleet.csv", mime="text/csv", use_container_width=True)
                    with c_btn4: st.download_button("📄 Generate Yearly PDF Report", data=bytes(generate_yearly_pdf(df_yearly, monthly_totals)), file_name="ZPC_Yearly_Report.pdf", mime="application/pdf", use_container_width=True, type="primary")
                
                # --- TAB 3 ---
                with tab3:
                    st.subheader(f"{curr_yr} Year-to-Date Performance Matrix")
                    st.write("---")
                    sc3, sc4 = st.columns([2, 1])
                    
                    ytd_sort_tuples = [
                        ("YTD Averages", "Avg KM/mo"),
                        ("YTD Averages", "Avg Trips/mo"),
                        ("YTD Averages", "Avg WS/mo"),
                        ("YTD Averages", "TRUE Avg Days/Trip")
                    ]
                    
                    readable_cols = [f"YTD {c[1]}" for c in ytd_sort_tuples]
                    
                    with sc3: 
                        selected_readable_col = st.selectbox("Sort Matrix By:", readable_cols, index=3)
                    with sc4: 
                        sort_asc_tab3 = st.radio("Order:", ["Ascending", "Descending"], horizontal=True, key="sort3") == "Ascending"
                    
                    actual_sort_tuple = ytd_sort_tuples[readable_cols.index(selected_readable_col)]
                    
                    def safe_float(x):
                        if isinstance(x, str):
                            if x == "": return -1 
                            return float(x.replace(',', ''))
                        return float(x)
                        
                    temp_sort_series = df_multi[actual_sort_tuple].apply(safe_float)
                    df_multi = df_multi.iloc[temp_sort_series.argsort()]
                    if not sort_asc_tab3:
                        df_multi = df_multi[::-1]
                    
                    avg_cols = [(m, "Avg Days/Trip") for m in month_names] + [("YTD Averages", "TRUE Avg Days/Trip")]
                    
                    try:
                        styled_matrix = df_multi.style.map(color_traffic_light, subset=avg_cols)
                    except AttributeError:
                        styled_matrix = df_multi.style.applymap(color_traffic_light, subset=avg_cols)
                        
                    st.dataframe(styled_matrix, use_container_width=True, hide_index=True)
                    
                    c_btn5, c_btn6 = st.columns(2)
                    
                    df_csv_export = df_multi.copy()
                    df_csv_export.columns = [' '.join(col).strip() for col in df_csv_export.columns.values]
                    
                    with c_btn5: st.download_button(label="⬇️ Download YTD Matrix CSV", data=df_csv_export.to_csv(index=False).encode('utf-8'), file_name=f"{curr_yr}_YTD_Tracker.csv", mime="text/csv", use_container_width=True)
                    with c_btn6: st.download_button(label="📄 Generate A2 Landscape PDF", data=bytes(generate_ytd_tracker_pdf(df_multi, current_month_str)), file_name="ZPC_YTD_Matrix.pdf", mime="application/pdf", use_container_width=True, type="primary")

                # --- TAB 4: DESTINATIONS ---
                with tab4:
                    st.subheader(f"📍 Route Frequency Breakdown ({current_month_str})")
                    if not dest_col_name:
                        st.warning("⚠️ Could not find a destination column in the uploaded Trips file. Please ensure it has a column named 'Destination', 'Location', 'Site', or 'Route'.")
                    
                    st.write("---")
                    sc5, sc6 = st.columns([2, 1])
                    with sc5: sort_col_tab4 = st.selectbox("Sort Table By:", ["Total Trips", "Current Month KM", "Workshop Days", "Truck"], index=0, key="sort4_col")
                    with sc6: sort_asc_tab4 = st.radio("Order:", ["Ascending", "Descending"], horizontal=True, key="sort4_order") == "Ascending"
                    
                    df_tab4["Total Trips"] = pd.to_numeric(df_tab4["Total Trips"], errors='coerce').fillna(0)
                    df_tab4["Current Month KM"] = pd.to_numeric(df_tab4["Current Month KM"], errors='coerce').fillna(0)
                    df_tab4["Workshop Days"] = pd.to_numeric(df_tab4["Workshop Days"], errors='coerce').fillna(0)

                    df_tab4 = df_tab4.sort_values(by=sort_col_tab4, ascending=sort_asc_tab4).reset_index(drop=True)
                    
                    df_tab4["Total Trips"] = df_tab4["Total Trips"].astype(int)
                    df_tab4["Current Month KM"] = df_tab4["Current Month KM"].astype(int)
                    df_tab4["Workshop Days"] = df_tab4["Workshop Days"].astype(int)

                    st.dataframe(df_tab4, use_container_width=True, hide_index=True)
                    
                    c_btn7, c_btn8 = st.columns(2)
                    with c_btn7: st.download_button("⬇️ Download Destination CSV", data=df_tab4.to_csv(index=False).encode('utf-8'), file_name=f"destinations_{current_month_str}.csv", mime="text/csv", use_container_width=True)
                    with c_btn8: st.download_button("📄 Generate Destination PDF Report", data=bytes(generate_destinations_pdf(df_tab4, current_month_str)), file_name=f"ZPC_Destinations_{current_month_str}.pdf", mime="application/pdf", use_container_width=True, type="primary")

    except Exception as e:
        st.error(f"❌ Error: {e}")
