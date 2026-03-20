from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised implicitly in this environment
    yaml = None


DEFAULT_EXTENSIONS = [
    ".3gp",
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ogm",
    ".ogv",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
]

DEFAULT_SECTIONS = ["meta", "video", "audio", "subtitles"]


class ConfigError(ValueError):
    """Raised when configuration cannot be parsed."""


@dataclass
class ScanConfig:
    recursive: bool = True
    follow_symlinks: bool = False
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))


@dataclass
class ReportConfig:
    sections: list[str] = field(default_factory=lambda: list(DEFAULT_SECTIONS))
    color: bool = True
    unicode: bool = True
    format: str = "terse"
    show_path: bool = True
    show_summary: bool = True


@dataclass
class RequirementsConfig:
    audio_languages: list[str] = field(default_factory=list)
    subtitle_languages: list[str] = field(default_factory=list)


@dataclass
class ComparisonConfig:
    duration_tolerance_seconds: int = 60
    aspect_ratio_tolerance: float = 0.03


@dataclass
class AppConfig:
    scan: ScanConfig = field(default_factory=ScanConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    requirements: RequirementsConfig = field(default_factory=RequirementsConfig)
    comparison: ComparisonConfig = field(default_factory=ComparisonConfig)
    ffprobe_path: str = "ffprobe"


@dataclass
class _Line:
    number: int
    indent: int
    content: str


def load_config(path: Optional[Path]) -> AppConfig:
    if path is None:
        return AppConfig()
    raw = load_config_mapping(path)
    return config_from_mapping(raw)


def load_config_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise ConfigError("Top-level YAML document must be a mapping.")
        return loaded
    return _load_simple_yaml(text)


def config_from_mapping(raw: dict[str, Any]) -> AppConfig:
    scan_raw = _mapping(raw.get("scan"))
    report_raw = _mapping(raw.get("report"))
    requirements_raw = _mapping(raw.get("requirements"))
    comparison_raw = _mapping(raw.get("comparison"))
    return AppConfig(
        scan=ScanConfig(
            recursive=_to_bool(scan_raw.get("recursive"), True),
            follow_symlinks=_to_bool(scan_raw.get("follow_symlinks"), False),
            extensions=_normalize_extensions(scan_raw.get("extensions", DEFAULT_EXTENSIONS)),
        ),
        report=ReportConfig(
            sections=_string_list(report_raw.get("sections", DEFAULT_SECTIONS)),
            color=_to_bool(report_raw.get("color"), True),
            unicode=_to_bool(report_raw.get("unicode"), True),
            format=_normalize_report_format(report_raw.get("format", "terse")),
            show_path=_to_bool(report_raw.get("show_path"), True),
            show_summary=_to_bool(report_raw.get("show_summary"), True),
        ),
        requirements=RequirementsConfig(
            audio_languages=_string_list(requirements_raw.get("audio_languages", [])),
            subtitle_languages=_string_list(requirements_raw.get("subtitle_languages", [])),
        ),
        comparison=ComparisonConfig(
            duration_tolerance_seconds=_to_int(comparison_raw.get("duration_tolerance_seconds"), 60),
            aspect_ratio_tolerance=_to_float(comparison_raw.get("aspect_ratio_tolerance"), 0.03),
        ),
        ffprobe_path=str(raw.get("ffprobe_path", "ffprobe")),
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def _normalize_extensions(value: Any) -> list[str]:
    items = _string_list(value)
    normalized = []
    for item in items:
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        normalized.append(cleaned if cleaned.startswith(".") else f".{cleaned}")
    return normalized or list(DEFAULT_EXTENSIONS)


def _normalize_report_format(value: Any) -> str:
    normalized = str(value).strip().lower()
    if normalized == "terminal":
        return "detail"
    if normalized in {"detail", "brief", "terse", "json"}:
        return normalized
    return "terse"


def _load_simple_yaml(text: str) -> dict[str, Any]:
    lines: list[_Line] = []
    for index, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if "\t" in raw_line[:indent]:
            raise ConfigError(f"Tabs are not supported in fallback YAML parser (line {index}).")
        lines.append(_Line(number=index, indent=indent, content=raw_line.strip()))
    if not lines:
        return {}
    parsed, position = _parse_block(lines, 0, lines[0].indent)
    if position != len(lines):
        line = lines[position]
        raise ConfigError(f"Unable to parse configuration near line {line.number}.")
    if not isinstance(parsed, dict):
        raise ConfigError("Top-level YAML document must be a mapping.")
    return parsed


def _parse_block(lines: list[_Line], index: int, indent: int) -> tuple[Any, int]:
    if lines[index].content.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines: list[_Line], index: int, indent: int) -> tuple[dict[str, Any], int]:
    parsed: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent != indent:
            raise ConfigError(f"Unexpected indentation on line {line.number}.")
        if line.content.startswith("- "):
            raise ConfigError(f"Mixed list and mapping content on line {line.number}.")
        if ":" not in line.content:
            raise ConfigError(f"Expected key/value pair on line {line.number}.")
        key, raw_value = line.content.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if value:
            parsed[key] = _parse_scalar(value)
            index += 1
            continue
        index += 1
        if index >= len(lines) or lines[index].indent <= indent:
            parsed[key] = {}
            continue
        child, index = _parse_block(lines, index, lines[index].indent)
        parsed[key] = child
    return parsed, index


def _parse_list(lines: list[_Line], index: int, indent: int) -> tuple[list[Any], int]:
    parsed: list[Any] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent != indent:
            raise ConfigError(f"Unexpected indentation on line {line.number}.")
        if not line.content.startswith("- "):
            raise ConfigError(f"Expected a list item on line {line.number}.")
        value = line.content[2:].strip()
        if value:
            parsed.append(_parse_scalar(value))
            index += 1
            continue
        index += 1
        if index >= len(lines) or lines[index].indent <= indent:
            parsed.append(None)
            continue
        child, index = _parse_block(lines, index, lines[index].indent)
        parsed.append(child)
    return parsed, index


def _parse_scalar(value: str) -> Any:
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
