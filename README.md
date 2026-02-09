# Image Activity

Plotting image activity over time from multiple sources and image types.

## Run

```bash
uv run activity --all
uv run activity --key screenshots
uv run activity --key memes
uv run activity --key camera
```

Set a custom output directory:

```bash
uv run activity --all --output-dir images
```

## Features

- Add bands and markers for major life events
- Generate heatmaps over days of week and hours of day
- Timestamp, mtime, exif, and regex pattern handlign for refined picture-set slicing

## Output

Plots are written to `--output-dir` (default `images/`) with filenames prefixed by analysis key, for example:

- `screenshots_hourly.png`
- `internet_temporal.png`
- `camera_heatmap_phone.png`
