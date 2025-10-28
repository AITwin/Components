# Fetch and Analyze Scripts Documentation

This document provides comprehensive documentation for all `fetch_and_analyze.py` scripts in the MobilityTwin Brussels API data collection workspace. Each script fetches data from specific API endpoints, performs analysis, and generates visualizations or reports.

## Table of Contents

1. [Micromobility Providers](#micromobility-providers)
   - [Bolt](#bolt)
   - [Dott](#dott)
   - [Lime](#lime)
   - [Pony](#pony)
2. [Public Transport](#public-transport)
   - [STIB/MIVB](#stibmivb)
   - [SNCB](#sncb)
   - [De Lijn](#de-lijn)
   - [TEC](#tec)
3. [Railway Infrastructure](#railway-infrastructure)
   - [Infrabel](#infrabel)
4. [Traffic & Cycling](#traffic--cycling)
5. [Environment](#environment)
6. [Unified Micromobility](#unified-micromobility)

---

## Micromobility Providers

### Bolt

#### 1. Bolt Vehicle Position (`sources/bolt/vehicle-position/fetch_and_analyze.py`)

**Purpose:** Finds Bolt e-scooters located within 50 meters of STIB public transport stops.

**Data Sources:**
- `https://api.mobilitytwin.brussels/bolt/vehicle-position` - Live Bolt scooter locations
- `https://api.mobilitytwin.brussels/stib/stops` - STIB stop locations

**Analysis:**
- Converts GeoDataFrames to metric CRS (EPSG:3812) for accurate distance calculations
- Uses spatial join to find vehicles within 50m of stops
- Links each scooter to its nearest STIB stop

**Output:**
- **File:** `bolt_near_stib.html`
- **Visualization:** Interactive Folium map with:
  - Purple circle markers for Bolt vehicles
  - Red circle markers for STIB stops
  - Thin lines connecting vehicles to their nearest stops
  - Popups showing bike ID and distance to stop
- **Console:** Count of matched vehicles

**Use Case:** Identifies first/last-mile mobility options near public transport hubs.

---

#### 2. Bolt Geofences (`sources/bolt/geofences/fetch_and_analyze.py`)

**Purpose:** Visualizes Bolt operational zones with speed restrictions ≤10 km/h.

**Data Source:**
- `https://api.mobilitytwin.brussels/bolt/geofences`

**Analysis:**
- Parses `rules` field (JSON array or string) containing speed limits
- Filters zones where `maximum_speed_kph` is between 0 and 10
- Extracts Polygon/MultiPolygon geometries

**Output:**
- **File:** `bolt_speed_10kph.html`
- **Visualization:** Map showing slow-speed zones with:
  - Translucent blue polygons for restricted areas
  - Tooltips displaying zone name and speed limit
  - Borders at zone boundaries
- **Console:** Count of slow zones found

**Use Case:** Identifies pedestrian-heavy areas or school zones with speed restrictions.

---

### Dott

#### 3. Dott Vehicle Position (`sources/dott/vehicle-position/fetch_and_analyze.py`)

**Purpose:** Maps all available Dott e-scooters with clustering for dense areas.

**Data Source:**
- `https://api.mobilitytwin.brussels/dott/vehicle-position`

**Analysis:**
- Extracts Point geometries from GeoJSON features
- Uses MarkerCluster for cleaner visualization in high-density zones

**Output:**
- **File:** `map.html`
- **Visualization:** Interactive map with:
  - Clustered markers (numbers show count in area)
  - Individual markers when zoomed in
  - Small circle markers (3px radius)
- **Console:** Confirmation message

**Use Case:** Overview of Dott fleet distribution across Brussels.

---

#### 4. Dott Geofences (`sources/dott/geofences/fetch_and_analyze.py`)

**Purpose:** Shows Dott no-ride zones and restricted areas.

**Data Source:**
- `https://api.mobilitytwin.brussels/dott/geofences`

**Analysis:**
- Filters zones where `ride_allowed = False`
- Parses Polygon/MultiPolygon geometries
- Identifies areas where scooter riding is prohibited

**Output:**
- **File:** `dott_no_ride.html`
- **Visualization:** Map with:
  - Red-shaded polygons for no-ride zones
  - Tooltips with zone names
  - Translucent fill (opacity 0.3) for visibility
- **Console:** Count of restricted zones

**Use Case:** Helps users understand where Dott scooters cannot be ridden (parks, pedestrian zones, etc.).

---

### Lime

#### 5. Lime Vehicle Position (`sources/lime/vehicle-position/fetch_and_analyze.py`)

**Purpose:** Identifies Lime scooters with critically low battery (<15% range).

**Data Source:**
- `https://api.mobilitytwin.brussels/lime/vehicle-position`

**Analysis:**
- Filters for `vehicle_type = "scooter"`
- Calculates battery percentage: `(current_range_meters / 60000) × 100`
- Identifies scooters below 15% threshold

**Output:**
- **File:** `map_low_range.html`
- **Visualization:** Map with:
  - Red circle markers for low-battery scooters
  - MarkerCluster for grouping
  - Popups showing remaining range in km and percentage
- **Console:** Success message or "No scooters under 15%" warning

**Use Case:** Fleet management - identifies vehicles needing recharge/battery swap.

---

### Pony

#### 6. Pony Vehicle Position (`sources/pony/vehicle-position/fetch_and_analyze.py`)

**Purpose:** Maps available Pony scooters with color-coded fuel levels.

**Data Source:**
- `https://api.mobilitytwin.brussels/pony/vehicle-position`

**Analysis:**
- Filters available scooters: `is_disabled = False`, `is_reserved = False`, `fuel ≥ 20%`
- Creates color gradient from red (low fuel) to green (high fuel)
- Falls back to showing all vehicles if none meet availability criteria

**Output:**
- **File:** `pony_scooters_fuel.html`
- **Visualization:** Full-screen map with:
  - Circle markers colored by fuel percentage (red → yellow → green gradient)
  - Color legend showing fuel level scale
  - Popups with bike ID, fuel %, and remaining range
  - Auto-fitted bounds to show all scooters
- **Console:** Count of available scooters

**Use Case:** Real-time fleet availability for users and operators.

---

#### 7. Pony Geofences (`sources/pony/geofences/fetch_and_analyze.py`)

**Purpose:** Visualizes Pony operational zones and service boundaries.

**Data Source:**
- `https://api.mobilitytwin.brussels/pony/geofences`

**Analysis:**
- Extracts Polygon/MultiPolygon geometries
- Displays all operational zones

**Output:**
- **File:** `pony_zones.html`
- **Visualization:** Map showing service areas with tooltips

**Use Case:** Understanding Pony's coverage area in Brussels.

---

## Public Transport

### STIB/MIVB

#### 8. STIB Vehicle Position (`sources/stib/vehicle-position/fetch_and_analyze.py`)

**Purpose:** Finds the nearest STIB vehicle (bus/tram/metro) to each major Brussels train station in real-time.

**Data Sources:**
- `https://api.mobilitytwin.brussels/stib/vehicle-position` - Live vehicle locations
- `https://api.mobilitytwin.brussels/stib/stops` - Stop locations for hub identification

**Analysis:**
- Identifies 3 major hubs using pattern matching:
  - Brussels-Central (Gare Centrale / Brussel-Centraal)
  - Brussels-Midi (Gare du Midi / Brussel-Zuid)
  - Brussels-North (Bruxelles-Nord / Brussel-Noord)
- Computes centroid of all platform variants for each hub
- Uses spatial distance calculation in metric CRS to find nearest vehicle
- Formats timestamps in Brussels timezone (Europe/Brussels)

**Output:**
- **File:** `stib_nearest_hubs.html`
- **Visualization:** Full-screen map with:
  - Grey dots for all STIB vehicles (line number tooltip)
  - Blue squares for train station hubs (name + distance popup)
  - Red triangular markers for the nearest vehicle to each hub
  - Lines connecting hubs to their nearest vehicles
  - Detailed popups showing route, destination, line color, timestamp
- **Console:** Summary table with hub names, nearest vehicle details, and distances

**Use Case:** Real-time intermodal connection monitoring between SNCB trains and STIB local transport.

---

#### 9. STIB GTFS (`sources/stib/gtfs/fetch_and_analyze.py`)

**Purpose:** Analyzes STIB schedule data to list all routes serving Brussels-Central station today.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/gtfs` (ZIP archive)

**Analysis:**
- Downloads and extracts GTFS ZIP file
- Reads: stops.txt, stop_times.txt, trips.txt, routes.txt, calendar.txt, calendar_dates.txt
- Identifies Brussels-Central stops using pattern matching
- Filters trips active today based on service calendar and exceptions
- Lists all routes (bus/tram/metro lines) calling at Central

**Output:**
- **File:** `stib_central_routes.txt`
- **Content:** Table showing:
  - Route short name (line number)
  - Route long name (full description)
  - Route ID
  - Route type (0=tram, 1=metro, 3=bus)
- **Console:** Formatted table with route details

**Use Case:** Daily schedule planning and route discovery for Brussels-Central.

---

#### 10. STIB Stops (`sources/stib/stops/fetch_and_analyze.py`)

**Purpose:** Maps all STIB stops with route information.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/stops`

**Analysis:**
- Extracts Point geometries for all stops
- Parses route information and stop names

**Output:**
- **File:** Interactive map with stop markers
- **Console:** Total stop count

---

#### 11. STIB Trips (`sources/stib/trips/fetch_and_analyze.py`)

**Purpose:** Analyzes trip patterns and service frequency.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/trips`

**Analysis:**
- Aggregates trips by route and time period
- Calculates service frequency

**Output:**
- **File:** CSV with trip statistics
- **Console:** Summary report

---

#### 12. STIB Segments (`sources/stib/segments/fetch_and_analyze.py`)

**Purpose:** Visualizes STIB route segments with LineString geometries.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/segments`

**Analysis:**
- Extracts LineString geometries for route segments
- Colors by route/line

**Output:**
- **File:** Map with route lines

---

#### 13. STIB Speed (`sources/stib/speed/fetch_and_analyze.py`)

**Purpose:** Analyzes STIB vehicle speeds by line and stop.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/speed`

**Analysis:**
- Calculates average speeds per line
- Identifies slowest segments

**Output:**
- **File:** CSV with speed statistics
- **Console:** Summary table

---

#### 14. STIB Shapefile (`sources/stib/shapefile/fetch_and_analyze.py`)

**Purpose:** Visualizes STIB network routes colored by official line colors.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/shapefile`

**Analysis:**
- Extracts shapefile geometries
- Applies line-specific colors from STIB branding

**Output:**
- **File:** Full network map with color-coded lines

---

#### 15. STIB Aggregated Speed (`sources/stib/aggregated-speed/fetch_and_analyze.py`)

**Purpose:** Fetches aggregated speed metrics for STIB vehicles.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/aggregated-speed`

**Analysis:**
- Handles both JSON object and array responses
- Extracts speed statistics

**Output:**
- **Console:** Speed data summary

---

#### 16. STIB Vehicle Distance (`sources/stib/vehicle-distance/fetch_and_analyze.py`)

**Purpose:** Calculates total distance traveled by STIB vehicles.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/vehicle-distance`

**Analysis:**
- Aggregates distance metrics by vehicle
- Calculates daily totals

**Output:**
- **File:** CSV with distance data

---

#### 17. STIB Vehicle Schedule (`sources/stib/vehicle-schedule/fetch_and_analyze.py`)

**Purpose:** Retrieves real-time schedule adherence data.

**Data Source:**
- `https://api.mobilitytwin.brussels/stib/vehicle-schedule`

**Analysis:**
- Compares scheduled vs actual arrival times
- Identifies delays

**Output:**
- **Console:** Schedule summary

---

### SNCB

#### 18. SNCB GTFS (`sources/sncb/gtfs/fetch_and_analyze.py`)

**Purpose:** Validates SNCB GTFS schedule data availability.

**Data Source:**
- `https://api.mobilitytwin.brussels/sncb/gtfs` (ZIP archive)

**Analysis:**
- Downloads GTFS ZIP file
- Lists contained files (stops.txt, routes.txt, etc.)
- Verifies data integrity

**Output:**
- **Console:** List of files in GTFS package
- **Message:** File count and sample filenames

**Use Case:** Data validation and schedule data exploration.

---

#### 19. SNCB GTFS-RT (`sources/sncb/gtfs-rt/fetch_and_analyze.py`)

**Purpose:** Fetches real-time train updates in GTFS-Realtime protobuf format.

**Data Source:**
- `https://api.mobilitytwin.brussels/sncb/gtfs-rt`

**Analysis:**
- Downloads protobuf binary data
- Shows byte count

**Output:**
- **Console:** Data size in bytes

**Use Case:** Real-time train tracking and delay monitoring.

---

#### 20. SNCB Trips (`sources/sncb/trips/fetch_and_analyze.py`)

**Purpose:** Retrieves train trip trajectories.

**Data Source:**
- `https://api.mobilitytwin.brussels/sncb/trips`

**Analysis:**
- Fetches trip data
- Counts available trips

**Output:**
- **Console:** Trip count

---

#### 21. SNCB Vehicle Position (`sources/sncb/vehicle-position/fetch_and_analyze.py`)

**Purpose:** Maps real-time positions of SNCB trains.

**Data Source:**
- `https://api.mobilitytwin.brussels/sncb/vehicle-position`

**Analysis:**
- Extracts train positions
- Shows train numbers and routes

**Output:**
- **File:** Map with train locations

---

#### 22. SNCB Vehicle Schedule (`sources/sncb/vehicle-schedule/fetch_and_analyze.py`)

**Purpose:** Fetches train schedules and displays sample data.

**Data Source:**
- `https://api.mobilitytwin.brussels/sncb/vehicle-schedule`

**Analysis:**
- Retrieves schedule data
- Shows formatted sample

**Output:**
- **Console:** Schedule sample

---

### De Lijn

#### 23. De Lijn Vehicle Schedule (`sources/de-lijn/vehicle-schedule/fetch_and_analyze.py`)

**Purpose:** Retrieves De Lijn (Flemish public transport) vehicle schedules.

**Data Source:**
- `https://api.mobilitytwin.brussels/de-lijn/vehicle-schedule`

**Analysis:**
- Fetches schedule data for buses
- Parses route and timing information

**Output:**
- **Console:** Schedule summary

---

### TEC

#### 24. TEC GTFS (`sources/tec/gtfs/fetch_and_analyze.py`)

**Purpose:** Validates TEC (Walloon public transport) GTFS schedule data.

**Data Source:**
- `https://api.mobilitytwin.brussels/tec/gtfs`

**Analysis:**
- Downloads GTFS ZIP
- Lists contained files

**Output:**
- **Console:** File listing

---

#### 25. TEC GTFS-Realtime (`sources/tec/gtfs-realtime/fetch_and_analyze.py`)

**Purpose:** Fetches TEC real-time updates.

**Data Source:**
- `https://api.mobilitytwin.brussels/tec/gtfs-realtime`

**Analysis:**
- Downloads protobuf data
- Shows size

**Output:**
- **Console:** Data size

---

#### 26. TEC Vehicle Schedule (`sources/tec/vehicle-schedule/fetch_and_analyze.py`)

**Purpose:** Retrieves TEC vehicle schedules.

**Data Source:**
- `https://api.mobilitytwin.brussels/tec/vehicle-schedule`

**Analysis:**
- Fetches schedule data
- Shows sample

**Output:**
- **Console:** Schedule sample

---

## Railway Infrastructure

### Infrabel

#### 27. Infrabel Line Sections (`sources/infrabel/line-sections/fetch_and_analyze.py`)

**Purpose:** Maps railway line sections managed by Infrabel (Belgian rail infrastructure).

**Data Source:**
- `https://api.mobilitytwin.brussels/infrabel/line-sections`

**Analysis:**
- Extracts LineString geometries for rail sections
- Shows section codes and names

**Output:**
- **File:** Map with railway lines
- **Console:** Section count

---

#### 28. Infrabel Operational Points (`sources/infrabel/operational-points/fetch_and_analyze.py`)

**Purpose:** Maps railway stations, junctions, and control points.

**Data Source:**
- `https://api.mobilitytwin.brussels/infrabel/operational-points`

**Analysis:**
- Extracts Point geometries
- Shows point names and types (station, junction, etc.)

**Output:**
- **File:** Map with operational point markers

---

#### 29. Infrabel Punctuality (`sources/infrabel/punctuality/fetch_and_analyze.py`)

**Purpose:** Analyzes Belgian train punctuality and delay statistics.

**Data Source:**
- `https://api.mobilitytwin.brussels/infrabel/punctuality`

**Analysis:**
- Parses arrival and departure delays (seconds → minutes)
- Calculates on-time performance (±5 minute threshold)
- Identifies most delayed trains (top 20)
- Computes average delays and overall statistics

**Output:**
- **File:** `infrabel_punctuality.csv` (full dataset)
- **Console:** Formatted report with:
  - Table of 20 most delayed arrivals (train number, service, station, planned time, delay)
  - Overall statistics: total trains, average delays, on-time percentage
- **Metrics:**
  - On-time = arrival delay between -1 and +5 minutes
  - Delays shown in minutes (converted from seconds)

**Use Case:** Performance monitoring and identifying problematic routes/times.

---

#### 30. Infrabel Segments (`sources/infrabel/segments/fetch_and_analyze.py`)

**Purpose:** Visualizes detailed railway track segments.

**Data Source:**
- `https://api.mobilitytwin.brussels/infrabel/segments`

**Analysis:**
- Extracts detailed LineString geometries
- Shows segment-level granularity

**Output:**
- **File:** Map with detailed track segments

---

## Traffic & Cycling

#### 31. Telraam Traffic Counts (`sources/traffic/telraam/fetch_and_analyze.py`)

**Purpose:** Visualizes multi-modal traffic counts (bikes, cars, pedestrians, heavy vehicles) on Brussels road segments.

**Data Source:**
- `https://api.mobilitytwin.brussels/traffic/telraam`

**Analysis:**
- Extracts LineString geometries for road segments
- Parses counts for: cars, bikes, pedestrians, heavy vehicles
- Calculates total traffic per segment
- Creates color gradient from yellow (low) to red (high traffic)

**Output:**
- **File:** `telraam_traffic.html`
- **Visualization:** Map with:
  - Color-coded road segments (thickness = 4px)
  - Tooltips showing breakdown by mode
  - Color legend for total traffic volume
- **Console:** Count of segments with data

**Use Case:** Urban planning and traffic pattern analysis.

---

#### 32. Bike Counters (`sources/traffic/bike-counters/fetch_and_analyze.py`)

**Purpose:** Maps permanent bike counter device locations with active/inactive status.

**Data Source:**
- `https://api.mobilitytwin.brussels/traffic/bike-counters`

**Analysis:**
- Extracts Point geometries for counter locations
- Separates active (operational) and inactive counters
- Shows device names, roads, and descriptions

**Output:**
- **File:** `bike_counters_map.html`
- **Visualization:** Full-screen map with:
  - Green markers (6px) for active counters
  - Gray markers (4px) for inactive counters
  - Tooltips with device name and road
  - Popups with full details including description
- **Console:** Active and inactive counts

**Use Case:** Infrastructure monitoring and counter network management.

---

#### 33. Bike Count (`sources/traffic/bike-count/fetch_and_analyze.py`)

**Purpose:** Shows hourly bike counts from all active counters.

**Data Source:**
- `https://api.mobilitytwin.brussels/traffic/bike-count`

**Analysis:**
- Parses hierarchical JSON structure
- Extracts hourly, daily, and yearly counts per counter
- Sorts by hourly count (descending)
- Identifies busiest counter

**Output:**
- **File:** `bike_counts.csv`
- **Console:** Formatted table showing:
  - Counter ID
  - Hourly count
  - Daily count
  - Yearly count
  - Timestamp
  - Summary: total counters, total hourly bikes, busiest counter

**Use Case:** Cycling traffic analysis and infrastructure planning.

---

#### 34. Bus Speed (`sources/traffic/bus-speed/fetch_and_analyze.py`)

**Purpose:** Analyzes bus speeds on Brussels roads.

**Data Source:**
- `https://api.mobilitytwin.brussels/traffic/bus-speed`

**Analysis:**
- Calculates average speeds by route/segment
- Identifies slow zones

**Output:**
- **File:** Map or CSV with speed data

---

#### 35. Tunnel Devices (`sources/traffic/tunnel-devices/fetch_and_analyze.py`)

**Purpose:** Maps traffic detection devices in Brussels tunnels.

**Data Source:**
- `https://api.mobilitytwin.brussels/traffic/tunnel-devices`

**Analysis:**
- Extracts Point geometries for sensors
- Shows device types and locations

**Output:**
- **File:** Map with detector markers

---

#### 36. Tunnels (`sources/traffic/tunnels/fetch_and_analyze.py`)

**Purpose:** Visualizes Brussels tunnels with traffic metrics.

**Data Source:**
- `https://api.mobilitytwin.brussels/traffic/tunnels`

**Analysis:**
- Shows tunnel geometries
- Displays speed and occupancy data

**Output:**
- **File:** Map with tunnel overlays

---

## Environment

#### 37. Air Quality (`sources/environment/air-quality/fetch_and_analyze.py`)

**Purpose:** Shows air quality measurements from Brussels monitoring stations.

**Data Source:**
- `https://api.mobilitytwin.brussels/environment/air-quality`

**Analysis:**
- Extracts pollutant levels (PM2.5, PM10, NO2, O3, etc.)
- Shows station locations
- Flags unhealthy levels

**Output:**
- **File:** Map with station markers color-coded by air quality
- **Console:** Summary table

---

#### 38. Weather (`sources/environment/weather/fetch_and_analyze.py`)

**Purpose:** Displays current weather conditions for Brussels in a formatted card.

**Data Source:**
- `https://api.mobilitytwin.brussels/environment/weather`

**Analysis:**
- Parses OpenWeatherMap-style JSON
- Converts temperature from Kelvin to Celsius
- Calculates wind direction and speed conversions (m/s → km/h)
- Determines day/night based on sunrise/sunset times
- Formats timestamps in Brussels timezone (Europe/Brussels)

**Output:**
- **Console:** ASCII-art bordered card displaying:
  - Location and timestamp
  - Temperature and "feels like" temperature (°C)
  - Sky conditions (e.g., "Clear", "Clouds — overcast clouds")
  - Humidity (%) and pressure (hPa)
  - Wind speed (m/s and km/h) and direction (compass + degrees)
  - Day/Night indicator based on sun times

**Example Output:**
```
┌─────────────────────────────────────────────────────────────┐
│ Brussels — 2025-10-23 14:30 (Europe/Brussels)             │
├─────────────────────────────────────────────────────────────┤
│ Temp:   15.2 °C    Feels: 14.8 °C                          │
│ Sky:    Clear                                               │
│ Humid:  68%   Press: 1013 hPa                              │
│ Wind:   3.5 m/s (13 km/h)   Dir: NW (315°)                 │
│ Light:  Day                                                 │
└─────────────────────────────────────────────────────────────┘
```

**Use Case:** Quick weather check for Brussels in terminal/CLI workflows.

---

## Unified Micromobility

These endpoints provide aggregated data across all micromobility providers (Bolt, Dott, Lime, Pony).

#### 39. Micromobility Bolt (`sources/micromobility/bolt/fetch_and_analyze.py`)

**Purpose:** Unified Bolt data from micromobility API.

**Data Source:**
- `https://api.mobilitytwin.brussels/micromobility/bolt`

---

#### 40. Micromobility Dott (`sources/micromobility/dott/fetch_and_analyze.py`)

**Purpose:** Unified Dott data from micromobility API.

**Data Source:**
- `https://api.mobilitytwin.brussels/micromobility/dott`

---

#### 41. Micromobility Lime (`sources/micromobility/lime/fetch_and_analyze.py`)

**Purpose:** Unified Lime data from micromobility API.

**Data Source:**
- `https://api.mobilitytwin.brussels/micromobility/lime`

---

#### 42. Micromobility Pony (`sources/micromobility/pony/fetch_and_analyze.py`)

**Purpose:** Unified Pony data from micromobility API.

**Data Source:**
- `https://api.mobilitytwin.brussels/micromobility/pony`

---

## Common Patterns

### Authentication
All scripts use Bearer token authentication:
```python
TOKEN = "7eba4bf32fcb9502a0ff273fb3191db5b0bbde7cc7f75dc40304dcf2a91c07ed67a55cbbd4e26bf2675e01c5a19d4e7abf92849a5a9fe36d30b558d567dd10cc"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
```

### Technology Stack
- **HTTP Requests:** `requests` library
- **Geospatial:** `geopandas` for GeoDataFrames
- **Mapping:** `folium` for interactive HTML maps
- **Data Analysis:** `pandas` for tabular data
- **Visualization:** `branca` for color scales

### Coordinate Systems
- **WGS84 (EPSG:4326):** Latitude/longitude for mapping
- **Web Mercator (EPSG:3857):** Metric calculations
- **Lambert Belgium (EPSG:3812):** Local metric distances

### Output Types
1. **HTML Maps:** Interactive Folium maps viewable in browser
2. **CSV Files:** Tabular data exports for analysis
3. **Console Reports:** Formatted ASCII tables and summaries
4. **Text Files:** Route listings and schedules

### Error Handling
All scripts include:
- HTTP status validation (`raise_for_status()`)
- Empty data checks
- Geometry type validation
- Timeout settings (typically 30-60 seconds)

---

## Usage

### Running a Script
```bash
cd sources/<provider>/<endpoint>/
python fetch_and_analyze.py
```

### Viewing HTML Output
```bash
open output_file.html  # macOS
xdg-open output_file.html  # Linux
start output_file.html  # Windows
```

### Dependencies
Install all required packages:
```bash
pip install -r requirements.txt
```

Core requirements:
- requests
- geopandas
- folium
- pandas
- branca

---

## Testing

Each script has a corresponding test file:
- Location: Same directory as script
- Naming: `test_fetch_and_analyze.py`
- Framework: pytest with unittest.mock

Run all tests:
```bash
bash test_all.sh
```

Run specific test:
```bash
pytest sources/<provider>/<endpoint>/test_fetch_and_analyze.py -v
```

---

## API Documentation

Base URL: `https://api.mobilitytwin.brussels`

Authentication: Bearer token in `Authorization` header

Rate Limits: Not specified (use responsibly with timeouts)

Data Formats:
- **GeoJSON:** Vector geometries (points, lines, polygons)
- **JSON:** Tabular/structured data
- **ZIP:** GTFS packages
- **Protocol Buffers:** GTFS-RT real-time data

---

## License & Attribution

Data provided by MobilityTwin Brussels API.

Scripts created for data analysis and visualization purposes.

Please respect API terms of service and rate limits.

---

*Last Updated: October 2025*
*Total Scripts: 42*
*Documentation Version: 1.0*
