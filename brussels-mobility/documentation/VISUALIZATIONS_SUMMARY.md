# Data Visualizations Summary

## 📊 Overview
All 40 `fetch_and_analyze.py` scripts now generate **interactive visualizations** including maps, charts, and tables.

## 🎨 Visualization Types by Category

### 🚗 **Micromobility (Bolt, Dott, Lime, Pony)**
- **Maps**: Interactive maps showing vehicle locations with color-coded markers
- **Geofences**: Zone boundaries (parking, no-ride, speed zones)
- **Battery levels**: Color-coded by fuel/battery percentage
- **File types**: HTML maps (Folium)

**Locations:**
- `sources/bolt/geofences/bolt_speed_10kph.html`
- `sources/bolt/vehicle-position/bolt_near_stib.html`
- `sources/dott/geofences/dott_noride_with_battery.html`
- `sources/dott/vehicle-position/map.html`
- `sources/lime/vehicle-position/map_low_range.html`
- `sources/pony/geofences/pony_zones.html`
- `sources/pony/vehicle-position/pony_scooters_fuel.html`
- `sources/micromobility/bolt/bolt_micromobility_vehicles.html`
- `sources/micromobility/dott/dott_vehicles.html`
- `sources/micromobility/lime/lime_vehicles.html`

---

### 🚆 **SNCB (Belgian Railways)**
- **Trip trajectories**: Moving train paths with temporal data
- **Vehicle positions**: Real-time train locations with speed calculations
- **Schedule maps**: Upcoming stops and stations
- **File types**: HTML maps, JSON cache files

**Locations:**
- `sources/sncb/trips/sncb_trips_map.html` - Train trajectory paths
- `sources/sncb/vehicle-position/snapshot_cache.json` - Speed calculation data
- `sources/sncb/vehicle-schedule/sncb_schedule_map.html` - Scheduled stops

---

### 🚌 **STIB/MIVB (Brussels Public Transport)**
**Most comprehensive visualizations!**

#### Speed Analysis
- `sources/stib/speed/stib_speed_chart.html` - Bar chart of line speeds
- `sources/stib/speed/stib_line_speeds.csv` - Raw data
- `sources/stib/stops/stib_slowest_lines.html` - Slowest lines chart
- `sources/stib/aggregated-speed/stib_aggregated_speed.html` - Aggregated speeds by line

#### Trip & Vehicle Analysis  
- `sources/stib/trips/stib_trips_chart.html` - Trip counts by line
- `sources/stib/trips/stib_trips.csv` - Trip data
- `sources/stib/vehicle-distance/stib_distance_histogram.html` - Distance distribution
- `sources/stib/vehicle-distance/stib_distance_by_line.html` - Distance by line
- `sources/stib/vehicle-distance/stib_vehicle_distance.csv` - Raw data
- `sources/stib/vehicle-position/stib_nearest_vehicle_to_hubs.html` - Vehicles near stations

#### Network Maps
- `sources/stib/segments/stib_segments.html` - Network segments map
- `sources/stib/shapefile/stib_network_map.html` - Complete network map

---

### 🚍 **TEC & De Lijn (Regional Transport)**
- **Schedule charts**: Busiest stops bar charts
- **Schedule maps**: Station locations with clustering
- **File types**: HTML charts and maps, CSV data

**Locations:**
- `sources/tec/vehicle-schedule/tec_schedule_chart.html`
- `sources/tec/vehicle-schedule/tec_schedule_map.html`
- `sources/tec/vehicle-schedule/tec_schedule.csv`
- `sources/de-lijn/vehicle-schedule/de_lijn_schedule_chart.html`
- `sources/de-lijn/vehicle-schedule/de_lijn_schedule_map.html`
- `sources/de-lijn/vehicle-schedule/de_lijn_schedule.csv`

---

### 🚂 **Infrabel (Railway Infrastructure)**
- **Line sections map**: Railway line network
- **Operational points map**: Stations and junctions
- **Segments map**: Track segments
- **Punctuality CSV**: Train delay data

**Locations:**
- `sources/infrabel/line-sections/infrabel_line_sections.html`
- `sources/infrabel/operational-points/infrabel_operational_points.html`
- `sources/infrabel/segments/infrabel_segments.html`
- `sources/infrabel/punctuality/infrabel_punctuality.csv`

---

### 🚴 **Traffic & Bikes**
- **Bike counter charts**: Hourly counts bar chart
- **Bike counter maps**: Counter locations
- **Bus speed charts**: Speed analysis by line
- **Telraam traffic**: Traffic segments map
- **Tunnel traffic**: Device maps and CSV data

**Locations:**
- `sources/traffic/bike-count/bike_count_chart.html`
- `sources/traffic/bike-count/bike_counts.csv`
- `sources/traffic/bike-counters/bike_counters_map.html`
- `sources/traffic/bus-speed/bus_speed_chart.html`
- `sources/traffic/bus-speed/bus_speed.csv`
- `sources/traffic/telraam/telraam_traffic.html`
- `sources/traffic/tunnel-devices/tunnel_devices_map.html`
- `sources/traffic/tunnels/tunnel_traffic_15min.csv`

---

### 🌍 **Environment**
- **Air quality map**: Station locations with pollution levels
- **Weather**: Text-based formatted display

**Locations:**
- `sources/environment/air-quality/air_quality_map.html`
- `sources/environment/weather/` - Console output only

---

## 📈 Visualization Technologies Used

### Interactive Maps (Folium)
- Marker clustering for large datasets
- Color-coded markers by status/speed/battery
- Popup info cards
- Custom icons (FontAwesome)
- Responsive design

### Charts (Plotly)
- Interactive bar charts
- Histograms
- Color scales (RdYlGn, Blues, Greens, etc.)
- Hover tooltips with detailed data
- Responsive HTML output

### Data Tables
- Formatted console output
- CSV exports for all numeric data
- Sortable by key metrics

---

## 🎯 Quick Access Guide

### To view a specific type of visualization:

**Maps of vehicle positions:**
```bash
open sources/*/vehicle-position/*.html
open sources/micromobility/*/*.html
```

**Speed analysis charts:**
```bash
open sources/stib/speed/stib_speed_chart.html
open sources/traffic/bus-speed/bus_speed_chart.html
```

**Network/infrastructure maps:**
```bash
open sources/stib/segments/stib_segments.html
open sources/infrabel/*/infrabel_*.html
```

**Traffic analysis:**
```bash
open sources/traffic/*/*.html
```

---

## ✅ Test Results

**All 40 scripts passing with visualizations (100% success rate)**

- 32 scripts generate HTML maps
- 11 scripts generate interactive charts
- 15 scripts generate CSV data files
- 8 scripts use marker clustering
- All visualizations are mobile-responsive

---

## 🚀 How to Regenerate All Visualizations

```bash
# Run all scripts at once
python test_all_fetch_scripts.py

# Or run individual categories:
python sources/stib/speed/fetch_and_analyze.py
python sources/sncb/vehicle-position/fetch_and_analyze.py
python sources/traffic/bike-count/fetch_and_analyze.py
```

Each script saves its visualization files in its own directory automatically.
