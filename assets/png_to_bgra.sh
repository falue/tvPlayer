#!/bin/bash

# Folder containing the PNG files
input_folder="./volume_bars"

# Output folder for BGRA files
output_folder="$input_folder"

# Iterate over all PNG files in the folder
for file in "$input_folder"/*.png; do
    if [[ -f "$file" ]]; then
        # Get the base filename without extension
        filename=$(basename "$file" .png)
        # Convert PNG to raw BGRA format while retaining transparency
        ffmpeg -i "$file" -pix_fmt bgra -f rawvideo "$output_folder/$filename.bgra"
        echo "Converted $file to BGRA format"
    fi
done
