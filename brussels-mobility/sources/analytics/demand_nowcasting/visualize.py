"""
Visualization functions for micromobility demand nowcasting.

This module creates interactive HTML maps showing demand forecasts and 
rebalancing recommendations, plus CSV exports of forecast data.
"""

from typing import List, Dict
import pandas as pd
import numpy as np

try:
    import folium
    from folium import plugins
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
    print("Warning: folium not available. Map visualization will be skipped.")


def build_forecast_map(
    forecast_df: pd.DataFrame,
    moves: List[Dict],
    output_html_path: str
) -> None:
    """
    Build an interactive Folium map showing demand forecast heatmap and rebalancing arrows.
    
    Args:
        forecast_df: DataFrame with columns:
            - cell_id
            - lat (cell centroid latitude)
            - lon (cell centroid longitude)
            - predicted_demand_30m
            - available_vehicles
            - projected_remaining
        moves: List of rebalancing move dicts from plan_rebalancing()
        output_html_path: Path to save the HTML map
    """
    if not FOLIUM_AVAILABLE:
        print(f"Skipping map generation: folium not available")
        return
    
    if forecast_df.empty:
        print(f"Skipping map generation: no forecast data")
        return
    
    # Calculate map center
    center_lat = forecast_df['lat'].median()
    center_lon = forecast_df['lon'].median()
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles='OpenStreetMap'
    )
    
    # Add demand heatmap layer
    # Use predicted_demand_30m as intensity, but also show shortage areas
    heat_data = []
    for _, row in forecast_df.iterrows():
        # Intensity based on demand or shortage severity
        if pd.notna(row.get('predicted_demand_30m', 0)):
            intensity = max(row['predicted_demand_30m'], 0)
            # Boost intensity for shortage cells (projected_remaining < 0)
            if row.get('projected_remaining', 0) < 0:
                intensity = max(intensity, abs(row['projected_remaining']) * 2)
            
            if intensity > 0:
                heat_data.append([row['lat'], row['lon'], intensity])
    
    if heat_data:
        plugins.HeatMap(
            heat_data,
            name='Demand Forecast',
            min_opacity=0.3,
            max_opacity=0.8,
            radius=15,
            blur=20,
            gradient={
                0.0: 'blue',
                0.5: 'yellow',
                0.75: 'orange',
                1.0: 'red'
            }
        ).add_to(m)
    
    # Add cell markers with detailed info
    for _, row in forecast_df.iterrows():
        # Determine marker color based on projected remaining
        proj_rem = row.get('projected_remaining', 0)
        if proj_rem < 0:
            color = 'red'
            icon = 'arrow-down'
            status = 'DEFICIT'
        elif proj_rem > 5:
            color = 'green'
            icon = 'arrow-up'
            status = 'SURPLUS'
        else:
            color = 'blue'
            icon = 'pause'
            status = 'BALANCED'
        
        # Create popup with detailed info
        popup_html = f"""
        <b>Cell:</b> {row['cell_id']}<br>
        <b>Status:</b> {status}<br>
        <b>Available Now:</b> {row.get('available_vehicles', 0):.0f} vehicles<br>
        <b>Predicted Demand (30m):</b> {row.get('predicted_demand_30m', 0):.1f}<br>
        <b>Projected Remaining:</b> {proj_rem:.1f}<br>
        """
        
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=folium.Popup(popup_html, max_width=250),
            icon=folium.Icon(color=color, icon=icon, prefix='fa'),
            tooltip=f"{row['cell_id']}: {status}"
        ).add_to(m)
    
    # Add rebalancing arrows
    if moves:
        # Create a lookup dict for cell centroids
        cell_coords = forecast_df.set_index('cell_id')[['lat', 'lon']].to_dict('index')
        
        for move in moves:
            from_id = move['from_cell_id']
            to_id = move['to_cell_id']
            count = move['count']
            distance = move['distance_m']
            
            # Get coordinates
            if from_id in cell_coords and to_id in cell_coords:
                from_lat = cell_coords[from_id]['lat']
                from_lon = cell_coords[from_id]['lon']
                to_lat = cell_coords[to_id]['lat']
                to_lon = cell_coords[to_id]['lon']
                
                # Draw arrow as polyline with arrowhead
                folium.PolyLine(
                    locations=[[from_lat, from_lon], [to_lat, to_lon]],
                    color='purple',
                    weight=3,
                    opacity=0.7,
                    popup=f"<b>Rebalancing Move</b><br>Move {count} vehicle(s)<br>Distance: {distance:.0f}m",
                    tooltip=f"Move {count} vehicles ({distance:.0f}m)"
                ).add_to(m)
                
                # Add arrowhead marker at destination
                folium.RegularPolygonMarker(
                    location=[to_lat, to_lon],
                    fill_color='purple',
                    number_of_sides=3,
                    radius=8,
                    rotation=_calculate_bearing(from_lat, from_lon, to_lat, to_lon),
                    popup=f"Destination: {to_id}"
                ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Save map
    m.save(output_html_path)
    print(f"Map saved to: {output_html_path}")


def export_forecast_csv(forecast_df: pd.DataFrame, output_csv_path: str) -> None:
    """
    Export forecast data to CSV for further analysis.
    
    Args:
        forecast_df: DataFrame with forecast columns
        output_csv_path: Path to save the CSV file
    """
    # Select and order columns for export
    export_cols = [
        'cell_id',
        'lat',
        'lon',
        'available_vehicles',
        'predicted_demand_30m',
        'projected_remaining'
    ]
    
    # Add shortage column
    output_df = forecast_df.copy()
    output_df['shortage_if_any'] = output_df['projected_remaining'].apply(
        lambda x: abs(x) if x < 0 else 0
    )
    
    export_cols.append('shortage_if_any')
    
    # Filter to only include columns that exist
    available_cols = [col for col in export_cols if col in output_df.columns]
    
    # Round numeric columns for readability
    numeric_cols = output_df[available_cols].select_dtypes(include=[np.number]).columns
    output_df[numeric_cols] = output_df[numeric_cols].round(2)
    
    # Export to CSV
    output_df[available_cols].to_csv(output_csv_path, index=False)
    print(f"Forecast CSV saved to: {output_csv_path}")


def _calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing between two points for arrow rotation.
    
    Args:
        lat1, lon1: Start point coordinates
        lat2, lon2: End point coordinates
        
    Returns:
        Bearing in degrees
    """
    import math
    
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)
    
    # Calculate bearing
    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
    
    bearing = math.atan2(x, y)
    bearing_deg = math.degrees(bearing)
    
    return (bearing_deg + 360) % 360
