# MSP Mesh Splash Map

This project generates map tile visualizations showing overlapping coverage from multiple KMZ files containing PNG overlays. The output is a set of PNG images and a JSON index, suitable for use in mapping applications.

## Features

- Extracts overlays from KMZ files in Google Drive.
- Combines overlays to visualize overlapping coverage using color coding:
  - Red: 1 overlay
  - Yellow: 2 overlays
  - Green: 3 or more overlays
- Outputs PNG tiles and a `tiles.json` index in `map_data/`

## Requirements

- Python 3.11+
- [Pillow](https://python-pillow.org/) (Python Imaging Library)

## GitHub Actions Workflow

A GitHub Actions workflow (`.github/workflows/generate-map-tiles.yml`) is provided to automate tile generation and commit the results to the repository. You can trigger it manually from the Actions tab.

## Output

- `map_data/`: Contains generated PNG tiles and `tiles.json`
- `tiles.json`: List of generated PNG filenames

## License

MIT License
