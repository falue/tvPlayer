#!/bin/bash

# Get the directory of the currently running script (autorun.sh)
SCRIPT_LOCATION=$(dirname "$(realpath "$0")")
# wait for screen to be available
sleep 5
# Activate the virtual environment
source "$SCRIPT_LOCATION/venv/bin/activate"
# Run the Python script using the directory of this script
python3 "$SCRIPT_LOCATION/tvPlayer.py"
