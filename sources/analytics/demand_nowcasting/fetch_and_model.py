"""
Main pipeline for micromobility demand nowcasting and rebalancing.

This script loads historical vehicle position data, trains a demand forecasting model,
and proposes rebalancing moves to optimize vehicle availability.
"""

import os
import sys
import json
import pickle
import warnings
from pathlib import Path
from typing import Dict, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import project utilities (support both direct execution and module import)
try:
    from .utils import (
        project_wgs84_to_meters,
        assign_grid_cells,
        cell_centroid_latlon,
        compute_neighbor_features,
        plan_rebalancing
    )
    from .visualize import build_forecast_map, export_forecast_csv
except ImportError:
    from utils import (
        project_wgs84_to_meters,
        assign_grid_cells,
        cell_centroid_latlon,
        compute_neighbor_features,
        plan_rebalancing
    )
    from visualize import build_forecast_map, export_forecast_csv

# Try to import machine learning libraries
try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("Warning: LightGBM not available, falling back to Ridge regression")

from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error


# Constants
CELL_SIZE_M = 250
TIME_BIN_MINUTES = 10
FORECAST_HORIZON_MINUTES = 30
FORECAST_HORIZON_BINS = FORECAST_HORIZON_MINUTES // TIME_BIN_MINUTES
RANDOM_STATE = 42


def load_vehicle_positions(base_path: str = "sources") -> pd.DataFrame:
    """
    Load vehicle position data from all micromobility providers.
    
    Args:
        base_path: Base directory path containing provider data
        
    Returns:
        Combined DataFrame with columns: timestamp, vehicle_id, lat, lon, provider
    """
    providers = ['dott', 'bolt', 'lime']
    all_data = []
    
    # First, try loading from historical_data directory (preferred)
    historical_path = Path(__file__).parent / 'historical_data'
    if historical_path.exists():
        for provider in providers:
            provider_hist_path = historical_path / provider
            if provider_hist_path.exists():
                json_files = list(provider_hist_path.glob('*.json'))
                if json_files:
                    print(f"Loading {len(json_files)} historical snapshots from {provider}")
                    base_path = str(historical_path)
                    break
    
    for provider in providers:
        # Try historical data first
        provider_path = Path(base_path) / provider
        if not provider_path.exists():
            # Fall back to sources/*/vehicle-position
            provider_path = Path(base_path) / provider / 'vehicle-position'
        
        if not provider_path.exists():
            print(f"Warning: {provider_path} not found, skipping {provider}")
            continue
        
        # Load JSON files
        for json_file in provider_path.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                # Use file modification time as base timestamp
                file_timestamp = datetime.fromtimestamp(json_file.stat().st_mtime)
                
                # Handle different response structures
                vehicles = []
                if isinstance(data, dict):
                    # Check for timestamped snapshots from historical collection
                    if 'collection_timestamp' in data and 'data' in data:
                        file_timestamp = pd.to_datetime(data['collection_timestamp']).tz_localize(None)
                        data = data['data']
                    
                    # GeoJSON FeatureCollection format (Dott, Lime, Bolt)
                    if data.get('type') == 'FeatureCollection' and 'features' in data:
                        for feature in data['features']:
                            if feature.get('type') == 'Feature':
                                coords = feature.get('geometry', {}).get('coordinates', [])
                                props = feature.get('properties', {})
                                if len(coords) >= 2:
                                    lon, lat = coords[0], coords[1]
                                    vehicle_id = (props.get('bike_id') or props.get('id') or 
                                                props.get('vehicle_id') or str(feature.get('id', '')))
                                    last_reported = props.get('last_reported') or props.get('last_updated')
                                    
                                    # Convert timestamp
                                    if last_reported:
                                        if isinstance(last_reported, (int, float)):
                                            # Unix timestamp
                                            ts = datetime.fromtimestamp(last_reported)
                                        else:
                                            ts = pd.to_datetime(last_reported).tz_localize(None)
                                    else:
                                        ts = file_timestamp
                                    
                                    all_data.append({
                                        'timestamp': ts,
                                        'vehicle_id': vehicle_id,
                                        'lat': float(lat),
                                        'lon': float(lon),
                                        'provider': provider,
                                        'battery': props.get('battery') or props.get('current_range_meters')
                                    })
                    # Standard formats
                    elif 'data' in data and 'bikes' in data['data']:
                        vehicles = data['data']['bikes']
                    elif 'vehicles' in data:
                        vehicles = data['vehicles']
                    elif 'bikes' in data:
                        vehicles = data['bikes']
                    else:
                        vehicles = [data]
                elif isinstance(data, list):
                    vehicles = data
                
                # Process standard vehicle list
                for vehicle in vehicles:
                    if isinstance(vehicle, dict):
                        lat = vehicle.get('lat') or vehicle.get('latitude')
                        lon = vehicle.get('lon') or vehicle.get('lng') or vehicle.get('longitude')
                        vehicle_id = vehicle.get('id') or vehicle.get('bike_id') or vehicle.get('vehicle_id')
                        
                        if lat is not None and lon is not None:
                            # Try to get timestamp
                            ts = vehicle.get('timestamp') or vehicle.get('last_updated')
                            if ts is None:
                                ts = file_timestamp
                            elif isinstance(ts, (int, float)):
                                ts = datetime.fromtimestamp(ts)
                            else:
                                ts = pd.to_datetime(ts).tz_localize(None)
                            
                            all_data.append({
                                'timestamp': ts,
                                'vehicle_id': vehicle_id,
                                'lat': float(lat),
                                'lon': float(lon),
                                'provider': provider,
                                'battery': vehicle.get('battery')
                            })
            except Exception as e:
                print(f"Warning: Could not load {json_file.name}: {e}")
        
        # Load Parquet files if any
        for parquet_file in provider_path.glob('*.parquet'):
            try:
                df = pd.read_parquet(parquet_file)
                df['provider'] = provider
                all_data.extend(df.to_dict('records'))
            except Exception as e:
                print(f"Warning: Could not load {parquet_file}: {e}")
    
    if not all_data:
        print("Warning: No vehicle position data found, generating synthetic data for demo")
        return generate_synthetic_vehicle_data()
    
    df = pd.DataFrame(all_data)
    
    # Normalize timestamp to datetime (remove timezone for consistency)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    if df['timestamp'].dt.tz is not None:
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    
    # Drop rows without valid coordinates or timestamp
    df = df.dropna(subset=['lat', 'lon', 'timestamp'])
    
    print(f"Loaded {len(df)} vehicle position records from {df['provider'].nunique()} providers")
    
    return df


def load_weather_data(base_path: str = "sources") -> pd.DataFrame:
    """
    Load weather data.
    
    Args:
        base_path: Base directory path containing weather data
        
    Returns:
        DataFrame with columns: timestamp, temp_c, wind_speed, rain_mmph, condition
    """
    weather_path = Path(base_path) / 'environment' / 'weather'
    
    if not weather_path.exists():
        print(f"Warning: Weather data not found, generating synthetic weather data")
        return generate_synthetic_weather_data()
    
    all_weather = []
    
    # Load JSON files
    for json_file in weather_path.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            # Handle different response structures
            if isinstance(data, dict):
                weather_record = {
                    'timestamp': data.get('timestamp') or data.get('dt'),
                    'temp_c': data.get('temp_c') or data.get('main', {}).get('temp'),
                    'wind_speed': data.get('wind_speed') or data.get('wind', {}).get('speed'),
                    'rain_mmph': data.get('rain_mmph', 0),
                    'condition': data.get('condition') or data.get('weather', [{}])[0].get('main', 'clear')
                }
                all_weather.append(weather_record)
        except Exception as e:
            print(f"Warning: Could not load {json_file}: {e}")
    
    # Load Parquet files
    for parquet_file in weather_path.glob('*.parquet'):
        try:
            df = pd.read_parquet(parquet_file)
            all_weather.extend(df.to_dict('records'))
        except Exception as e:
            print(f"Warning: Could not load {parquet_file}: {e}")
    
    if not all_weather:
        return generate_synthetic_weather_data()
    
    df = pd.DataFrame(all_weather)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    df = df.dropna(subset=['timestamp'])
    
    print(f"Loaded {len(df)} weather records")
    
    return df


def aggregate_to_grid(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate vehicle positions to grid cells and time bins.
    
    Args:
        df: DataFrame with timestamp, vehicle_id, lat, lon, provider columns
        
    Returns:
        Aggregated DataFrame with columns:
            time_bin, cell_id, cell_x, cell_y, available_vehicles, provider_count
    """
    # Project to meters
    df = project_wgs84_to_meters(df)
    
    # Assign grid cells
    df = assign_grid_cells(df, cell_size_m=CELL_SIZE_M)
    
    # Round timestamp to 10-minute bins
    df['time_bin'] = df['timestamp'].dt.floor(f'{TIME_BIN_MINUTES}min')
    
    # Aggregate by time_bin and cell_id
    agg_df = df.groupby(['time_bin', 'cell_id', 'cell_x', 'cell_y']).agg({
        'vehicle_id': 'nunique',  # Count unique vehicles
        'provider': 'nunique'      # Count distinct providers
    }).reset_index()
    
    agg_df.columns = ['time_bin', 'cell_id', 'cell_x', 'cell_y', 'available_vehicles', 'provider_count']
    
    # Sort by time
    agg_df = agg_df.sort_values(['time_bin', 'cell_id']).reset_index(drop=True)
    
    print(f"Aggregated to {len(agg_df)} cell-time observations across {agg_df['cell_id'].nunique()} unique cells")
    
    return agg_df


def create_features(agg_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create features for demand forecasting model.
    
    Args:
        agg_df: Aggregated grid-time data
        weather_df: Weather data
        
    Returns:
        DataFrame with features and target variable
    """
    df = agg_df.copy()
    
    # Time features
    df['hour'] = df['time_bin'].dt.hour
    df['dow'] = df['time_bin'].dt.dayofweek
    df['is_weekend'] = (df['dow'] >= 5).astype(int)
    df['hour_of_week'] = df['dow'] * 24 + df['hour']
    
    # Lag features (availability at previous time bins)
    df = df.sort_values(['cell_id', 'time_bin'])
    
    for lag_bins in [1, 2]:  # 10min and 20min lags
        df[f'avail_lag_{lag_bins * TIME_BIN_MINUTES}'] = df.groupby('cell_id')['available_vehicles'].shift(lag_bins)
    
    # Forward fill missing lags within each cell (up to 3 bins)
    for col in [c for c in df.columns if c.startswith('avail_lag_')]:
        df[col] = df.groupby('cell_id')[col].ffill(limit=3).fillna(0)
    
    # Current availability
    df['avail_now'] = df['available_vehicles']
    
    # Weather features
    if not weather_df.empty:
        # Round weather timestamps to 10min bins
        weather_df = weather_df.copy()
        weather_df['time_bin'] = pd.to_datetime(weather_df['timestamp']).dt.floor(f'{TIME_BIN_MINUTES}min')
        # Remove timezone from weather time_bin to match aggregated data
        if weather_df['time_bin'].dt.tz is not None:
            weather_df['time_bin'] = weather_df['time_bin'].dt.tz_localize(None)
        
        # Aggregate weather to time bins (take mean)
        weather_agg = weather_df.groupby('time_bin').agg({
            'temp_c': 'mean',
            'wind_speed': 'mean',
            'rain_mmph': 'mean'
        }).reset_index()
        
        # Also ensure df time_bin has no timezone
        if df['time_bin'].dt.tz is not None:
            df['time_bin'] = df['time_bin'].dt.tz_localize(None)
        
        # Merge weather
        df = df.merge(weather_agg, on='time_bin', how='left')
        
        # Fill missing weather with forward/backward fill
        for col in ['temp_c', 'wind_speed', 'rain_mmph']:
            if col in df.columns:
                df[col] = df[col].ffill().bfill().fillna(0)
        
        df['is_raining'] = (df['rain_mmph'] > 0).astype(int)
    else:
        # Default weather features
        df['temp_c'] = 15.0
        df['wind_speed'] = 5.0
        df['rain_mmph'] = 0.0
        df['is_raining'] = 0
    
    # Neighbor features (spatial context)
    try:
        df = compute_neighbor_features(df, cell_size_m=CELL_SIZE_M)
    except Exception as e:
        print(f"Warning: Could not compute neighbor features: {e}")
        df['neighbors_mean_avail'] = 0.0
    
    # Target variable: demand in next 30 minutes
    # Demand = drop in availability (vehicles picked up)
    df = df.sort_values(['cell_id', 'time_bin'])
    df['future_availability'] = df.groupby('cell_id')['available_vehicles'].shift(-FORECAST_HORIZON_BINS)
    df['demand_30m'] = (df['available_vehicles'] - df['future_availability']).clip(lower=0)
    
    # Drop rows without valid target (last N bins of each cell)
    df_with_target = df.dropna(subset=['demand_30m']).copy()
    
    print(f"Created features for {len(df_with_target)} observations with valid targets")
    
    return df_with_target


def build_baseline_predictor(train_df: pd.DataFrame) -> Dict:
    """
    Build baseline predictor using historical averages by cell and hour-of-week.
    
    Args:
        train_df: Training data with demand_30m and hour_of_week columns
        
    Returns:
        Dict mapping (cell_id, hour_of_week) -> mean demand
    """
    baseline_stats = train_df.groupby(['cell_id', 'hour_of_week'])['demand_30m'].mean().to_dict()
    global_mean = train_df['demand_30m'].mean()
    
    def predict_baseline(cell_id, hour_of_week):
        return baseline_stats.get((cell_id, hour_of_week), global_mean)
    
    return {
        'stats': baseline_stats,
        'global_mean': global_mean,
        'predict': predict_baseline
    }


def train_model(train_df: pd.DataFrame, feature_cols: list) -> Tuple[object, Optional[StandardScaler]]:
    """
    Train demand forecasting model.
    
    Args:
        train_df: Training data
        feature_cols: List of feature column names
        
    Returns:
        Tuple of (trained model, scaler or None)
    """
    X_train = train_df[feature_cols].fillna(0)
    y_train = train_df['demand_30m'].values
    
    if LIGHTGBM_AVAILABLE:
        print("Training LightGBM model...")
        model = lgb.LGBMRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.05,
            num_leaves=31,
            random_state=RANDOM_STATE,
            verbose=-1
        )
        model.fit(X_train, y_train)
        scaler = None
    else:
        print("Training Ridge regression model...")
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        model = Ridge(alpha=1.0, random_state=RANDOM_STATE)
        model.fit(X_train_scaled, y_train)
    
    return model, scaler


def evaluate_model(
    model: object,
    scaler: Optional[StandardScaler],
    test_df: pd.DataFrame,
    feature_cols: list,
    baseline_predictor: Dict
) -> Dict:
    """
    Evaluate model performance on test set.
    
    Args:
        model: Trained model
        scaler: Feature scaler (or None)
        test_df: Test data
        feature_cols: List of feature column names
        baseline_predictor: Baseline predictor dict
        
    Returns:
        Dict with evaluation metrics
    """
    X_test = test_df[feature_cols].fillna(0)
    y_test = test_df['demand_30m'].values
    
    # Model predictions
    if scaler is not None:
        X_test_scaled = scaler.transform(X_test)
        y_pred = model.predict(X_test_scaled)
    else:
        y_pred = model.predict(X_test)
    
    # Clip negative predictions
    y_pred = np.maximum(y_pred, 0)
    
    # Baseline predictions
    y_baseline = test_df.apply(
        lambda row: baseline_predictor['predict'](row['cell_id'], row['hour_of_week']),
        axis=1
    ).values
    
    # Calculate metrics
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    baseline_mae = mean_absolute_error(y_test, y_baseline)
    
    # Avoid division by zero
    if baseline_mae > 0:
        improvement = (baseline_mae - mae) / baseline_mae * 100
    else:
        improvement = 0.0
    
    return {
        'mae': mae,
        'rmse': rmse,
        'baseline_mae': baseline_mae,
        'improvement': improvement
    }


def generate_forecast_and_rebalancing(
    df: pd.DataFrame,
    model: object,
    scaler: Optional[StandardScaler],
    feature_cols: list
) -> Tuple[pd.DataFrame, list]:
    """
    Generate forecast for most recent time bin and plan rebalancing.
    
    Args:
        df: Full feature DataFrame
        model: Trained model
        scaler: Feature scaler (or None)
        feature_cols: List of feature column names
        
    Returns:
        Tuple of (forecast_df, moves_list)
    """
    # Get most recent time bin
    latest_time = df['time_bin'].max()
    latest_df = df[df['time_bin'] == latest_time].copy()
    
    if latest_df.empty:
        print("Warning: No data for latest time bin")
        return pd.DataFrame(), []
    
    # Predict demand
    X = latest_df[feature_cols].fillna(0)
    if scaler is not None:
        X_scaled = scaler.transform(X)
        predictions = model.predict(X_scaled)
    else:
        predictions = model.predict(X)
    
    predictions = np.maximum(predictions, 0)
    
    # Build forecast DataFrame
    forecast_df = latest_df[['cell_id', 'cell_x', 'cell_y', 'available_vehicles']].copy()
    forecast_df['predicted_demand_30m'] = predictions
    forecast_df['projected_remaining'] = forecast_df['available_vehicles'] - forecast_df['predicted_demand_30m']
    
    # Add lat/lon centroids
    forecast_df['lat'] = forecast_df.apply(
        lambda row: cell_centroid_latlon(row['cell_x'], row['cell_y'], CELL_SIZE_M)[0],
        axis=1
    )
    forecast_df['lon'] = forecast_df.apply(
        lambda row: cell_centroid_latlon(row['cell_x'], row['cell_y'], CELL_SIZE_M)[1],
        axis=1
    )
    
    # Identify deficits and surpluses
    deficits_df = forecast_df[forecast_df['projected_remaining'] < 0].copy()
    deficits_df['need'] = -deficits_df['projected_remaining']
    
    # Only consider surplus cells with >2 projected remaining
    surpluses_df = forecast_df[forecast_df['projected_remaining'] > 2].copy()
    surpluses_df['surplus'] = surpluses_df['projected_remaining'] - 2  # Keep at least 2
    
    # Plan rebalancing
    cell_centroids = forecast_df.set_index('cell_id')[['lat', 'lon']].to_dict('index')
    cell_centroids = {k: (v['lat'], v['lon']) for k, v in cell_centroids.items()}
    
    moves = plan_rebalancing(deficits_df, surpluses_df, cell_centroids)
    
    print(f"Forecast generated for {len(forecast_df)} cells at {latest_time}")
    print(f"Identified {len(deficits_df)} deficit cells and {len(surpluses_df)} surplus cells")
    print(f"Planned {len(moves)} rebalancing moves")
    
    return forecast_df, moves


def generate_synthetic_vehicle_data() -> pd.DataFrame:
    """Generate synthetic vehicle position data for demo purposes."""
    np.random.seed(RANDOM_STATE)
    
    # Brussels approximate center
    center_lat, center_lon = 50.8503, 4.3517
    
    # Generate 7 days of data, every 10 minutes (no timezone)
    dates = pd.date_range(
        end=pd.Timestamp.now().tz_localize(None),
        periods=7 * 24 * 6,
        freq='10min'
    )
    
    data = []
    n_cells = 20
    
    for ts in dates:
        hour = ts.hour
        dow = ts.dayofweek
        
        # More vehicles during day, weekends
        base_count = 100 if 7 <= hour <= 20 else 50
        if dow >= 5:
            base_count *= 1.5
        
        n_vehicles = int(base_count + np.random.normal(0, 10))
        
        for i in range(n_vehicles):
            # Random location around center
            lat = center_lat + np.random.normal(0, 0.02)
            lon = center_lon + np.random.normal(0, 0.02)
            
            data.append({
                'timestamp': ts,
                'vehicle_id': f'v_{i % 500}',
                'lat': lat,
                'lon': lon,
                'provider': np.random.choice(['dott', 'bolt', 'lime']),
                'battery': np.random.randint(20, 100)
            })
    
    return pd.DataFrame(data)


def generate_synthetic_weather_data() -> pd.DataFrame:
    """Generate synthetic weather data for demo purposes."""
    np.random.seed(RANDOM_STATE)
    
    # Create dates without timezone
    dates = pd.date_range(
        end=pd.Timestamp.now().tz_localize(None),
        periods=7 * 24 * 6,
        freq='10min'
    )
    
    data = []
    for ts in dates:
        hour = ts.hour
        temp = 15 + 5 * np.sin((hour - 6) * np.pi / 12) + np.random.normal(0, 2)
        rain = max(0, np.random.normal(0, 0.5))
        
        data.append({
            'timestamp': ts,
            'temp_c': temp,
            'wind_speed': abs(np.random.normal(5, 2)),
            'rain_mmph': rain,
            'condition': 'rain' if rain > 0.5 else 'clear'
        })
    
    df = pd.DataFrame(data)
    return df


def main():
    """Main pipeline execution."""
    print("=" * 80)
    print("MICROMOBILITY DEMAND NOWCASTING & REBALANCING")
    print("=" * 80)
    
    # Determine base path
    script_dir = Path(__file__).parent
    base_path = script_dir.parent.parent
    
    # Load data
    print("\n[1/8] Loading vehicle position data...")
    vehicle_df = load_vehicle_positions(str(base_path))
    
    print("\n[2/8] Loading weather data...")
    weather_df = load_weather_data(str(base_path))
    
    # Aggregate to grid
    print("\n[3/8] Aggregating to spatial grid...")
    agg_df = aggregate_to_grid(vehicle_df)
    
    # Create features
    print("\n[4/8] Creating features...")
    feature_df = create_features(agg_df, weather_df)
    
    if len(feature_df) < 10:
        print("Error: Insufficient data for training. Need at least 10 observations.")
        return
    
    if len(feature_df) < 50:
        print(f"Warning: Limited data available ({len(feature_df)} observations). Results may be less accurate.")
    
    # Define feature columns
    feature_cols = [
        'hour', 'dow', 'is_weekend',
        'avail_now', 'avail_lag_10', 'avail_lag_20',
        'temp_c', 'wind_speed', 'rain_mmph', 'is_raining',
        'neighbors_mean_avail', 'provider_count'
    ]
    
    # Ensure all feature columns exist
    for col in feature_cols:
        if col not in feature_df.columns:
            feature_df[col] = 0
    
    # Train/test split by time
    print("\n[5/8] Splitting train/test by time...")
    
    # Check temporal range
    time_range = feature_df['time_bin'].max() - feature_df['time_bin'].min()
    
    # If less than 12 hours of data, use percentage split instead of last-day split
    if time_range < timedelta(hours=12):
        print(f"  Limited temporal range ({time_range}), using 80/20 split...")
        split_idx = int(len(feature_df) * 0.8)
        feature_df_sorted = feature_df.sort_values('time_bin')
        train_df = feature_df_sorted.iloc[:split_idx]
        test_df = feature_df_sorted.iloc[split_idx:]
    else:
        split_time = feature_df['time_bin'].max() - timedelta(days=1)
        train_df = feature_df[feature_df['time_bin'] < split_time]
        test_df = feature_df[feature_df['time_bin'] >= split_time]
    
    print(f"  Train: {len(train_df)} observations")
    print(f"  Test: {len(test_df)} observations")
    
    # Build baseline
    print("\n[6/8] Building baseline predictor...")
    baseline_predictor = build_baseline_predictor(train_df)
    
    # Train model
    print("\n[7/8] Training model...")
    model, scaler = train_model(train_df, feature_cols)
    
    # Evaluate
    print("\n[8/8] Evaluating model...")
    metrics = evaluate_model(model, scaler, test_df, feature_cols, baseline_predictor)
    
    # Generate forecast and rebalancing
    print("\nGenerating forecast and rebalancing plan...")
    forecast_df, moves = generate_forecast_and_rebalancing(feature_df, model, scaler, feature_cols)
    
    # Save model
    model_path = script_dir / 'model_artifact.pkl'
    try:
        with open(model_path, 'wb') as f:
            pickle.dump({'model': model, 'scaler': scaler, 'feature_cols': feature_cols}, f)
        print(f"Model saved to: {model_path}")
    except Exception as e:
        print(f"Warning: Could not save model: {e}")
    
    # Visualizations
    output_html = script_dir / 'output_map.html'
    output_csv = script_dir / 'output_forecast.csv'
    
    build_forecast_map(forecast_df, moves, str(output_html))
    export_forecast_csv(forecast_df, str(output_csv))
    
    # Print results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nTest MAE (ML Model): {metrics['mae']:.2f} vehicles")
    print(f"Test RMSE: {metrics['rmse']:.2f} vehicles")
    print(f"Baseline MAE: {metrics['baseline_mae']:.2f} vehicles")
    print(f"Improvement over baseline: {metrics['improvement']:.1f}%")
    
    print(f"\nTop {min(3, len(moves))} rebalancing moves:")
    for i, move in enumerate(moves[:3]):
        print(f"  {i+1}. Move {move['count']} vehicle(s) from {move['from_cell_id']} to {move['to_cell_id']} ({move['distance_m']:.0f}m)")
    
    if len(moves) > 3:
        print(f"  ... and {len(moves) - 3} more moves")
    
    print(f"\nHTML map: {output_html}")
    print(f"CSV forecast: {output_csv}")
    
    # Print markdown report
    REPORT_MD = f"""
# Micromobility Demand Nowcasting & Rebalancing

## Project Goal
Forecast micromobility demand (scooters/bikes) 30 minutes ahead for 250m x 250m grid cells
and propose vehicle rebalancing moves to optimize availability.

## Data Sources
- **Vehicle Positions**: {vehicle_df['provider'].nunique()} providers (dott, bolt, lime)
- **Weather**: Temperature, wind speed, rain intensity
- **Temporal Coverage**: {(feature_df['time_bin'].max() - feature_df['time_bin'].min()).days} days
- **Spatial Coverage**: {feature_df['cell_id'].nunique()} unique grid cells

## Modeling Approach
1. **Spatial Aggregation**: 250m x 250m grid cells using Web Mercator projection
2. **Temporal Aggregation**: 10-minute time bins
3. **Features**:
   - Time: hour, day-of-week, weekend indicator
   - Lag: vehicle availability at -10min, -20min
   - Weather: temperature, wind, rain
   - Spatial: neighboring cell average availability
4. **Target**: Demand = drop in availability over next 30 minutes
5. **Model**: {'LightGBM Regressor' if LIGHTGBM_AVAILABLE else 'Ridge Regression'}
6. **Baseline**: Historical mean demand by cell and hour-of-week

## Evaluation Metrics
- **Test MAE (Model)**: {metrics['mae']:.2f} vehicles
- **Test RMSE**: {metrics['rmse']:.2f} vehicles  
- **Baseline MAE**: {metrics['baseline_mae']:.2f} vehicles
- **Improvement**: {metrics['improvement']:.1f}%

## Rebalancing Strategy
- Identified **{len(forecast_df[forecast_df['projected_remaining'] < 0])} deficit cells** (demand > supply)
- Identified **{len(forecast_df[forecast_df['projected_remaining'] > 2])} surplus cells** (excess supply)
- Proposed **{len(moves)} rebalancing moves** using greedy nearest-neighbor matching
- Total vehicles to relocate: **{sum(m['count'] for m in moves)} vehicles**

## Outputs
- **Interactive Map**: `output_map.html` - Heatmap of demand + rebalancing arrows
- **Forecast CSV**: `output_forecast.csv` - Per-cell predictions and shortages

## Next Steps
1. **Integrate event data**: concerts, sports, festivals to capture demand spikes
2. **Dynamic pricing**: adjust pricing in high-demand / low-supply areas
3. **Operator integration**: API for real-time rebalancing dispatch
4. **Battery optimization**: prioritize moving high-battery vehicles
5. **Multi-horizon forecasting**: 60min, 90min, 2hr forecasts
6. **Causal inference**: A/B test rebalancing strategies in select zones
"""
    
    print("\n" + "=" * 80)
    print("REPORT SUMMARY")
    print("=" * 80)
    print(REPORT_MD)
    
    print("\n" + "=" * 80)
    print("Pipeline complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
