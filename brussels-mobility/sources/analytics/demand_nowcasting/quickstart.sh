#!/bin/bash
# Quick Start Script for Micromobility Demand Nowcasting
# Run this from the project root: /Users/eyad/Desktop/doc

set -e  # Exit on error

echo "=========================================="
echo "Micromobility Demand Nowcasting Quick Start"
echo "=========================================="

# Check Python version
echo -e "\n[1/4] Checking Python version..."
python3 --version

# Install dependencies
echo -e "\n[2/4] Installing dependencies..."
pip install -q pandas numpy scikit-learn pyproj folium lightgbm matplotlib seaborn jupyter pytest

# Run tests
echo -e "\n[3/4] Running tests..."
cd /Users/eyad/Desktop/doc
python -m pytest tests/analytics/test_demand_nowcasting.py -v

# Run pipeline
echo -e "\n[4/4] Running demand nowcasting pipeline..."
cd /Users/eyad/Desktop/doc/sources/analytics/demand_nowcasting
python -m fetch_and_model

echo -e "\n=========================================="
echo "✅ Setup complete!"
echo "=========================================="
echo ""
echo "View results:"
echo "  Map: sources/analytics/demand_nowcasting/output_map.html"
echo "  CSV: sources/analytics/demand_nowcasting/output_forecast.csv"
echo "  Model: sources/analytics/demand_nowcasting/model_artifact.pkl"
echo ""
echo "Next steps:"
echo "  - Open output_map.html in your browser"
echo "  - Review output_forecast.csv for per-cell predictions"
echo "  - Explore notebooks/eda.ipynb for data analysis"
echo "  - Read README.md for detailed documentation"
echo ""
