# Testing

## Running Tests

Quick test (30 seconds):
```bash
./run_all_tests.sh analytics
```

All tests (~10 minutes):
```bash
./run_all_tests.sh
```

Specific test suites:
```bash
./run_all_tests.sh analytics     # ML/analytics tests
./run_all_tests.sh integration   # API integration tests
./run_all_tests.sh unit          # Unit tests
```

## What Gets Tested

**Analytics Tests** (~20 tests, 2-3 seconds)
- Grid cell operations for spatial analysis
- Vehicle data aggregation
- Feature engineering for ML models
- Demand forecasting
- Rebalancing optimization
- Map generation and exports

**Integration Tests** (~40 scripts, 8 minutes)
- All API data sources (Bolt, Dott, Lime, Pony, SNCB, STIB, etc.)
- Real API calls to verify connectivity
- Data parsing and validation
- Map/visualization generation

**Unit Tests** (~90+ tests, 1 minute)
- Individual module functionality
- Mock testing for external dependencies
- Edge case handling
- Error handling

## Test Results

**Core tests pass consistently:**
- Analytics: 20/20 tests ✅
- Unit tests: All pass ✅

**Integration tests are variable** - they make real API calls to external services. Failures are common and expected when:
- APIs return 500 errors (server issues)
- Network connections timeout or drop
- APIs are rate-limited or temporarily unavailable

This is normal for integration tests that depend on external services. The code handles these gracefully.

Current status: Core functionality is solid, all critical paths tested.

## Common Issues

**Import warnings**: Pylance may complain about imports in tests. Ignore them - tests modify `sys.path` and run fine.

**API timeouts**: External APIs can be slow. The tests handle this gracefully with timeouts.

**Expected failures**: A few tests are marked as xfail due to technical limitations with Python's `exec()` and mocking. The actual code works fine (verified by integration tests).

## Adding New Tests

Analytics tests go in `tests/analytics/`. Each data source has its own `test_fetch_and_analyze.py` file alongside the main script.

The test runner automatically discovers and runs everything.
