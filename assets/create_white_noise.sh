#!/bin/bash

# Variables
WIDTH=300
HEIGHT=168
DURATION=5
FRAMES=$((DURATION * 25))  # Assuming 25 frames per second
PIXELS=$((WIDTH * HEIGHT))  # Number of pixels per frame
BYTES_PER_CALL=16000        # Maximum number of bytes per API call
CHUNKS=$((PIXELS * 1))      # Total bytes per frame (1 byte per pixel for grayscale)
API_URL="https://www.random.org/cgi-bin/randbyte?nbytes="
TEMP_DIR="white_noise/_temp"  # Updated to use white_noise/_temp directory
DELAY=2  # Delay between API calls in seconds

# Create the white_noise/_temp directory if it doesn't exist
mkdir -p $TEMP_DIR

# Function to fetch random data in chunks from random.org
fetch_random_bytes() {
    local required_bytes=$1
    local output_file=$2

    > $output_file  # Create or empty the file

    # Fetch bytes in chunks of 16,000 until the required bytes are collected
    while [ $required_bytes -gt 0 ]; do
        local bytes_to_fetch=$((required_bytes > BYTES_PER_CALL ? BYTES_PER_CALL : required_bytes))
        echo "Fetching $bytes_to_fetch bytes..."

        RESPONSE=$(curl -s "${API_URL}${bytes_to_fetch}&format=h")
        
        if [[ $RESPONSE == *"quota"* ]]; then
            echo "API quota for today exhausted. Exiting..."
            exit 1  # Stop the script if the daily quota is exhausted
        elif [ -n "$RESPONSE" ]; then
            echo "$RESPONSE" | xxd -r -p >> $output_file
        else
            echo "Failed to fetch random bytes. Retrying in $DELAY seconds..."
            sleep $DELAY
        fi

        required_bytes=$((required_bytes - bytes_to_fetch))
        sleep $DELAY  # Add delay between requests to avoid hitting speed limits
    done
}

# Generate each frame
for ((i = 0; i < $FRAMES; i++)); do
    echo "Generating frame $((i + 1))..."
    
    # Fetch random bytes and store them in a raw file
    fetch_random_bytes $CHUNKS $TEMP_DIR/frame_$i.raw

    # Convert raw data into PNG (grayscale)
    ffmpeg -f rawvideo -pixel_format gray -video_size ${WIDTH}x${HEIGHT} -i $TEMP_DIR/frame_$i.raw $TEMP_DIR/frame_$i.png
done

# Use ffmpeg to stitch PNG images into a video
ffmpeg -framerate 25 -i "$TEMP_DIR/frame_%d.png" -c:v libx264 -pix_fmt yuv420p noise.mp4

# Clean up: delete the temporary directory and its contents
rm -rf $TEMP_DIR

echo "White noise video created as noise.mp4 and temporary files cleaned up."
