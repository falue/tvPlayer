#!/bin/bash

# Variables
WIDTH=300  # Frame width
HEIGHT=168  # Frame height
DURATION=5
FRAMES=$((DURATION * 25))  # Assuming 25 frames per second
PIXELS=$((WIDTH * HEIGHT))  # Number of pixels per frame (1 byte per pixel)
BYTES_PER_FRAME=$PIXELS     # Each frame will use exactly one pixel per byte
RANDOM_DATA_FILES=(./white_noise/data/2024-09-01.bin ./white_noise/data/2024-09-02.bin ./white_noise/data/2024-09-03.bin ./white_noise/data/2024-09-04.bin ./white_noise/2024-09-05.bin ./white_noise/2024-09-06.bin)
TEMP_DIR="white_noise/_temp"  # Directory to store temp frames
TOTAL_BYTES_EXTRACTED=0       # Track total number of bytes extracted

# Create the white_noise/_temp directory if it doesn't exist
mkdir -p $TEMP_DIR

# Function to get file size in a cross-platform way
get_file_size() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        stat --format="%s" "$1"  # Linux stat
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        stat -f"%z" "$1"  # macOS stat
    else
        echo "Unsupported OS."
        exit 1
    fi
}

# Function to extract random bytes from the list of files
extract_random_bytes() {
    local output_file=$1
    local bytes_needed=$2
    local bytes_extracted=0

    > "$output_file"  # Create or empty the file

    for data_file in "${RANDOM_DATA_FILES[@]}"; do
        if [[ ! -f "$data_file" ]]; then
            echo "Random data file not found: $data_file"
            continue
        fi

        # Get the size of the current file
        available_bytes=$(get_file_size "$data_file")
        bytes_to_read=$((bytes_needed - bytes_extracted))

        # If the current file has enough bytes, read from it
        if (( available_bytes > TOTAL_BYTES_EXTRACTED )); then
            available_from_file=$((available_bytes - TOTAL_BYTES_EXTRACTED))
            if (( available_from_file >= bytes_to_read )); then
                dd if="$data_file" of="$output_file" bs=1 skip=$TOTAL_BYTES_EXTRACTED count=$bytes_to_read status=none
                TOTAL_BYTES_EXTRACTED=$((TOTAL_BYTES_EXTRACTED + bytes_to_read))
                return  # All needed bytes have been extracted
            else
                dd if="$data_file" of="$output_file" bs=1 skip=$TOTAL_BYTES_EXTRACTED count=$available_from_file status=none
                bytes_extracted=$((bytes_extracted + available_from_file))
                TOTAL_BYTES_EXTRACTED=0  # Reset counter for the next file
            fi
        fi
    done

    if (( bytes_extracted < bytes_needed )); then
        echo "Not enough data available in the provided files."
        exit 1
    fi
}

# Generate each frame
for ((i = 0; i < $FRAMES; i++)); do
    echo "Generating frame $((i + 1))..."

    # Extract the random bytes for the current frame
    extract_random_bytes "$TEMP_DIR/$(printf "%03d" $i).raw" $BYTES_PER_FRAME

    # Convert raw data into PNG (grayscale)
    ffmpeg -f rawvideo -pixel_format gray -video_size ${WIDTH}x${HEIGHT} -i $TEMP_DIR/$(printf "%03d" $i).raw $TEMP_DIR/$(printf "%03d" $i).png
done

# Check if all PNG files are present and readable before stitching them into a video
FRAME_LIST=""
for ((i = 0; i < $FRAMES; i++)); do
    FILE="$TEMP_DIR/$(printf "%03d" $i).png"
    if [[ -f "$FILE" && -r "$FILE" ]]; then
        FRAME_LIST+="$FILE|"
    else
        echo "Skipping missing or unreadable file: $FILE"
    fi
done

# Remove the last '|' from the list of frames
FRAME_LIST=${FRAME_LIST%|}

# Use ffmpeg to stitch PNG images into a video, skipping missing frames
if [[ -n "$FRAME_LIST" ]]; then
    ffmpeg -y -i "concat:$FRAME_LIST" -c:v libx264 -pix_fmt yuv420p white_noise/noise.mp4
else
    echo "No frames were found to create a video."
fi

# Clean up: delete the temporary directory and its contents
# rm -rf $TEMP_DIR

echo "White noise video created as noise.mp4 and temporary files cleaned up."
