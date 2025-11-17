# Micromobility Demand Nowcasting - Quick Start Guide

## 🚀 Overview

This project forecasts micromobility demand (scooters/bikes) 30 minutes ahead for 250m x 250m grid cells in Brussels and recommends vehicle rebalancing moves to optimize availability.

## 📋 Prerequisites

- Python 3.10 or higher
- Virtual environment activated
- Internet connection (for API calls)

## ⚡ Quick Start (2-Hour Demo)

For a quick demo with limited data:

```bash
# 1. Navigate to the project directory
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting

# 2. Collect 2 hours of data (12 snapshots)
/Users/eyad/Desktop/doc/.venv/bin/python collect_historical_data.py --duration 2 --interval 10

# 3. Run the forecasting pipeline
/Users/eyad/Desktop/doc/.venv/bin/python fetch_and_model.py

# 4. View results
open output_map.html
```

## 🎯 Full Production Run (48-Hour Collection)

For production-quality forecasts with comprehensive demand patterns:

### Step 1: Start 48-Hour Data Collection

```bash
# Navigate to project directory
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting

# Start collection in background (will run for 48 hours)
nohup /Users/eyad/Desktop/doc/.venv/bin/python collect_historical_data.py --duration 48 --interval 10 > collection.log 2>&1 &

# Save the process ID for monitoring
echo $! > collection.pid
```

**What this does:**
- Collects vehicle position snapshots every 10 minutes
- Runs for 48 hours (288 snapshots per provider)
- Saves data to `historical_data/{dott,bolt,lime}/`
- Logs output to `collection.log`
- Runs in background so you can close terminal

### Step 2: Monitor Collection Progress

```bash
# Check if collection is still running
ps -p $(cat collection.pid)

# View live progress
tail -f collection.log

# Count snapshots collected so far
find historical_data/ -name "*.json" | wc -l

# Expected: 3 providers × snapshots_collected (max 864 files)
```

**Timeline:**
- **Start:** When you run the command
- **Duration:** 48 hours (2 days)
- **End:** Automatically stops after 48 hours
- **Total snapshots:** 288 per provider = 864 total files

### Step 3: Run the Forecasting Pipeline

After 48 hours (or when collection completes):

```bash
# Navigate to project directory
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting

# Run the full pipeline
/Users/eyad/Desktop/doc/.venv/bin/python fetch_and_model.py
```

**What this does:**
1. Loads all historical snapshots (288 × 3 = 864 files)
2. Aggregates to 250m grid cells
3. Creates time-series features (lags, weather, spatial)
4. Trains Ridge regression model
5. Generates 30-minute demand forecasts
6. Identifies deficit/surplus cells
7. Plans rebalancing moves
8. Creates interactive map and CSV output

**Expected runtime:** 2-5 minutes

### Step 4: View Results

```bash
# Open interactive map in browser
open output_map.html

# View forecast CSV
cat output_forecast.csv

# Or open in Excel/Numbers
open output_forecast.csv
```

## 📊 Output Files

After running the pipeline, you'll find:

### 1. `output_map.html` (Interactive Map)
- **Heatmap** of vehicle availability
- **Blue markers** = balanced cells
- **Red markers** = deficit cells (need more vehicles)
- **Green markers** = surplus cells (excess vehicles)
- **Purple arrows** = recommended rebalancing moves
- **Click markers** to see cell details

### 2. `output_forecast.csv` (Data Export)
Columns:
- `cell_id`: Grid cell identifier (x_y coordinates)
- `lat`, `lon`: Cell center coordinates
- `available_vehicles`: Current count
- `predicted_demand_30m`: Expected pickups in next 30 minutes
- `projected_remaining`: Availability after demand
- `shortage_if_any`: Deficit if projected < threshold

### 3. `model_artifact.pkl` (Trained Model)
- Saved Ridge regression model
- Can be loaded for batch predictions
- Includes fitted StandardScaler

### 4. `historical_data/` (Collected Snapshots)
```
historical_data/
├── dott/
│   ├── snapshot_20251028_140000.json
│   ├── snapshot_20251028_141000.json
│   └── ...
├── bolt/
│   └── ...
└── lime/
    └── ...
```

## 🔧 Command Reference

### Data Collection

```bash
# Collect once (single snapshot)
python collect_historical_data.py

# Collect for 2 hours (demo)
python collect_historical_data.py --duration 2 --interval 10

# Collect for 24 hours (daily patterns)
python collect_historical_data.py --duration 24 --interval 10

# Collect for 48 hours (weekly patterns, recommended)
python collect_historical_data.py --duration 48 --interval 10

# Custom interval (every 5 minutes)
python collect_historical_data.py --duration 12 --interval 5
```

### Pipeline Execution

```bash
# Run with default settings
python fetch_and_model.py

# The pipeline automatically detects and uses historical_data/ if available
# Falls back to synthetic data if no historical data exists
```

### Monitoring & Cleanup

```bash
# Stop collection (if running in background)
kill $(cat collection.pid)

# Check disk usage
du -sh historical_data/

# Clean old data (careful!)
rm -rf historical_data/

# Archive data before cleaning
tar -czf historical_data_backup.tar.gz historical_data/
```

## 📈 Expected Results

### With 48-Hour Data Collection:

- **~2,000-5,000 observations** (varies by vehicle availability)
- **20-50 active grid cells** in Brussels area
- **MAE: 0.5-2.0 vehicles** per cell
- **20-40% improvement** over baseline
- **5-15 rebalancing moves** recommended

### Interpretation:

- **MAE < 1.0**: Excellent accuracy
- **MAE 1.0-2.0**: Good accuracy
- **MAE > 2.0**: Acceptable, may need more data or tuning

## ⚠️ Troubleshooting

### Issue: "Insufficient data for training"

**Cause:** Less than 10 observations collected

**Solution:**
- Check if collection is still running: `ps -p $(cat collection.pid)`
- Verify snapshots exist: `ls -l historical_data/dott/`
- Wait for more snapshots to be collected
- Minimum recommended: 2 hours (12 snapshots)

### Issue: "No module named 'lightgbm'"

**Status:** Expected warning (not an error)

**Explanation:** LightGBM is optional. Code automatically falls back to Ridge regression, which works very well for this task.

**Optional fix:**
```bash
/Users/eyad/Desktop/doc/.venv/bin/pip install lightgbm
```

### Issue: Collection stopped unexpectedly

**Check logs:**
```bash
tail -50 collection.log
```

**Common causes:**
- Computer went to sleep (disable sleep for long runs)
- Network timeout (APIs temporarily unavailable)
- Disk full (check with `df -h`)

**Resume collection:**
```bash
# Restart collection (will append to existing data)
nohup /Users/eyad/Desktop/doc/.venv/bin/python collect_historical_data.py --duration 24 --interval 10 > collection.log 2>&1 &
```

### Issue: API returns limited vehicles

**Observation:** Only 3-9 vehicles per snapshot

**Explanation:** This is the actual current availability in Brussels from the APIs. The model will still work but with lower spatial granularity.

**Workaround:** Collect over longer periods (48+ hours) to capture more temporal variation even with limited vehicles.

## 🎓 Best Practices

### 1. Data Collection Timing

**Recommended collection times:**
- **48 hours starting Monday 6 AM** - Captures weekday and weekend patterns
- **Include rush hours:** 7-9 AM and 5-7 PM for peak demand
- **Avoid holidays** when starting collection (atypical patterns)

### 2. System Requirements

```bash
# Prevent computer sleep during collection
caffeinate -i python collect_historical_data.py --duration 48 --interval 10
```

### 3. Production Deployment

For continuous forecasting:

```bash
# 1. Collect data continuously
while true; do
    python collect_historical_data.py --duration 24 --interval 10
    sleep 86400  # Wait 24 hours
done

# 2. Run pipeline hourly (cron job)
0 * * * * cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting && python fetch_and_model.py
```

## 📚 Next Steps

After successful 48-hour run:

1. **Analyze patterns** - Open `notebooks/eda.ipynb` for exploratory analysis
2. **Tune model** - Adjust hyperparameters in `fetch_and_model.py`
3. **Extend forecast horizon** - Modify `FORECAST_HORIZON_MINUTES` for 60-min predictions
4. **Integrate with operations** - Use CSV output for dispatch systems
5. **A/B test rebalancing** - Implement recommendations and measure impact

## 🆘 Support

- **Documentation:** See `README.md` for architecture details
- **Tests:** Run `pytest tests/analytics/test_demand_nowcasting.py -v`
- **Code:** All source in `sources/analytics/demand_nowcasting/`

## 📝 Summary Checklist

- [ ] Navigate to project directory
- [ ] Start 48-hour collection in background
- [ ] Monitor progress periodically
- [ ] Wait 48 hours for completion
- [ ] Run forecasting pipeline
- [ ] View output_map.html
- [ ] Analyze output_forecast.csv
- [ ] Review console metrics

**Estimated total time:** 48 hours collection + 5 minutes execution

---

**Last Updated:** October 28, 2025  
**Version:** 1.0
