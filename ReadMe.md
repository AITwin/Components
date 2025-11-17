# Brussels Mobility Data

Data collection and analysis for Brussels' transportation systems - bikes, scooters, buses, trains, and more.

## What's This?

This project pulls real-time data from 40+ APIs covering Brussels mobility:
- Micromobility (Bolt, Dott, Lime, Pony) - ~11k vehicles
- Public transit (SNCB, STIB, TEC, De Lijn)
- Traffic monitoring (bike counters, bus speeds, tunnels)
- Environment (weather, air quality)

Plus some ML experiments for predicting micromobility demand and optimizing vehicle rebalancing.

## Quick Start

Install:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run tests:
```bash
./run_all_tests.sh analytics  # Quick (30 seconds)
./run_all_tests.sh            # Everything (~10 min)
```

Try the demand nowcasting:
```bash
cd sources/analytics/demand_nowcasting
bash quickstart.sh
```

## Project Structure

```
sources/                    # Data collection scripts
  analytics/               # ML models for demand forecasting
    demand_nowcasting/     # Main forecasting system
  bolt/                    # Bolt API integration
  dott/                    # Dott API integration
  lime/                    # Lime API integration
  pony/                    # Pony API integration
  sncb/                    # Belgian railways
  stib/                    # Brussels metro/tram/bus
  tec/                     # Wallonia transport
  de-lijn/                 # Flanders transport
  infrabel/                # Railway infrastructure
  environment/             # Weather & air quality
  traffic/                 # Traffic monitoring

tests/                     # Test suite
documentation/             # More detailed docs
output/                    # Generated maps and CSVs
```

## How It Works

Each data source has a `fetch_and_analyze.py` script that:
1. Calls the API
2. Processes the data
3. Generates a visualization (usually an HTML map)
4. Saves the results

The demand nowcasting system:
1. Aggregates vehicle positions into 250m grid cells
2. Builds features (time of day, weather, historical patterns)
3. Trains a LightGBM model to predict demand
4. Suggests vehicle rebalancing moves

## Running Scripts

Fetch data from specific sources:
```bash
python sources/micromobility/dott/fetch_and_analyze.py
python sources/stib/vehicle-position/fetch_and_analyze.py
python sources/environment/weather/fetch_and_analyze.py
```

Check output in the `output/` directory.

## Testing

Most tests run reliably. Some integration tests might timeout if external APIs are slow - that's normal.

```bash
./run_all_tests.sh analytics     # ML tests only
./run_all_tests.sh integration   # All API calls
./run_all_tests.sh unit          # Individual module tests
```

See `documentation/TESTING.md` for more.

## Documentation

- `documentation/TESTING.md` - Test info
- `documentation/DEMAND_NOWCASTING_QUICKSTART.md` - ML system guide
- `documentation/FETCH_AND_ANALYZE_DOCUMENTATION.md` - All data sources

## Notes

This started as a mobility analysis experiment and grew into a fairly comprehensive data collection system. The code's a bit scattered (data sources have tests living next to them rather than centralized), but everything works.

Some APIs require authentication - check individual scripts for details.

Most visualizations use Folium for maps and Plotly for charts. Outputs are HTML files you can open in a browser.

## Status

Tests passing, APIs working, docs up to date. Built with Python 3.12.
