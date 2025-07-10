import os
import glob
import zipfile
import re
import json

from io import BytesIO
from PIL import Image

def get_kmz_files():
    kmz_dir = "src/kmz"
    kmz_files = glob.glob(os.path.join(kmz_dir, '*.kmz'))
    return kmz_files

def find_cloakp_png_in_kmz(kmz_path):
    # Match files like cloakpN44W094.png (cloakp, then anything, then .png)
    pattern = re.compile(r'^cloakp.*\.png$', re.IGNORECASE)
    found_files = []
    with zipfile.ZipFile(kmz_path, 'r') as z:
        for name in z.namelist():
            if pattern.match(os.path.basename(name)):
                found_files.append(name)
    return found_files

def collect_cloakp_images_from_kmz_files():
    """
    Returns a dictionary: {cloakp file name: [image data from each kmz]}
    """
    kmz_files = get_kmz_files()
    cloakp_dict = {}

    # For each kmz, extract image data for each cloakp image
    for kmz_path in kmz_files:
        with zipfile.ZipFile(kmz_path, 'r') as z:
            # Find all cloakp image names in this kmz
            cloakp_names = find_cloakp_png_in_kmz(kmz_path)
            # Add new image names to the dict if not already present
            for name in cloakp_names:
                base_name = os.path.basename(name)
                if base_name not in cloakp_dict:
                    cloakp_dict[base_name] = []
                with z.open(name) as img_file:
                    image_data = img_file.read()
                    cloakp_dict[base_name].append(image_data)
    return cloakp_dict

color_map = {
    0: (0, 0, 0, 0), # Transparent
    1: (255, 0, 0, 255), # Red
    2: (255, 255, 0, 255), # Yellow
    3: (0, 255, 0, 255), # Green
}

def generate_overlap_visualizations(cloakp_dict):
    """
    For each image group in the dict, generates a new image where the color of each pixel
    depends on the number of overlapping opaque pixels at that location using the color_map.
    Returns a dict: {image name: PIL.Image object}
    """
    result_images = {}
    for img_name, img_datas in cloakp_dict.items():
        if not img_datas:
            continue

        # Open all images and convert to RGBA
        imgs = [Image.open(BytesIO(data)).convert('RGBA') for data in img_datas]
        width, height = imgs[0].size

        # Get alpha channels for all images
        alphas = [img.getchannel('A') for img in imgs]
        alpha_datas = [list(alpha.getdata()) for alpha in alphas]

        # Prepare output image (RGBA)
        out_img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        out_pixels = out_img.load()

        for y in range(height):
            for x in range(width):
                idx = y * width + x
                # Count how many images have opaque pixel at this location
                opaque_count = sum(alpha_data[idx] == 255 for alpha_data in alpha_datas)
                # Determine color based on count. If it's 0, it remains transparent.
                # If it is more than 0, use the color_map. If count exceeds the map, use the last color.
                if opaque_count == 0:
                    out_pixels[x, y] = color_map[0]
                else:
                    color_idx = opaque_count if opaque_count in color_map else max(color_map.keys())
                    if opaque_count > max(color_map.keys()):
                        color_idx = max(color_map.keys())
                    out_pixels[x, y] = color_map[color_idx]

        result_images[img_name] = out_img

    return result_images

def save_visualizations(result_images):
    """
    Saves the generated images to the 'visualizations' directory.
    """
    output_dir = "map_data"
    os.makedirs(output_dir, exist_ok=True)

    for img_name, img in result_images.items():
        img.save(os.path.join("map_data", img_name.replace("cloakp", "")), format="PNG")

def main():
    cloakp_dict = collect_cloakp_images_from_kmz_files()
    if not cloakp_dict:
        print("No cloakp images found in KMZ files.")
        return

    result_images = generate_overlap_visualizations(cloakp_dict)
    save_visualizations(result_images)
    print(f"Generated {len(result_images)} visualizations and saved to 'map_data' directory.")

    # Save list of PNG filenames to JSON
    png_names = [img_name.replace("cloakp", "") for img_name in result_images.keys()]
    json_path = os.path.join("map_data", "tiles.json")
    with open(json_path, "w") as f:
        json.dump(png_names, f)
    print(f"Saved list of PNG filenames to '{json_path}'.")

if __name__ == "__main__":
    main()