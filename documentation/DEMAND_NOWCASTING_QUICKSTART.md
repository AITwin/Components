# Demand Nowcasting Quick Start

## What it does

Predicts micromobility demand (scooters/bikes) 30 minutes ahead for 250m grid cells around Brussels and suggests where to move vehicles.

## Prerequisites

- Python 3.10+
- Virtual environment (`.venv` in the project root)
- Internet connection

## Quick Demo (2 hours)

Try it out with limited data:

```bash
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting

# Collect 2 hours of data
/Users/eyad/Desktop/doc/.venv/bin/python collect_historical_data.py --duration 2 --interval 10

# Run the model
/Users/eyad/Desktop/doc/.venv/bin/python fetch_and_model.py

# Check results
open output_map.html
```

## Full Run (48 hours)

For better predictions, collect data over 48 hours:

### 1. Start collection

```bash
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting

# Run in background
nohup /Users/eyad/Desktop/doc/.venv/bin/python collect_historical_data.py --duration 48 --interval 10 > collection.log 2>&1 &

# Save the process ID
echo $! > collection.pid
```

This collects vehicle snapshots every 10 minutes for 48 hours. You can close the terminal - it'll keep running.

### 2. Monitor progress

```bash
# Check if it's still running
ps -p $(cat collection.pid)

# Watch live progress
tail -f collection.log

# Count files collected
find historical_data/ -name "*.json" | wc -l
```

You should end up with ~864 files (3 providers × 288 snapshots each).

### 3. Run the model

After 48 hours:

```bash
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting
/Users/eyad/Desktop/doc/.venv/bin/python fetch_and_model.py
```

This takes 2-5 minutes and:
- Loads all the snapshots
- Aggregates to 250m grid cells  
- Builds features (time patterns, weather, spatial)
- Trains a model (Ridge regression by default)
- Predicts demand 30 min ahead
- Suggests rebalancing moves

### 4. Check results

```bash
open output_map.html    # Interactive map
open output_forecast.csv  # Data export
```

## Output Files

**output_map.html** - Interactive map showing:
- Blue markers = balanced cells
- Red = deficit (need vehicles)
- Green = surplus (excess vehicles)
- Purple arrows = suggested moves

**output_forecast.csv** - Spreadsheet with:
- `cell_id` - Grid cell location
- `lat`, `lon` - Coordinates
- `available_vehicles` - Current count
- `predicted_demand_30m` - Expected demand
- `projected_remaining` - Availability after demand
- `shortage_if_any` - How many short

**historical_data/** - All the snapshots you collected

## Command Reference

```bash
# Data collection options
python collect_historical_data.py                              # Single snapshot
python collect_historical_data.py --duration 2 --interval 10   # 2 hours
python collect_historical_data.py --duration 24 --interval 10  # Daily patterns
python collect_historical_data.py --duration 48 --interval 10  # Recommended

# Stop collection early
kill $(cat collection.pid)

# Clean up old data
rm -rf historical_data/

# Backup before cleaning
tar -czf historical_data_backup.tar.gz historical_data/
```

## Expected Results

With 48 hours of data:
- 2,000-5,000 observations
- 20-50 active grid cells
- MAE around 0.5-2.0 vehicles per cell
- 20-40% better than naive baseline
- 5-15 rebalancing suggestions

MAE < 1.0 is excellent, 1.0-2.0 is good, >2.0 is acceptable but could use more data.

## Troubleshooting

**"Insufficient data for training"**
- Need at least 10 observations. Wait for more snapshots or check if collection is running.

**"No module named 'lightgbm'"**
- This is just a warning. The code falls back to Ridge regression which works fine.
- Install if you want: `/Users/eyad/Desktop/doc/.venv/bin/pip install lightgbm`

**Collection stopped**
- Check logs: `tail -50 collection.log`
- Computer might have gone to sleep
- API might have timed out
- Restart: `nohup python collect_historical_data.py --duration 24 --interval 10 > collection.log 2>&1 &`

**Only seeing 3-9 vehicles per snapshot**
- That's normal - it's the actual current availability
- Model still works, just with less spatial detail
- Collect over longer periods to capture more variation

## Tips

**Prevent computer sleep during collection:**
```bash
caffeinate -i python collect_historical_data.py --duration 48 --interval 10
```

**Best times to collect:**
- Start Monday 6 AM for weekday/weekend mix
- Include rush hours (7-9 AM, 5-7 PM)
- Avoid starting on holidays

**For continuous forecasting:**
Run the pipeline hourly via cron:
```bash
0 * * * * cd /path/to/demand_nowcasting && python fetch_and_model.py
```

## Next Steps

After your first run:
- Check out `notebooks/eda.ipynb` for data exploration
- Tune model parameters in `fetch_and_model.py`
- Try longer forecast horizons (60+ minutes)
- Use CSV output for your dispatch system
- Test rebalancing recommendations in practice

More details in `README.md`.
