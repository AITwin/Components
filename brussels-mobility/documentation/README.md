# Documentation

## Main Docs

**[DEMAND_NOWCASTING_QUICKSTART.md](DEMAND_NOWCASTING_QUICKSTART.md)** - Start here if you want to try the demand forecasting system

**[DEMAND_NOWCASTING_README.md](DEMAND_NOWCASTING_README.md)** - Technical details about the ML pipeline, grid cells, features, rebalancing

**[FETCH_AND_ANALYZE_DOCUMENTATION.md](FETCH_AND_ANALYZE_DOCUMENTATION.md)** - All 40+ data sources (APIs, what they return, how to use them)

**[TESTING.md](TESTING.md)** - How to run tests

## Other Docs

**[NORMALIZATION_REPORT.md](NORMALIZATION_REPORT.md)** - How the different APIs compare, field mappings

**[VISUALIZATIONS_SUMMARY.md](VISUALIZATIONS_SUMMARY.md)** - What visualizations get generated

**[DEMAND_NOWCASTING_SUMMARY.md](DEMAND_NOWCASTING_SUMMARY.md)** - High-level overview of the forecasting system

## Quick Start

1. Read the quickstart guide: [DEMAND_NOWCASTING_QUICKSTART.md](DEMAND_NOWCASTING_QUICKSTART.md)
2. Run tests: `../run_all_tests.sh analytics`
3. Browse data sources: [FETCH_AND_ANALYZE_DOCUMENTATION.md](FETCH_AND_ANALYZE_DOCUMENTATION.md)

## Project Layout

```
sources/                  # Data collection scripts by provider
  analytics/             # ML forecasting system
  bolt/, dott/, lime/    # Micromobility APIs
  sncb/, stib/           # Public transit
  infrabel/              # Rail infrastructure
  environment/           # Weather, air quality
  traffic/               # Traffic monitoring

tests/                   # Test suite
output/                  # Generated maps/CSVs
documentation/           # This folder
```

The code's organized by data source - each has its own folder with fetch scripts, tests, and sample data.
