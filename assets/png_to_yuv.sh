#!/bin/bash

# Folder containing the PNG files
input_folder=".channel_numbers"

# Output folder for YUV files
output_folder="$input_folder"

# Iterate over all PNG files in the folder
for file in "$input_folder"/*.png; do
    if [[ -f "$file" ]]; then
        # Get the base filename without extension
        filename=$(basename "$file" .png)
        # Convert PNG to YUV
        ffmpeg -i "$file" -pix_fmt yuv420p "$output_folder/$filename.yuv"
        echo "Converted $file to YUV"
    fi
done
