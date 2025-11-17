#!/usr/bin/env python3
"""
Unified test runner for the Brussels mobility project.

Runs all tests: unit tests, integration tests, and analytics tests.
"""
import subprocess
import sys
from pathlib import Path
import time
import argparse


def run_analytics_tests(verbose=False):
    """Run analytics unit tests (in tests/analytics/)."""
    print("\n" + "=" * 80)
    print("Running Analytics Tests")
    print("=" * 80)
    
    cmd = [sys.executable, "-m", "pytest", "tests/analytics/", "-v"]
    if not verbose:
        cmd.append("-q")
    
    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running analytics tests: {e}")
        return False


def run_integration_tests(verbose=False):
    """Run integration tests (fetch_and_analyze.py scripts)."""
    print("\n" + "=" * 80)
    print("Running Integration Tests")
    print("=" * 80)
    
    root_dir = Path(__file__).parent.parent / "sources"
    scripts = sorted(root_dir.rglob("fetch_and_analyze.py"))
    
    passed = 0
    failed = 0
    timeouts = []
    
    for i, script in enumerate(scripts, 1):
        rel_path = script.relative_to(Path(__file__).parent.parent)
        
        if verbose:
            print(f"\n[{i}/{len(scripts)}] {rel_path}")
        
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=120,  # Increased to 120 seconds for slow APIs
                cwd=script.parent
            )
            if result.returncode == 0:
                passed += 1
                if verbose:
                    print(f"  ✅ Passed")
            else:
                failed += 1
                print(f"  ❌ Failed: {rel_path}")
                if verbose:
                    if result.stderr:
                        print(f"  Error: {result.stderr[:200]}")
                    if result.stdout:
                        print(f"  Output: {result.stdout[-200:]}")
        except subprocess.TimeoutExpired:
            failed += 1
            timeouts.append(str(rel_path))
            print(f"  ⏱️  Timeout: {rel_path}")
        except Exception as e:
            failed += 1
            print(f"  ❌ Error: {rel_path} - {e}")
    
    print(f"\nIntegration tests: {passed}/{len(scripts)} passed")
    if timeouts:
        print(f"Note: {len(timeouts)} test(s) timed out (API may be slow)")
    return failed == 0


def run_unit_tests(verbose=False):
    """Run unit tests scattered in sources/."""
    print("\n" + "=" * 80)
    print("Running Unit Tests")
    print("=" * 80)
    
    root_dir = Path(__file__).parent.parent / "sources"
    test_files = []
    for pattern in ["test_samples.py"]:
        test_files.extend(root_dir.rglob(pattern))
    
    test_files = sorted(set(test_files))
    
    if not test_files:
        print("No unit test files found")
        return True
    
    passed = 0
    failed = 0
    
    for i, test_file in enumerate(test_files, 1):
        rel_path = test_file.relative_to(Path(__file__).parent.parent)
        
        if verbose:
            print(f"\n[{i}/{len(test_files)}] {rel_path}")
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file.name, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=test_file.parent
            )
            if result.returncode == 0:
                passed += 1
                if verbose:
                    print(f"  ✅ Passed")
            else:
                failed += 1
                print(f"  ❌ Failed: {rel_path}")
                if verbose and result.stderr:
                    print(f"  Error: {result.stderr[:200]}")
        except Exception as e:
            failed += 1
            print(f"  ❌ Error: {rel_path} - {e}")
    
    print(f"\nUnit tests: {passed}/{len(test_files)} passed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Run Brussels mobility project tests")
    parser.add_argument("suite", nargs="?", default="all",
                       choices=["all", "analytics", "integration", "unit"],
                       help="Which test suite to run (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Show detailed output")
    
    args = parser.parse_args()
    
    start_time = time.time()
    results = {}
    
    if args.suite in ["all", "analytics"]:
        results["analytics"] = run_analytics_tests(args.verbose)
    
    if args.suite in ["all", "integration"]:
        results["integration"] = run_integration_tests(args.verbose)
    
    if args.suite in ["all", "unit"]:
        results["unit"] = run_unit_tests(args.verbose)
    
    elapsed = time.time() - start_time
    
    # Summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    for suite, passed in results.items():
        status = "✅ Passed" if passed else "❌ Failed"
        print(f"{suite.capitalize()}: {status}")
    
    print(f"\nTotal time: {elapsed:.1f}s")
    
    all_passed = all(results.values())
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
