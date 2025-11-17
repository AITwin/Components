#!/usr/bin/env python3
"""
Historical data collector for micromobility demand nowcasting.

This script collects vehicle position snapshots every 10 minutes and saves them
with timestamps to build a historical dataset for training the forecasting model.

Usage:
    # Collect once
    python collect_historical_data.py
    
    # Collect every 10 minutes for 24 hours (run in background)
    python collect_historical_data.py --duration 24 --interval 10
"""

import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
import subprocess

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def collect_snapshot(provider: str, output_dir: Path):
    """Collect a single snapshot from a provider's API."""
    provider_path = Path(__file__).parent.parent.parent / provider / 'vehicle-position'
    fetch_script = provider_path / 'fetch_and_analyze.py'
    
    if not fetch_script.exists():
        print(f"⚠️  Fetch script not found for {provider}: {fetch_script}")
        return False
    
    try:
        # Run the fetch script
        result = subprocess.run(
            [sys.executable, str(fetch_script)],
            cwd=str(provider_path),
            capture_output=True,
            timeout=30
        )
        
        # Copy the response_sample.json with timestamp
        response_file = provider_path / 'response_sample.json'
        if response_file.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            snapshot_file = output_dir / provider / f'snapshot_{timestamp}.json'
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy with timestamp preserved in content
            with open(response_file, 'r') as f:
                data = json.load(f)
            
            # Add collection timestamp
            metadata = {
                'collection_timestamp': datetime.now().isoformat(),
                'provider': provider,
                'data': data
            }
            
            with open(snapshot_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✓ Collected {provider} snapshot: {snapshot_file.name}")
            return True
        else:
            print(f"⚠️  No response file for {provider}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout collecting {provider} data")
        return False
    except Exception as e:
        print(f"⚠️  Error collecting {provider}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Collect historical micromobility data')
    parser.add_argument('--duration', type=int, default=0, 
                       help='Collection duration in hours (0 = single snapshot)')
    parser.add_argument('--interval', type=int, default=10,
                       help='Collection interval in minutes (default: 10)')
    parser.add_argument('--output', type=str, default='historical_data',
                       help='Output directory for snapshots')
    
    args = parser.parse_args()
    
    output_dir = Path(__file__).parent / args.output
    output_dir.mkdir(exist_ok=True)
    
    providers = ['dott', 'bolt', 'lime']
    
    if args.duration == 0:
        # Single collection
        print(f"Collecting single snapshot from {len(providers)} providers...")
        for provider in providers:
            collect_snapshot(provider, output_dir)
        print(f"\n✅ Snapshots saved to: {output_dir}")
        print(f"\nTo collect time-series data, run:")
        print(f"  python {Path(__file__).name} --duration 24 --interval 10")
    else:
        # Periodic collection
        total_snapshots = int((args.duration * 60) / args.interval)
        print(f"Starting periodic collection:")
        print(f"  Duration: {args.duration} hours")
        print(f"  Interval: {args.interval} minutes")
        print(f"  Total snapshots: {total_snapshots}")
        print(f"  Output: {output_dir}\n")
        
        for i in range(total_snapshots):
            print(f"\n[Snapshot {i+1}/{total_snapshots}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            for provider in providers:
                collect_snapshot(provider, output_dir)
            
            if i < total_snapshots - 1:
                wait_seconds = args.interval * 60
                print(f"⏱️  Waiting {args.interval} minutes until next collection...")
                time.sleep(wait_seconds)
        
        print(f"\n✅ Collection complete! {total_snapshots} snapshots per provider saved to: {output_dir}")
        print(f"\nNow run the demand nowcasting pipeline:")
        print(f"  cd {Path(__file__).parent}")
        print(f"  python fetch_and_model.py")


if __name__ == '__main__':
    main()
