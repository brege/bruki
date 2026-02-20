import fnmatch
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: str
    exclude: list[str] = Field(default_factory=list)


class DataSeriesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    label: str
    color: str
    methods: list[str]
    sources: dict[str, SourceConfig]
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)


class PlotConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    series: list[str]
    figures: list[dict[str, Any]] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    export_csv: str | None = None


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    output_dir: str = "images"
    extensions: list[str]
    anti_patterns: list[str] = Field(default_factory=list)
    events: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, DataSeriesConfig]
    plots: dict[str, PlotConfig]

    @model_validator(mode="after")
    def validate_analysis_references(self) -> "ConfigModel":
        known_series = set(self.data.keys())
        known_events = set(self.events.keys())
        for set_name, set_config in self.plots.items():
            missing_series = [
                series_name for series_name in set_config.series if series_name not in known_series
            ]
            if missing_series:
                raise ValueError(f"plots.{set_name} references unknown series: {missing_series}")
            missing_events = [
                event_name for event_name in set_config.events if event_name not in known_events
            ]
            if missing_events:
                raise ValueError(f"plots.{set_name} references unknown events: {missing_events}")
        for event_name, event_definition in self.events.items():
            if "events" in event_definition:
                raise ValueError(
                    f"events.{event_name} is a group; only direct event definitions are supported"
                )
        return self


def load_config(config_path: str) -> ConfigModel:
    config_file = Path(config_path).expanduser()
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    with config_file.open("r", encoding="utf-8") as file_handle:
        raw_config = yaml.safe_load(file_handle)
    return ConfigModel.model_validate(raw_config)


def resolve_events(
    config: ConfigModel,
    event_references: list[str],
) -> list[dict[str, Any]]:
    events_map = config.events
    unknown_events = [event_name for event_name in event_references if event_name not in events_map]
    if unknown_events:
        raise ValueError(f"Unknown events: {unknown_events}")
    return [events_map[event_name] for event_name in event_references]


def list_image_paths(
    source_spec: SourceConfig,
    extensions: list[str],
    anti_patterns: list[str],
) -> list[Path]:
    root_path = Path(source_spec.path).expanduser()
    if not root_path.exists():
        return []
    exclude_directories = source_spec.exclude
    extension_set = {extension.lower() for extension in extensions}
    matches: list[Path] = []
    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in extension_set:
            continue
        relative_path = file_path.relative_to(root_path)
        if any(
            exclude_directory in relative_path.parts for exclude_directory in exclude_directories
        ):
            continue
        if any(fnmatch.fnmatch(file_path.name, anti_pattern) for anti_pattern in anti_patterns):
            continue
        matches.append(file_path)
    return sorted(matches)
