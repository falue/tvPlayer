from PIL import Image
import os

# Folder containing the PNG files
input_folder = "./channel_numbers"
output_folder = input_folder

# Iterate over all PNG files in the folder
for file in os.listdir(input_folder):
    if file.endswith(".png"):
        file_path = os.path.join(input_folder, file)
        img = Image.open(file_path).convert("RGBA")  # Ensure it's RGBA

        # Get the base filename without extension
        filename = os.path.splitext(file)[0]
        output_path = os.path.join(output_folder, f"{filename}.bgra")

        # Convert the image data to raw BGRA, making black pixels transparent
        raw_data = bytearray()
        for pixel in img.getdata():
            r, g, b, a = pixel  # RGBA format
            if (r, g, b) == (0, 0, 0):
                a = 0  # Make black pixels fully transparent
            raw_data.extend([b, g, r, a])  # BGRA format

        # Save as .bgra (raw file format)
        with open(output_path, "wb") as f:
            f.write(raw_data)

        print(f"Converted {file} to BGRA format with black pixels transparent.")
