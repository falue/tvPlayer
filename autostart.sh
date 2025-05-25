#!/bin/bash

# Get the directory of the currently running script (autorun.sh)
script_dir=$(dirname "$(realpath "$0")")
# Activate the virtual environment
source "$script_dir/venv/bin/activate"
# Run the Python script using the directory of this script
sudo python3 "$script_dir/tvPlayer.py"
