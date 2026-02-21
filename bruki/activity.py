#!/usr/bin/env python3

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

from bruki import plots
from bruki.config import ConfigModel, load_config, resolve_events, resolve_paths


def parse_timestamp(filename: str, patterns: list[dict[str, Any]]) -> datetime | None:
    for pattern in patterns:
        # Filename regex selects which timestamp parser format to apply.
        if re.match(pattern["regex"], filename) is None:
            continue
        if "timestamp_regex" in pattern:
            # Regex captures timestamp components that are joined into one parse string.
            timestamp_match = re.match(pattern["timestamp_regex"], filename)
            if timestamp_match is None:
                continue
            return datetime.strptime(
                "".join(timestamp_match.groups()),
                pattern["timestamp_components_format"],
            )
        return datetime.strptime(filename, pattern["timestamp_format"])
    return None


def parse_exif_datetime(file_path: Path, method: str) -> datetime | None:
    exif_tag_names = {
        306: "DateTime",
        36867: "DateTimeOriginal",
        36868: "DateTimeDigitized",
    }
    if method == "exif-created":
        tag_priority = ["DateTimeOriginal", "DateTimeDigitized", "DateTime"]
    else:
        tag_priority = ["DateTime", "DateTimeDigitized", "DateTimeOriginal"]

    with Image.open(file_path) as image:
        exif = image.getexif()
    if not exif:
        return None

    values_by_name: dict[str, str] = {}
    for tag_id, tag_value in exif.items():
        tag_name = exif_tag_names.get(tag_id)
        if tag_name:
            values_by_name[tag_name] = str(tag_value)

    for tag_name in tag_priority:
        tag_value = values_by_name.get(tag_name)
        if not tag_value:
            continue
        try:
            return datetime.strptime(tag_value, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
    return None


def extract_timestamp(
    file_path: Path,
    methods: list[str],
    patterns: list[dict[str, Any]],
) -> datetime | None:
    for method in methods:
        if method == "modified-time":
            return datetime.fromtimestamp(file_path.stat().st_mtime)
        if method == "timestamp":
            timestamp = parse_timestamp(file_path.name, patterns)
            if timestamp is not None:
                return timestamp
            continue
        if method in {"exif-created", "exif-modified"}:
            timestamp = parse_exif_datetime(file_path, method)
            if timestamp is not None:
                return timestamp
            continue
    return None


def collect_rows(config: ConfigModel, set_name: str) -> pd.DataFrame:
    set_config = config.plots[set_name]
    columns = ["series", "source", "analysis", "timestamp", "hour", "day_of_week", "month", "date"]
    rows = []
    for series_name, source_name, file_paths in resolve_paths(config, series=set_config.series):
        series_config = config.data[series_name]
        methods = series_config.methods
        patterns = series_config.patterns
        for file_path in file_paths:
            timestamp = extract_timestamp(file_path, methods, patterns)
            rows.append(
                {
                    "series": series_name,
                    "source": source_name,
                    "analysis": set_name,
                    "timestamp": timestamp,
                    "hour": timestamp.hour if timestamp else None,
                    "day_of_week": timestamp.weekday() if timestamp else None,
                    "month": timestamp.month if timestamp else None,
                    "date": timestamp.date() if timestamp else None,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def run_set(config: ConfigModel, set_name: str, output_dir: str) -> None:
    dataframe = collect_rows(config, set_name)
    set_config = config.plots[set_name]
    if set_config.export_csv is not None:
        csv_path = Path(output_dir) / set_config.export_csv
        dataframe.to_csv(csv_path, index=False)
    if not set_config.figures:
        return
    plot_config = set_config.model_dump(mode="python", exclude_none=True)
    event_references = plot_config.get("events", [])
    if event_references:
        plot_config["event_items"] = resolve_events(config, event_references)
    data_config = {
        series_id: plots.SeriesSpec(label=series.label, color=series.color)
        for series_id, series in config.data.items()
    }
    plots.plot(dataframe, output_dir, set_name, plot_config, data_config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate activity plots")
    parser.add_argument("-c", "--config", default="config.yaml", help="configuration file path")
    parser.add_argument("-k", "--key", help="analysis key to run")
    parser.add_argument("-o", "--output-dir", help="override output directory for plots")
    args = parser.parse_args()

    config = load_config(args.config)
    output_dir = args.output_dir or config.output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if not args.key:
        for set_name in config.plots:
            print(f"Generating plots: {set_name}")
            run_set(config, set_name, output_dir)
        return

    print(f"Generating plots: {args.key}")
    run_set(config, args.key, output_dir)


if __name__ == "__main__":
    main()
