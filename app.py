import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="Technician Arrival Dashboard", layout="wide")

st.title("Technician Arrival Dashboard")
st.write("Track how well technicians arrive on time for their scheduled jobs")

# load data from working directory
def load_data():
    """Load schedule and GPS data from files"""
    schedules = None
    gps_data = None
        
    # paths
    script_dir = Path(__file__).parent

    schedule_path = script_dir / "schedule.csv"
    gps_path = script_dir / "gps.csv"
    
    # load Schedule.csv 
    try:
        schedules = pd.read_csv(schedule_path)
        st.sidebar.success("Loaded Schedule.csv from directory")
    except FileNotFoundError:
        st.sidebar.error("Schedule.csv not found in working directory")
    
    # load GPS.csv  
    try:
        gps_data = pd.read_csv(gps_path)
        st.sidebar.success("Loaded GPS.csv from directory")
    except FileNotFoundError:
        st.sidebar.error("GPS.csv not found in working directory")
    
    return schedules, gps_data

# helper function calculates distance between 2 points
def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate approximate distance in meters between two GPS points"""
    # Simple distance calculation (good enough for most use cases)
    lat_diff = lat1 - lat2
    lon_diff = lon1 - lon2
    distance_degrees = (lat_diff**2 + lon_diff**2)**0.5
    distance_meters = distance_degrees * 111000  # Convert to meters (approximate)
    return distance_meters

# find when technician actually arrived
def find_arrival_time(gps_data, tech_id, job_lat, job_lon, scheduled_time):
    """Find when a technician actually arrived at a job location"""
    
    # get GPS data for this technician around the scheduled time
    time_window_start = scheduled_time - pd.Timedelta(hours=2)
    time_window_end = scheduled_time + pd.Timedelta(hours=2)
    
    # filter GPS data
    tech_gps = gps_data[
        (gps_data['technician_id'] == tech_id) &
        (gps_data['timestamp'] >= time_window_start) &
        (gps_data['timestamp'] <= time_window_end)
    ]
    
    if tech_gps.empty:
        return None
    
    # find GPS points close to the job location
    tech_gps = tech_gps.copy()
    tech_gps['distance'] = tech_gps.apply(
        lambda row: calculate_distance(row['latitude'], row['longitude'], job_lat, job_lon),
        axis=1
    )
    
    # find first time they were close to the job
    close_points = tech_gps[tech_gps['distance'] <= 100]
    
    if not close_points.empty:
        return close_points['timestamp'].min()
    
    return None

# categorize how late/early someone was
def get_arrival_status(delay_minutes):
    """Categorize arrival status based on delay"""
    if pd.isna(delay_minutes):
        return 'No GPS Data'
    elif delay_minutes <= -5:
        return 'Early'
    elif delay_minutes <= 5:
        return 'On Time'
    elif delay_minutes <= 30:
        return 'Late'
    else:
        return 'Very Late'

# function to get colors for status
def get_status_color(status):
    """Get color for each status"""
    colors = {
        'Early': 'green',
        'On Time': 'lightgreen', 
        'Late': 'orange',
        'Very Late': 'red',
        'No GPS Data': 'gray'
    }
    return colors.get(status, 'gray')

# load the data 
schedules, gps_data = load_data()

if schedules is not None and gps_data is not None:
    try:
        # convert to datetime
        schedules['scheduled_start'] = pd.to_datetime(schedules['scheduled_start'])
        gps_data['timestamp'] = pd.to_datetime(gps_data['timestamp'])
        
        st.success("Data loaded successfully!")
        
        # show basic overview
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Jobs", len(schedules))
        with col2:
            st.metric("Technicians", schedules['technician_id'].nunique())
        with col3:
            st.metric("GPS Records", len(gps_data))
        
        # let user select technician
        all_technicians = sorted(schedules['technician_id'].unique())
        selected_techs = st.sidebar.multiselect(
            "Select Technicians", 
            all_technicians, 
            default=all_technicians[:5]
        )
        
        if selected_techs:
            # filter schedules for selected technicians
            filtered_schedules = schedules[schedules['technician_id'].isin(selected_techs)].copy()
            
            # show progress bar
            progress_bar = st.progress(0)
            st.write("Analyzing arrivals...")
            
            # find actual arrival times for each job
            actual_arrivals = []
            total_jobs = len(filtered_schedules)
            
            for i, (_, job) in enumerate(filtered_schedules.iterrows()):
                # Update progress
                progress_bar.progress((i + 1) / total_jobs)
                
                # find arrival when they actually arrived
                arrival_time = find_arrival_time(
                    gps_data,
                    job['technician_id'],
                    job['job_latitude'],
                    job['job_longitude'],
                    job['scheduled_start']
                )
                actual_arrivals.append(arrival_time)
            
            # add results to dataframe
            filtered_schedules['actual_arrival'] = actual_arrivals
            
            # Calculate delay in minutes
            filtered_schedules['delay_minutes'] = (
                (filtered_schedules['actual_arrival'] - filtered_schedules['scheduled_start'])
                .dt.total_seconds() / 60
            )
            
            # add status categories
            filtered_schedules['status'] = filtered_schedules['delay_minutes'].apply(get_arrival_status)
            
            # clear progress bar
            progress_bar.empty()
            st.success("Analysis complete!")
            
            # result tabs
            tab1, tab2, tab3 = st.tabs(["Summary", "Map", "Details"])
            
            with tab1:
                st.subheader("Arrival Performance Summary")
                
                status_counts = filtered_schedules['status'].value_counts()
                
                # metrics
                cols = st.columns(len(status_counts))
                for i, (status, count) in enumerate(status_counts.items()):
                    with cols[i]:
                        percentage = (count / len(filtered_schedules)) * 100
                        st.metric(status, f"{count} ({percentage:.1f}%)")
                
                # status barchat
                fig_bar = px.bar(
                    x=status_counts.index,
                    y=status_counts.values,
                    color=status_counts.index,
                    color_discrete_map={status: get_status_color(status) for status in status_counts.index},
                    title="Arrival Status Distribution"
                )
                fig_bar.update_layout(
                    showlegend=False,
                    xaxis_title="Arrival Status",
                    yaxis_title="Number of Jobs"
                )
                st.plotly_chart(fig_bar, use_container_width=True)
                
                # show delay stat
                valid_delays = filtered_schedules['delay_minutes'].dropna()
                if not valid_delays.empty:
                    st.subheader("Delay Statistics")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Average Delay", f"{valid_delays.mean():.1f} minutes")
                    with col2:
                        st.metric("Worst Delay", f"{valid_delays.max():.1f} minutes")
                    with col3:
                        st.metric("Best (Early)", f"{valid_delays.min():.1f} minutes")
            
            with tab2:
                st.subheader("Job Locations on Map")
                
                # map showing job locations with status
                fig_map = px.scatter_mapbox(
                    filtered_schedules,
                    lat="job_latitude",
                    lon="job_longitude",
                    color="status",
                    color_discrete_map={status: get_status_color(status) for status in filtered_schedules['status'].unique()},
                    hover_data=['technician_id', 'job_id', 'delay_minutes'],
                    zoom=10,
                    height=600
                )
                fig_map.update_layout(mapbox_style="open-street-map")
                st.plotly_chart(fig_map, use_container_width=True)
            
            with tab3:
                st.subheader("Detailed Results")
                
                # show the data table
                display_columns = [
                    'technician_id', 'job_id', 'scheduled_start', 
                    'actual_arrival', 'delay_minutes', 'status'
                ]
                
                st.dataframe(
                    filtered_schedules[display_columns].sort_values('scheduled_start'),
                    use_container_width=True
                )
                
                # download data
                csv_data = filtered_schedules.to_csv(index=False)
                st.download_button(
                    "Download Results",
                    csv_data,
                    f"arrival_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
                    "text/csv"
                )
        
        else:
            st.warning("Please select at least one technician to analyze.")
    
    except Exception as e:
        st.error(f"Error processing data: {str(e)}")