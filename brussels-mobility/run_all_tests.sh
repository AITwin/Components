#!/usr/bin/env bash
# Test runner for Brussels mobility project

set -e

PYTHON_EXE=".venv/bin/python"
if [ ! -f "$PYTHON_EXE" ]; then
    PYTHON_EXE="python3"
fi

echo "Brussels Mobility Tests"
echo "========================"
echo ""

# Use the new unified test runner
if [ -z "$1" ]; then
    $PYTHON_EXE tests/run_all_tests.py
else
    $PYTHON_EXE tests/run_all_tests.py "$1" "${@:2}"
fi
