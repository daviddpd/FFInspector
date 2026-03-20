from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .analysis import inspect_media_file
from .config import AppConfig, ConfigError, load_config
from .discovery import discover_media_paths
from .probe import FFProbeRunner
from .renderers import get_renderer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ffinspect",
        description="Inspect video files with ffprobe, compare sidecar NFO metadata, and audit language coverage.",
    )
    parser.add_argument("target", help="Media file or directory to inspect.")
    parser.add_argument("-c", "--config", help="Path to YAML config file.")
    parser.add_argument(
        "--format",
        choices=["terse", "brief", "detail", "table", "json", "terminal"],
        help="Report format override. 'terminal' is accepted as an alias for 'detail'.",
    )
    parser.add_argument(
        "--sections",
        help="Comma-separated report sections (meta,video,audio,subtitles).",
    )
    parser.add_argument(
        "--require-audio-language",
        action="append",
        default=[],
        help="Required audio language. May be passed multiple times.",
    )
    parser.add_argument(
        "--require-subtitle-language",
        action="append",
        default=[],
        help="Required subtitle language. May be passed multiple times.",
    )
    parser.add_argument(
        "--extensions",
        help="Comma-separated extensions to scan when the target is a directory.",
    )
    parser.add_argument("--ffprobe-path", help="Override ffprobe binary path.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse into directories.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config)) if args.config else AppConfig()
    except (OSError, ConfigError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    _apply_cli_overrides(config, args)

    try:
        targets = discover_media_paths(Path(args.target), config.scan)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not targets:
        print("No matching media files found.", file=sys.stderr)
        return 1

    probe_runner = FFProbeRunner(config.ffprobe_path)
    results = [
        inspect_media_file(
            path,
            probe_runner,
            config,
            display_path=_relative_display_path(Path(args.target), path),
            nfo_display_path=_relative_sidecar_path(Path(args.target), path.with_suffix(".nfo")),
        )
        for path in targets
    ]

    renderer = get_renderer(
        config.report.format,
        use_color=config.report.color and sys.stdout.isatty(),
        use_unicode=config.report.unicode,
    )
    print(renderer.render(results, config))
    return 0


def _apply_cli_overrides(config: AppConfig, args) -> None:
    if args.format:
        config.report.format = args.format
    if args.sections:
        config.report.sections = [item.strip() for item in args.sections.split(",") if item.strip()]
    if args.require_audio_language:
        config.requirements.audio_languages = list(args.require_audio_language)
    if args.require_subtitle_language:
        config.requirements.subtitle_languages = list(args.require_subtitle_language)
    if args.extensions:
        config.scan.extensions = [
            item.strip().lower() if item.strip().startswith(".") else f".{item.strip().lower()}"
            for item in args.extensions.split(",")
            if item.strip()
        ]
    if args.ffprobe_path:
        config.ffprobe_path = args.ffprobe_path
    if args.no_color:
        config.report.color = False
    if args.no_recursive:
        config.scan.recursive = False


def _relative_display_path(target: Path, candidate: Path) -> str:
    base = target if target.is_dir() else target.parent
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return candidate.name if target.is_file() else str(candidate)


def _relative_sidecar_path(target: Path, candidate: Path) -> str | None:
    if not candidate.exists():
        return None
    return _relative_display_path(target, candidate)
