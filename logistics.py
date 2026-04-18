import streamlit as st
import pandas as pd
import plotly.express as px

st.title("🚛 Miloto Live Fleet Performance")

st.info("Upload your daily Trips file here. This runs independently of your maintenance data.")

# Add 'xlsx' to the accepted file types
uploaded_file = st.file_uploader("Upload Daily Miloto Trips Data", type=["csv", "xlsx"])

@st.cache_data
def load_data(file):
    # Check file type and read accordingly
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    
    # Filter for Miloto Transport only
    df = df[df['Transport Company'].str.contains('MILOTO', case=False, na=False)].copy()
    
    # ==========================================
    # THE CORRECTION DICTIONARY (Fix typos here)
    # ==========================================
    corrections = {
        "BCB1316": "MILOTO-83(MTL83)",
        # To add future fixes, add them on a new line below like this:
        # "WRONG TYPO": "CORRECT NAME",
    }
    
    # Apply the corrections to the Identity column
    df['Identity'] = df['Identity'].replace(corrections)
    # ==========================================
    
    # Exclude dedicated local trucks (30, 48, 107)
    exclude_pattern = r'(MILOTO|MTL)-?(30|48|107)\b'
    df = df[~df['Identity'].str.contains(exclude_pattern, regex=True, na=False)]
    
    # Format dates
    df['DOT'] = pd.to_datetime(df['DOT'], format='%d-%m-%Y')
    df = df.sort_values(by=['Identity', 'DOT'])
    
    return df

if uploaded_file is not None:
    # Load the data
    df = load_data(uploaded_file)

    # ==========================================
    # LOGIC: Calendar Days / Total Trips
    # ==========================================
    
    # 1. Automatically find how many days into the month we are
    max_date = df['DOT'].max()
    total_calendar_days = max_date.day 
    
    # 2. Count total trips per truck
    truck_stats = df.groupby('Identity').agg(
        Total_Trips=('DOT', 'count')
    ).reset_index()

    # 3. Calculate Average Days per Trip (Calendar Days / Trips)
    truck_stats['Avg_Days'] = total_calendar_days / truck_stats['Total_Trips']

    # 4. Calculate True Fleet Averages
    fleet_avg_trips = truck_stats['Total_Trips'].mean()
    fleet_avg_days = total_calendar_days / fleet_avg_trips

    # ==========================================

    # Top Level KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("Month-to-Date Days", f"{total_calendar_days} Days")
    col2.metric("Fleet Avg Turnaround", f"{fleet_avg_days:.2f} Days")
    col3.metric("Fleet Avg Trips (MTD)", f"{fleet_avg_trips:.1f} Trips")

    st.divider()

    # Live Leaderboard
    st.subheader("🏆 Live Truck Leaderboard")
    truck_stats['Performance vs Fleet'] = truck_stats['Avg_Days'] - fleet_avg_days
    truck_stats = truck_stats.sort_values('Avg_Days', ascending=True).dropna()

    st.dataframe(
        truck_stats.style.format({"Avg_Days": "{:.2f}", "Performance vs Fleet": "{:.2f}"})
        .background_gradient(subset=['Avg_Days'], cmap="RdYlGn_r"),
        use_container_width=True
    )

    # Destination Breakdown Viewer
    st.subheader("📍 Destination Breakdown per Truck")
    selected_truck_routes = st.selectbox("Select a truck to view its routes:", truck_stats['Identity'].unique(), key="route_select")

    if selected_truck_routes:
        truck_data = df[df['Identity'] == selected_truck_routes]
        dest_counts = truck_data['Destination'].value_counts().reset_index()
        dest_counts.columns = ['Destination', 'Trips']
        
        st.dataframe(dest_counts, hide_index=True, use_container_width=True)

    st.divider()

    # Isolated Performance Tracker 
    st.subheader("🎯 Individual Performance vs Fleet")
    st.markdown("Isolate a truck to compare its performance against the fleet averages without the clutter.")

    # Calculate cumulative trips for the background data
    daily_trips = df.groupby(['DOT', 'Identity']).size().reset_index(name='Trips')
    daily_trips['Cumulative_Trips'] = daily_trips.groupby('Identity')['Trips'].cumsum()

    # Dropdown to select the specific truck to analyze
    compare_truck = st.selectbox("Select Truck to Analyze:", sorted(df['Identity'].unique()), key="compare_truck_select")

    if compare_truck:
        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            # --- Chart 1: Speed (Avg Days per Trip) ---
            truck_avg = truck_stats[truck_stats['Identity'] == compare_truck]['Avg_Days'].values[0]
            
            # Create a simple comparison dataframe
            speed_df = pd.DataFrame({
                "Metric": [compare_truck, "Fleet Average"],
                "Days": [truck_avg, fleet_avg_days]
            })
            
            # Bar chart comparing the two numbers
            fig_speed = px.bar(speed_df, x="Metric", y="Days", color="Metric",
                               title="Average Turnaround Speed (Lower is Better)",
                               color_discrete_sequence=["#FF4B4B", "#1f77b4"])
            
            # Add a horizontal line to easily see the fleet average across the truck's bar
            fig_speed.add_hline(y=fleet_avg_days, line_dash="dot", line_color="white", opacity=0.5)
            st.plotly_chart(fig_speed, use_container_width=True)

        with col_chart2:
            # --- Chart 2: Volume (Cumulative Trips over time) ---
            truck_daily = daily_trips[daily_trips['Identity'] == compare_truck]
            
            # Line chart showing just the selected truck's progress
            fig_vol = px.line(truck_daily, x='DOT', y='Cumulative_Trips', markers=True,
                              title="Trips Completed This Month",
                              color_discrete_sequence=["#2ecc71"])
            
            # Add the target line for the current Fleet MTD Average
            fig_vol.add_hline(y=fleet_avg_trips, line_dash="dot", annotation_text="Current Fleet Average", line_color="#FF4B4B")
            
            # Lock the Y-axis based on the top performing truck
            max_y = max(daily_trips['Cumulative_Trips'].max(), fleet_avg_trips) + 1
            fig_vol.update_layout(yaxis_range=[0, max_y])
            
            st.plotly_chart(fig_vol, use_container_width=True)