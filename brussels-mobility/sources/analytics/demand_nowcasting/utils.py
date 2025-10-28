"""
Utility functions for micromobility demand nowcasting and rebalancing.

This module provides spatial grid operations (projection, cell assignment, 
centroid conversion) and rebalancing logic for micromobility vehicles.
"""

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from pyproj import Transformer


def project_wgs84_to_meters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Project WGS84 lat/lon coordinates to meters using Web Mercator (EPSG:3857).
    
    Args:
        df: DataFrame with 'lat' and 'lon' columns
        
    Returns:
        DataFrame with added 'x' and 'y' columns in meters
    """
    df = df.copy()
    
    # Create transformer from WGS84 (EPSG:4326) to Web Mercator (EPSG:3857)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    
    # Transform lon, lat to x, y
    x, y = transformer.transform(df['lon'].values, df['lat'].values)
    
    df['x'] = x
    df['y'] = y
    
    return df


def assign_grid_cells(df: pd.DataFrame, cell_size_m: int = 250) -> pd.DataFrame:
    """
    Assign each point to a spatial grid cell based on x/y meter coordinates.
    
    Args:
        df: DataFrame with 'x' and 'y' columns in meters
        cell_size_m: Grid cell size in meters (default 250m)
        
    Returns:
        DataFrame with added 'cell_x', 'cell_y', and 'cell_id' columns
    """
    df = df.copy()
    
    # Compute grid cell coordinates (bottom-left corner of each cell)
    df['cell_x'] = (np.floor(df['x'] / cell_size_m) * cell_size_m).astype(int)
    df['cell_y'] = (np.floor(df['y'] / cell_size_m) * cell_size_m).astype(int)
    
    # Create unique cell identifier
    df['cell_id'] = df['cell_x'].astype(str) + '_' + df['cell_y'].astype(str)
    
    return df


def cell_centroid_latlon(cell_x: int, cell_y: int, cell_size_m: int = 250) -> Tuple[float, float]:
    """
    Convert grid cell coordinates back to WGS84 lat/lon centroid.
    
    Args:
        cell_x: Cell x-coordinate in meters (bottom-left corner)
        cell_y: Cell y-coordinate in meters (bottom-left corner)
        cell_size_m: Grid cell size in meters (default 250m)
        
    Returns:
        Tuple of (latitude, longitude) for the cell centroid
    """
    # Calculate centroid in meters
    centroid_x = cell_x + cell_size_m / 2
    centroid_y = cell_y + cell_size_m / 2
    
    # Transform back to WGS84
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(centroid_x, centroid_y)
    
    return float(lat), float(lon)


def get_neighbor_cells(cell_x: int, cell_y: int, cell_size_m: int = 250) -> List[str]:
    """
    Get the 8 neighboring cell IDs for a given cell.
    
    Args:
        cell_x: Cell x-coordinate in meters
        cell_y: Cell y-coordinate in meters
        cell_size_m: Grid cell size in meters (default 250m)
        
    Returns:
        List of neighbor cell_id strings
    """
    neighbors = []
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx == 0 and dy == 0:
                continue
            neighbor_x = cell_x + dx * cell_size_m
            neighbor_y = cell_y + dy * cell_size_m
            neighbors.append(f"{neighbor_x}_{neighbor_y}")
    return neighbors


def compute_neighbor_features(df: pd.DataFrame, cell_size_m: int = 250) -> pd.DataFrame:
    """
    Compute spatial context features from neighboring cells.
    
    Args:
        df: DataFrame with 'time_bin', 'cell_x', 'cell_y', 'cell_id', 'available_vehicles'
        cell_size_m: Grid cell size in meters (default 250m)
        
    Returns:
        DataFrame with added 'neighbors_mean_avail' column
    """
    df = df.copy()
    
    # Create a mapping of (time_bin, cell_id) -> available_vehicles
    avail_map = df.set_index(['time_bin', 'cell_id'])['available_vehicles'].to_dict()
    
    def get_neighbor_mean(row):
        neighbors = get_neighbor_cells(row['cell_x'], row['cell_y'], cell_size_m)
        neighbor_vals = []
        for neighbor_id in neighbors:
            key = (row['time_bin'], neighbor_id)
            if key in avail_map:
                neighbor_vals.append(avail_map[key])
        return np.mean(neighbor_vals) if neighbor_vals else 0.0
    
    df['neighbors_mean_avail'] = df.apply(get_neighbor_mean, axis=1)
    
    return df


def plan_rebalancing(
    deficits_df: pd.DataFrame,
    surpluses_df: pd.DataFrame,
    cell_centroids_dict: Dict[str, Tuple[float, float]]
) -> List[Dict]:
    """
    Plan rebalancing moves from surplus cells to deficit cells using greedy nearest-neighbor matching.
    
    Args:
        deficits_df: DataFrame with columns ['cell_id', 'cell_x', 'cell_y', 'need'] where need > 0
        surpluses_df: DataFrame with columns ['cell_id', 'cell_x', 'cell_y', 'surplus'] where surplus > 0
        cell_centroids_dict: Dict mapping cell_id -> (lat, lon) for distance calculation
        
    Returns:
        List of rebalancing moves, each a dict with keys:
            - from_cell_id: source cell
            - to_cell_id: destination cell
            - count: number of vehicles to move
            - distance_m: Euclidean distance in meters
    """
    moves = []
    
    if deficits_df.empty or surpluses_df.empty:
        return moves
    
    # Create working copies
    deficits = deficits_df.copy().sort_values('need', ascending=False).reset_index(drop=True)
    surpluses = surpluses_df.copy()
    surpluses['remaining'] = surpluses['surplus']
    
    # Process each deficit in order of urgency
    for _, deficit_row in deficits.iterrows():
        deficit_id = deficit_row['cell_id']
        need = deficit_row['need']
        deficit_x = deficit_row['cell_x']
        deficit_y = deficit_row['cell_y']
        
        # Find surpluses that still have vehicles available
        available_surpluses = surpluses[surpluses['remaining'] > 0].copy()
        
        if available_surpluses.empty:
            break  # No more vehicles to allocate
        
        # Calculate distances to all available surplus cells
        available_surpluses['distance'] = np.sqrt(
            (available_surpluses['cell_x'] - deficit_x) ** 2 +
            (available_surpluses['cell_y'] - deficit_y) ** 2
        )
        
        # Sort by distance and allocate from nearest first
        available_surpluses = available_surpluses.sort_values('distance')
        
        remaining_need = need
        
        for surplus_idx, surplus_row in available_surpluses.iterrows():
            if remaining_need <= 0:
                break
            
            surplus_id = surplus_row['cell_id']
            available = surplus_row['remaining']
            distance = surplus_row['distance']
            
            # Allocate as many vehicles as possible from this surplus cell
            to_move = min(remaining_need, available)
            
            if to_move > 0:
                moves.append({
                    'from_cell_id': surplus_id,
                    'to_cell_id': deficit_id,
                    'count': int(to_move),
                    'distance_m': float(distance)
                })
                
                # Update remaining surplus
                surpluses.loc[surplus_idx, 'remaining'] -= to_move
                remaining_need -= to_move
    
    return moves


def compute_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute Euclidean distance in meters between two lat/lon points using Web Mercator projection.
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
        
    Returns:
        Distance in meters
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x1, y1 = transformer.transform(lon1, lat1)
    x2, y2 = transformer.transform(lon2, lat2)
    
    return float(np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))
