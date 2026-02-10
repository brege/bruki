# Image Activity

Plotting image activity over time from multiple sources and image types.

## Usage

Specify a key via `-k|--key`:

```bash
uv run activity # [
uv run activity --key screenshots
uv run activity -k internet
uv run activity -k camera
```

Set a custom output directory via `-o|--output-dir`: 

```bash
uv run activity -o images
```

## Features

- Add bands and markers for major life events
- Generate heatmaps over days of week and hours of day
- Timestamp, modified-time, EXIF, and regex parsing for refined picture-set slicing

## Output

Plots are written to `--output-dir` (default `images/`) with filenames prefixed by analysis key, for example:

- `screenshots_hourly.png`
- `internet_temporal.png`
- `camera_heatmap_phone.png`
