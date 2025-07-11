import os
import io
import glob
import zipfile
import re
import json
import xml.etree.ElementTree as ET

from io import BytesIO
from PIL import Image

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from shortuuid import random

google_drive_folder_id = "1hnCj_7EFA-ngb73-jSF8xW2FckdIR4dx"


def download_kmz_files():
    SCOPES = [
        "https://www.googleapis.com/auth/drive.metadata.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    service = build("drive", "v3", credentials=creds)

    results = (
        service.files()
        .list(
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType)",
            q=f"'{google_drive_folder_id}' in parents",
        )
        .execute()
    )
    items = results.get("files", [])

    if not items:
        print("No files found.")
        return
    os.makedirs("kmz", exist_ok=True)
    downloaded_files = []

    def download_file(item):
        if item["name"].lower().endswith(".kmz"):
            file_id = item["id"]
            file_name = item["name"]
            file_path = os.path.join("kmz", file_name)
            print(f"Downloading {file_name}... ", end="")
            if os.path.exists(file_path):
                print(f"file already exists, skipping.")
                return file_name
            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(file_path, "wb")
            downloader = MediaIoBaseDownload(fh, request)
            done = False

            while not done:
                status, done = downloader.next_chunk()
            print(f"Done")
            return file_name
        return None

    # Remove concurrent.futures usage, use a simple for loop
    for item in items:
        result = download_file(item)
        if result:
            downloaded_files.append(result)

    return downloaded_files


def get_kmz_files():
    kmz_dir = "kmz"
    kmz_files = glob.glob(os.path.join(kmz_dir, "*.kmz"))
    return kmz_files


def find_cloakp_png_in_kmz(kmz_path):
    # Match files like cloakpN44W094.png (cloakp, then anything, then .png)
    pattern = re.compile(r"^cloakp.*\.png$", re.IGNORECASE)
    found_files = []
    with zipfile.ZipFile(kmz_path, "r") as z:
        for name in z.namelist():
            if pattern.match(os.path.basename(name)):
                found_files.append(name)
    return found_files


def collect_data_from_kmz_files():
    """
    Returns a tuple:
      - cloakp_dict: {cloakp file name: [image data from each kmz]}
      - node_positions: [{name, lat, long, alt} for each kmz]
    """
    kmz_files = get_kmz_files()
    cloakp_dict = {}
    node_positions = []

    for kmz_path in kmz_files:
        with zipfile.ZipFile(kmz_path, "r") as z:
            # Find all cloakp image names in this kmz
            cloakp_names = find_cloakp_png_in_kmz(kmz_path)
            for name in cloakp_names:
                base_name = os.path.basename(name)
                if base_name not in cloakp_dict:
                    cloakp_dict[base_name] = []
                with z.open(name) as img_file:
                    image_data = img_file.read()
                    cloakp_dict[base_name].append(image_data)

            # Find the KML file (endswith .kml)
            kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if kml_names:
                with z.open(kml_names[0]) as kml_file:
                    kml_data = kml_file.read()
                    # Parse KML XML
                    try:
                        root = ET.fromstring(kml_data)
                        ns = {"kml": "http://earth.google.com/kml/2.1"}
                        # Find Placemark with <Snippet>position of viewer</Snippet>
                        placemarks = root.findall(".//kml:Placemark", ns)
                        for pm in placemarks:
                            snippet = pm.find("kml:Snippet", ns)
                            if (
                                snippet is not None
                                and snippet.text == "position of viewer"
                            ):
                                name_elem = pm.find("kml:name", ns)
                                point = pm.find("kml:Point", ns)
                                coords_elem = (
                                    point.find("kml:coordinates", ns)
                                    if point is not None
                                    else None
                                )
                                if name_elem is not None and coords_elem is not None:
                                    coords = coords_elem.text.strip().split(",")
                                    if len(coords) >= 3:
                                        node_positions.append(
                                            {
                                                "name": name_elem.text,
                                                "lat": float(coords[1]),
                                                "long": float(coords[0]),
                                                "alt": float(coords[2]),
                                            }
                                        )
                                break
                    except Exception as e:
                        print(f"Error parsing KML in {kmz_path}: {e}")

    return cloakp_dict, node_positions


# def get_color_from_overlapping_pixels(opaque_count):
#     color_map = {
#         0: (0, 0, 0, 0),  # Transparent
#         1: (255, 0, 0, 255),  # Red
#         2: (255, 255, 0, 255),  # Yellow
#         3: (0, 255, 0, 255),  # Green
#     }
#     # Determine color based on count. If it's 0, it remains transparent.
#     # If it is more than 0, use the color_map. If count exceeds the map, use the last color.
#     if opaque_count == 0:
#         return color_map[0]
#     else:
#         color_idx = opaque_count if opaque_count in color_map else max(color_map.keys())
#         if opaque_count > max(color_map.keys()):
#             color_idx = max(color_map.keys())
#         return color_map[color_idx]


def get_color_from_overlapping_pixels(opaque_count):
    base_color = (255, 0, 0, 0)
    max_opaque_count = 10
    if opaque_count == 0:
        return (0, 0, 0, 0)  # Transparent

    # Generate a color based on the count
    alpha = int(255 * (opaque_count / max_opaque_count))
    # Ensure alpha is between 0 and 255
    alpha = max(0, min(255, alpha))
    # Return the base color with the calculated alpha
    return (base_color[0], base_color[1], base_color[2], alpha)


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
        imgs = [Image.open(BytesIO(data)).convert("RGBA") for data in img_datas]
        width, height = imgs[0].size

        # Get alpha channels for all images
        alphas = [img.getchannel("A") for img in imgs]
        alpha_datas = [list(alpha.getdata()) for alpha in alphas]

        # Prepare output image (RGBA)
        out_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        out_pixels = out_img.load()

        for y in range(height):
            for x in range(width):
                idx = y * width + x
                # Count how many images have opaque pixel at this location
                opaque_count = sum(alpha_data[idx] == 255 for alpha_data in alpha_datas)
                # Get the color for this pixel based on the count
                color = get_color_from_overlapping_pixels(opaque_count)
                out_pixels[x, y] = color

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


def anonymize_node_positions(node_positions):
    """
    Anonymizes the node positions offsetting the latitude and longitude by a small random value.
    """
    anonymized_positions = []
    for lat, lon in node_positions:
        # Offset by a small random value
        lat += random.uniform(-0.005, 0.005)
        lon += random.uniform(-0.005, 0.005)
        anonymized_positions.append((lat, lon))
    return anonymized_positions


def main():
    # Download KMZ files from Google Drive
    print("Downloading KMZ files from Google Drive...")
    downloaded_files = download_kmz_files()
    if not downloaded_files:
        print("No KMZ files downloaded.")
        return
    print(f"Downloaded {len(downloaded_files)} KMZ files.")
    cloakp_dict, node_positions = collect_data_from_kmz_files()
    node_positions = anonymize_node_positions(node_positions)
    if not cloakp_dict:
        print("No cloakp images found in KMZ files.")
        return

    print("Generating visualizations for overlapping cloakp images...")
    result_images = generate_overlap_visualizations(cloakp_dict)
    save_visualizations(result_images)
    print(
        f"Generated {len(result_images)} visualizations and saved to 'map_data' directory."
    )

    # Save list of PNG filenames to JSON
    png_names = [img_name.replace("cloakp", "") for img_name in result_images.keys()]
    json_path = os.path.join("map_data", "tiles.json")
    with open(json_path, "w") as f:
        json.dump(png_names, f)
    print(f"Saved list of PNG filenames to '{json_path}'.")

    # Save node_positions to JSON
    node_json_path = os.path.join("map_data", "nodes.json")
    with open(node_json_path, "w") as f:
        json.dump(node_positions, f)
    print(f"Saved node positions to '{node_json_path}'.")


if __name__ == "__main__":
    main()
