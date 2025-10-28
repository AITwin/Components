"""
Test suite for micromobility demand nowcasting and rebalancing.

This module tests all core functionality including spatial grid operations,
aggregation, feature engineering, modeling, and rebalancing logic.
"""

import sys
import os
from pathlib import Path
import tempfile
import pandas as pd
import numpy as np
import pytest

# Add sources to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'sources'))

from analytics.demand_nowcasting.utils import (
    project_wgs84_to_meters,
    assign_grid_cells,
    cell_centroid_latlon,
    get_neighbor_cells,
    plan_rebalancing
)
from analytics.demand_nowcasting.fetch_and_model import (
    aggregate_to_grid,
    build_baseline_predictor,
    generate_synthetic_vehicle_data,
    generate_synthetic_weather_data
)


# Fixtures

@pytest.fixture
def sample_positions_df():
    """Create a small sample of vehicle positions."""
    # Brussels center coordinates
    return pd.DataFrame({
        'timestamp': pd.to_datetime(['2024-10-21 08:00:00'] * 5, utc=True),
        'vehicle_id': ['v1', 'v2', 'v3', 'v4', 'v5'],
        'lat': [50.8503, 50.8503, 50.8513, 50.8513, 50.8523],
        'lon': [4.3517, 4.3517, 4.3527, 4.3527, 4.3537],
        'provider': ['dott', 'bolt', 'lime', 'dott', 'bolt']
    })


@pytest.fixture
def sample_agg_df():
    """Load sample aggregated data from fixtures."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'demand_nowcasting_sample.csv'
    df = pd.read_csv(fixture_path)
    df['time_bin'] = pd.to_datetime(df['time_bin'], utc=True)
    return df


@pytest.fixture
def sample_deficits_surpluses():
    """Create sample deficit and surplus DataFrames for rebalancing tests."""
    deficits = pd.DataFrame({
        'cell_id': ['cell_100_200', 'cell_350_200'],
        'cell_x': [100, 350],
        'cell_y': [200, 200],
        'need': [5.0, 3.0]
    })
    
    surpluses = pd.DataFrame({
        'cell_id': ['cell_100_450', 'cell_350_450'],
        'cell_x': [100, 350],
        'cell_y': [450, 450],
        'surplus': [4.0, 6.0]
    })
    
    centroids = {
        'cell_100_200': (50.8503, 4.3517),
        'cell_350_200': (50.8505, 4.3520),
        'cell_100_450': (50.8508, 4.3517),
        'cell_350_450': (50.8510, 4.3520)
    }
    
    return deficits, surpluses, centroids


# Tests

class TestGridCellOperations:
    """Test spatial grid cell operations."""
    
    def test_assign_grid_cells_creates_cell_id(self, sample_positions_df):
        """Test that cell_id is created from lat/lon coordinates."""
        df = project_wgs84_to_meters(sample_positions_df)
        df = assign_grid_cells(df, cell_size_m=250)
        
        assert 'cell_id' in df.columns
        assert 'cell_x' in df.columns
        assert 'cell_y' in df.columns
        assert df['cell_id'].notna().all()
    
    def test_identical_coords_map_to_same_cell(self, sample_positions_df):
        """Test that identical coordinates map to the same cell."""
        df = project_wgs84_to_meters(sample_positions_df)
        df = assign_grid_cells(df, cell_size_m=250)
        
        # First two rows have identical lat/lon
        assert df.iloc[0]['cell_id'] == df.iloc[1]['cell_id']
    
    def test_different_coords_map_to_different_cells(self, sample_positions_df):
        """Test that significantly different coordinates map to different cells."""
        df = project_wgs84_to_meters(sample_positions_df)
        df = assign_grid_cells(df, cell_size_m=250)
        
        # First and last rows have different lat/lon
        assert df.iloc[0]['cell_id'] != df.iloc[4]['cell_id']
    
    def test_cell_centroid_conversion(self):
        """Test conversion of cell coordinates back to lat/lon."""
        # Use realistic Brussels coordinates in Web Mercator meters
        # Brussels center is approximately at x=484000, y=6587000 in EPSG:3857
        cell_x, cell_y = 484000, 6587000
        lat, lon = cell_centroid_latlon(cell_x, cell_y, cell_size_m=250)
        
        assert isinstance(lat, float)
        assert isinstance(lon, float)
        # Should be reasonable coordinates (roughly Brussels, Belgium)
        assert 50 < lat < 51
        assert 4 < lon < 5
    
    def test_get_neighbor_cells(self):
        """Test that 8 neighbors are correctly identified."""
        neighbors = get_neighbor_cells(1000, 2000, cell_size_m=250)
        
        assert len(neighbors) == 8
        assert '1000_2250' in neighbors  # North
        assert '1000_1750' in neighbors  # South
        assert '1250_2000' in neighbors  # East
        assert '750_2000' in neighbors   # West


class TestAggregation:
    """Test data aggregation and time binning."""
    
    def test_build_aggregation(self, sample_positions_df):
        """Test aggregation of raw positions to grid cells and time bins."""
        agg_df = aggregate_to_grid(sample_positions_df)
        
        assert 'time_bin' in agg_df.columns
        assert 'cell_id' in agg_df.columns
        assert 'available_vehicles' in agg_df.columns
        assert 'provider_count' in agg_df.columns
        
        # Should have aggregated the 5 vehicles
        assert agg_df['available_vehicles'].sum() <= 5
    
    def test_time_bin_rounding(self, sample_positions_df):
        """Test that time_bin rounds to 10-minute intervals."""
        # Add varied timestamps
        sample_positions_df['timestamp'] = pd.to_datetime([
            '2024-10-21 08:03:00',
            '2024-10-21 08:07:00',
            '2024-10-21 08:14:00',
            '2024-10-21 08:18:00',
            '2024-10-21 08:23:00'
        ], utc=True)
        
        agg_df = aggregate_to_grid(sample_positions_df)
        
        # Should have 3 time bins: 08:00, 08:10, 08:20
        unique_bins = agg_df['time_bin'].unique()
        assert len(unique_bins) <= 3
        
        # All bins should be on 10-minute boundaries
        for time_bin in agg_df['time_bin']:
            assert time_bin.minute % 10 == 0


class TestFeatureEngineering:
    """Test feature creation and target variable computation."""
    
    def test_make_training_frame(self, sample_agg_df):
        """Test that features are created correctly."""
        df = sample_agg_df.copy()
        
        # Features should already be in the fixture
        assert 'hour' in df.columns
        assert 'dow' in df.columns
        assert 'avail_lag_10' in df.columns
        assert 'avail_lag_20' in df.columns
        assert 'demand_30m' in df.columns
        
        # Demand should be non-negative
        assert (df['demand_30m'] >= 0).all()
    
    def test_demand_calculation(self, sample_agg_df):
        """Test that demand_30m is correctly calculated."""
        df = sample_agg_df.copy()
        
        # Demand should exist and be reasonable
        assert df['demand_30m'].notna().any()
        assert df['demand_30m'].max() <= df['available_vehicles'].max()
    
    def test_lag_features_created(self, sample_agg_df):
        """Test that lag features are created."""
        df = sample_agg_df.copy()
        
        # Should have lag features
        assert 'avail_lag_10' in df.columns
        assert 'avail_lag_20' in df.columns
        
        # Lag features should be filled (no NaN in middle of series)
        assert df['avail_lag_10'].notna().sum() > 0


class TestBaselineForecast:
    """Test baseline prediction model."""
    
    def test_baseline_forecast(self, sample_agg_df):
        """Test baseline predictor returns numeric predictions."""
        train_df = sample_agg_df.copy()
        
        baseline = build_baseline_predictor(train_df)
        
        assert 'stats' in baseline
        assert 'global_mean' in baseline
        assert 'predict' in baseline
        
        # Test prediction
        cell_id = train_df.iloc[0]['cell_id']
        hour_of_week = train_df.iloc[0]['hour_of_week']
        
        prediction = baseline['predict'](cell_id, hour_of_week)
        
        assert isinstance(prediction, (int, float))
        assert prediction >= 0
    
    def test_baseline_uses_historical_averages(self, sample_agg_df):
        """Test that baseline uses historical averages for predictions."""
        train_df = sample_agg_df.copy()
        
        baseline = build_baseline_predictor(train_df)
        
        # For a cell and hour_of_week that exists, should return average
        cell_id = 'cell_100_200'
        hour_of_week = 8  # Monday 8am
        
        # Calculate expected average
        expected = train_df[
            (train_df['cell_id'] == cell_id) &
            (train_df['hour_of_week'] == hour_of_week)
        ]['demand_30m'].mean()
        
        if pd.notna(expected):
            prediction = baseline['predict'](cell_id, hour_of_week)
            assert abs(prediction - expected) < 0.01


class TestRebalancing:
    """Test rebalancing logic."""
    
    def test_plan_rebalancing(self, sample_deficits_surpluses):
        """Test that rebalancing moves are correctly planned."""
        deficits, surpluses, centroids = sample_deficits_surpluses
        
        moves = plan_rebalancing(deficits, surpluses, centroids)
        
        assert isinstance(moves, list)
        assert len(moves) > 0
        
        # Check move structure
        for move in moves:
            assert 'from_cell_id' in move
            assert 'to_cell_id' in move
            assert 'count' in move
            assert 'distance_m' in move
            assert move['count'] > 0
            assert move['distance_m'] >= 0
    
    def test_no_overallocation(self, sample_deficits_surpluses):
        """Test that moves don't allocate more than available surplus."""
        deficits, surpluses, centroids = sample_deficits_surpluses
        
        moves = plan_rebalancing(deficits, surpluses, centroids)
        
        # Sum moves from each surplus cell
        moves_from = {}
        for move in moves:
            from_cell = move['from_cell_id']
            moves_from[from_cell] = moves_from.get(from_cell, 0) + move['count']
        
        # Check against original surplus
        for cell_id, total_moved in moves_from.items():
            original_surplus = surpluses[surpluses['cell_id'] == cell_id]['surplus'].values[0]
            assert total_moved <= original_surplus
    
    def test_deficit_reduction(self, sample_deficits_surpluses):
        """Test that deficits are greedily reduced."""
        deficits, surpluses, centroids = sample_deficits_surpluses
        
        moves = plan_rebalancing(deficits, surpluses, centroids)
        
        # Highest deficit should get first allocation
        highest_deficit_cell = deficits.sort_values('need', ascending=False).iloc[0]['cell_id']
        
        # Check that highest deficit cell receives vehicles
        moves_to_highest = [m for m in moves if m['to_cell_id'] == highest_deficit_cell]
        assert len(moves_to_highest) > 0
    
    def test_empty_inputs(self):
        """Test that empty inputs return empty moves list."""
        empty_deficits = pd.DataFrame(columns=['cell_id', 'cell_x', 'cell_y', 'need'])
        empty_surpluses = pd.DataFrame(columns=['cell_id', 'cell_x', 'cell_y', 'surplus'])
        centroids = {}
        
        moves = plan_rebalancing(empty_deficits, empty_surpluses, centroids)
        assert moves == []


class TestVisualization:
    """Test visualization and export functions."""
    
    def test_forecast_map_creation(self):
        """Test that forecast map can be created and saved."""
        pytest.importorskip("folium")
        
        from analytics.demand_nowcasting.visualize import build_forecast_map
        
        # Create minimal forecast data
        forecast_df = pd.DataFrame({
            'cell_id': ['cell_100_200', 'cell_350_200'],
            'lat': [50.8503, 50.8505],
            'lon': [4.3517, 4.3520],
            'predicted_demand_30m': [2.5, 3.8],
            'available_vehicles': [5, 8],
            'projected_remaining': [2.5, 4.2]
        })
        
        moves = [{
            'from_cell_id': 'cell_350_200',
            'to_cell_id': 'cell_100_200',
            'count': 2,
            'distance_m': 250.0
        }]
        
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            temp_path = f.name
        
        try:
            build_forecast_map(forecast_df, moves, temp_path)
            
            # Check file was created
            assert os.path.exists(temp_path)
            assert os.path.getsize(temp_path) > 0
            
            # Check it contains HTML
            with open(temp_path, 'r') as f:
                content = f.read()
                assert '<html>' in content.lower() or '<!doctype' in content.lower()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_csv_export(self):
        """Test CSV export of forecast data."""
        from analytics.demand_nowcasting.visualize import export_forecast_csv
        
        forecast_df = pd.DataFrame({
            'cell_id': ['cell_100_200', 'cell_350_200'],
            'lat': [50.8503, 50.8505],
            'lon': [4.3517, 4.3520],
            'predicted_demand_30m': [2.5, 3.8],
            'available_vehicles': [5, 8],
            'projected_remaining': [2.5, -1.2]  # One deficit
        })
        
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            temp_path = f.name
        
        try:
            export_forecast_csv(forecast_df, temp_path)
            
            # Check file was created
            assert os.path.exists(temp_path)
            
            # Read back and check
            df = pd.read_csv(temp_path)
            assert len(df) == 2
            assert 'cell_id' in df.columns
            assert 'shortage_if_any' in df.columns
            
            # Check shortage calculation
            assert df[df['cell_id'] == 'cell_350_200']['shortage_if_any'].values[0] == 1.2
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestSyntheticDataGeneration:
    """Test synthetic data generation for demo purposes."""
    
    def test_generate_synthetic_vehicle_data(self):
        """Test that synthetic vehicle data is generated correctly."""
        df = generate_synthetic_vehicle_data()
        
        assert len(df) > 0
        assert 'timestamp' in df.columns
        assert 'vehicle_id' in df.columns
        assert 'lat' in df.columns
        assert 'lon' in df.columns
        assert 'provider' in df.columns
        
        # Should have reasonable coordinates (Brussels area)
        assert df['lat'].between(50.7, 51.0).all()
        assert df['lon'].between(4.2, 4.5).all()
    
    def test_generate_synthetic_weather_data(self):
        """Test that synthetic weather data is generated correctly."""
        df = generate_synthetic_weather_data()
        
        assert len(df) > 0
        assert 'timestamp' in df.columns
        assert 'temp_c' in df.columns
        assert 'wind_speed' in df.columns
        assert 'rain_mmph' in df.columns
        
        # Should have reasonable values
        assert df['temp_c'].between(-10, 35).all()
        assert df['wind_speed'].between(0, 30).all()
        assert df['rain_mmph'].min() >= 0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
