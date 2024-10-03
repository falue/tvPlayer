from PIL import Image, ImageDraw, ImageFont
import os

# Customitzing
image_width = 1600                   # Image size
image_height = 150                  # Image size
font_size = 150                     # Set the size of the font
FONTCOLOR = (75, 255, 0, 255)       # Text color with full opacity (RGB with Alpha)
BGCOLOR = (255, 255, 255, 0)        # Background color (transparent)
custom_texts = [
    "----------       0",
    "|---------    10",
    "||--------    20",
    "|||-------    30",
    "||||------    40",
    "|||||-----    50",
    "||||||----    60",
    "|||||||---    70",
    "||||||||--    80",
    "|||||||||-    90",
    "|||||||||| 100"
]  # List of additional custom texts
font_path = "./W95FA-mono.ttf"           # Change this path if the font is installed elsewhere

# Output directory for saving the images
output_dir = "./volume_bars"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Load the font
try:
    font = ImageFont.truetype(font_path, font_size)
except IOError:
    print("Font not found. Ensure the font is installed and the path is correct.")
    exit()


# Function to generate image from a given text
def create_image(text, output_filename):
    # Create a new transparent image
    img = Image.new('RGBA', (image_width, image_height), BGCOLOR)

    # Create drawing object
    draw = ImageDraw.Draw(img)

    # Get text size to center the text
    text_width, text_height = draw.textbbox((0, 0), text, font=font)[2:]
    text_x = (image_width - text_width) / 2
    text_y = (image_height - text_height) / 2

    # Draw the text on the image
    draw.text((text_x, text_y), text, font=font, fill=FONTCOLOR)

    # Save the image as a PNG file
    output_path = os.path.join(output_dir, output_filename)
    img.save(output_path)

    print(f"Saved {output_path}")

# Generate images for custom texts
for index, text in enumerate(custom_texts):
    create_image(text, f"volume_{index*10}.png")

print("All images generated.")
