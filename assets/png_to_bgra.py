from PIL import Image
import os

# Folder containing the PNG files
input_folder = "./channel_numbers"
output_folder = input_folder
# from -200 to 400
scales = [-200, -190, -180, -170, -160, -150, -140, -130, -120, -110, -100, -90, -80, -70, -60, -50, -40, -30, -20, -10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 260, 270, 280, 290, 300, 310, 320, 330, 340, 350, 360, 370, 380, 390, 400]

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
