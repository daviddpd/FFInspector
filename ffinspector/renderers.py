from __future__ import annotations

import io
import json
import shutil
from dataclasses import asdict

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import AppConfig
from .models import AudioTrack, InspectionIssue, InspectionResult, SubtitleTrack, VideoTrack
from .utils import (
    format_bitrate,
    format_duration_exact,
    format_duration_minutes,
    format_fps,
    format_sample_rate,
    normalize_language,
)


RenderablePart = Text | str | None


class BaseTerminalRenderer:
    def __init__(self, use_color: bool = True, use_unicode: bool = True) -> None:
        self.use_color = use_color
        self.use_unicode = use_unicode

    def _build_console(self, buffer: io.StringIO) -> Console:
        width = shutil.get_terminal_size((140, 40)).columns
        return Console(
            file=buffer,
            force_terminal=self.use_color,
            no_color=not self.use_color,
            color_system="standard" if self.use_color else None,
            emoji=self.use_unicode,
            highlight=False,
            markup=False,
            soft_wrap=True,
            width=width,
        )

    def render(self, results: list[InspectionResult], config: AppConfig) -> str:
        buffer = io.StringIO()
        console = self._build_console(buffer)

        for index, result in enumerate(results):
            if index:
                console.print()
            for line in self._render_result(result, config):
                console.print(self._to_text(line))

        if config.report.show_summary:
            if results:
                console.print()
            for line in self._render_summary(results):
                console.print(line)

        return buffer.getvalue().rstrip("\n")

    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[Text]:
        raise NotImplementedError

    def _render_summary(self, results: list[InspectionResult]) -> list[Text]:
        ok = sum(1 for result in results if result.status == "ok")
        warnings = sum(1 for result in results if result.status == "warning")
        errors = sum(1 for result in results if result.status == "error")
        return [
            Text("Summary"),
            Text(f"  Files: {len(results)}"),
            Text(f"  OK: {ok}"),
            Text(f"  Warnings: {warnings}"),
            Text(f"  Errors: {errors}"),
        ]

    def _status_icon(self, status: str) -> str:
        if status == "ok":
            return "✓" if self.use_unicode else "OK"
        if status == "warning":
            return "⚠" if self.use_unicode else "!"
        return "✖" if self.use_unicode else "x"

    def _status_color(self, status: str) -> str:
        return {"ok": "green", "warning": "yellow", "error": "red"}[status]

    def _title_color(self, status: str) -> str:
        if status == "error":
            return "red"
        return "yellow"

    def _bullet(self) -> str:
        return " · " if self.use_unicode else " - "

    def _divider(self) -> str:
        return " │ " if self.use_unicode else " | "

    def _styled(self, text: str, style: str) -> Text:
        return Text(text, style=style)

    def _to_text(self, part: RenderablePart) -> Text:
        if part is None:
            return Text()
        if isinstance(part, Text):
            return part.copy()
        return Text(str(part))

    def _compact_join(self, parts: list[RenderablePart]) -> Text:
        rendered = Text()
        first = True
        for part in parts:
            text = self._to_text(part)
            if not text.plain:
                continue
            if not first:
                rendered.append(self._bullet())
            rendered.append_text(text)
            first = False
        return rendered

    def _section_line(self, label: str, color: str, body: RenderablePart) -> Text:
        line = Text()
        line.append(label, style=f"bold {color}")
        line.append(self._divider())
        line.append_text(self._to_text(body))
        return line

    def _result_title(self, result: InspectionResult) -> str:
        title = self._base_title(result)
        if result.nfo and result.nfo.season is not None and result.nfo.episode is not None:
            return f"{title} S{result.nfo.season:02d}E{result.nfo.episode:02d}"
        return title

    def _base_title(self, result: InspectionResult) -> str:
        return result.nfo.title if result.nfo and result.nfo.title else result.path.stem

    def _meta_parts(self, result: InspectionResult, show_path: bool) -> list[RenderablePart]:
        nfo = result.nfo
        parts: list[RenderablePart] = [
            self._styled(self._base_title(result), f"bold {self._title_color(result.status)}")
        ]
        if nfo and nfo.rating:
            parts.append(nfo.rating)
        if nfo and nfo.season is not None and nfo.episode is not None:
            parts.append(f"S{nfo.season:02d}E{nfo.episode:02d}")
        if nfo and (nfo.aired or nfo.premiered):
            parts.append(nfo.aired or nfo.premiered or "")
        if show_path:
            parts.append(result.display_path)
        return parts

    def _video_parts(self, result: InspectionResult, compact: bool) -> list[RenderablePart]:
        if not result.media.video_tracks:
            return ["none"]
        track = result.media.video_tracks[0]
        if compact:
            parts: list[RenderablePart] = [
                f"{format_duration_minutes(result.media.duration_seconds)}",
                track.codec_display or track.codec or "unknown",
                self._compact_resolution(track),
            ]
            if track.dynamic_range:
                parts.append(track.dynamic_range)
            if track.fps is not None:
                parts.append(f"{format_fps(track.fps)} fps")
            return parts
        return [
            f"{format_duration_exact(result.media.duration_seconds)} (~{format_duration_minutes(result.media.duration_seconds)})",
            track.codec_display or track.codec or "unknown",
            track.resolution_label or "unknown",
            self._exact_resolution(track),
            track.aspect_ratio or "unknown",
            f"{format_fps(track.fps)} fps",
            format_bitrate(track.bitrate),
            track.dynamic_range or "unknown",
        ]

    def _audio_parts(self, result: InspectionResult, compact: bool) -> list[RenderablePart]:
        return self._limited_track_parts(
            result.media.audio_tracks,
            result.audio_languages,
            compact=compact,
            formatter=self._audio_track_summary,
        )

    def _subtitle_parts(self, result: InspectionResult, compact: bool) -> list[RenderablePart]:
        return self._limited_track_parts(
            result.media.subtitle_tracks,
            result.subtitle_languages,
            compact=compact,
            formatter=self._subtitle_track_summary,
        )

    def _audio_track_summary(self, track: AudioTrack, compact: bool) -> RenderablePart:
        language = track.language_code or track.language_name or "und"
        prefix = self._default_marker(track.is_default)
        quality = track.branding or track.codec_display or track.codec or "unknown"
        if compact:
            suffix = quality
            if track.channel_label:
                suffix += f"/{track.channel_label}"
            return f"{prefix}{language}:{suffix}"
        parts = [f"{prefix}{language}", quality]
        if track.channel_label:
            parts.append(track.channel_label)
        if track.sample_rate:
            parts.append(format_sample_rate(track.sample_rate))
        if track.title:
            parts.append(track.title)
        return " ".join(parts)

    def _subtitle_track_summary(self, track: SubtitleTrack, compact: bool) -> RenderablePart:
        language = track.language_code or track.language_name or "und"
        prefix = self._default_marker(track.is_default)
        codec = track.codec_display or track.codec or "unknown"
        extras = track.extra_info or ""
        if compact:
            token = f"{prefix}{language}:{codec}"
            if extras:
                token += f"({extras})"
            return token
        parts = [f"{prefix}{language}", codec]
        if extras:
            parts.append(extras)
        return " ".join(parts)

    def _default_marker(self, is_default: bool) -> str:
        if not is_default:
            return ""
        return "★" if self.use_unicode else "*"

    def _exact_resolution(self, track: VideoTrack) -> str:
        if track.width and track.height:
            return f"{track.width}x{track.height}"
        return "unknown"

    def _compact_resolution(self, track: VideoTrack) -> str:
        if track.resolution_label and track.width and track.height:
            return f"{track.resolution_label}/{track.width}x{track.height}"
        if track.width and track.height:
            return f"{track.width}x{track.height}"
        return track.resolution_label or "unknown"

    def _limited_track_parts(self, tracks, check, compact: bool, formatter) -> list[RenderablePart]:
        return self._track_preview_parts(
            tracks,
            check,
            compact=compact,
            formatter=formatter,
            include_requirement_marker=True,
        )

    def _track_preview_parts(
        self,
        tracks,
        check,
        compact: bool,
        formatter,
        include_requirement_marker: bool,
    ) -> list[RenderablePart]:
        shown_tracks = self._select_tracks_for_compact_output(tracks, check)
        parts: list[RenderablePart] = [formatter(track, compact=compact) for track in shown_tracks]
        if include_requirement_marker and check.missing:
            parts.append(self._styled(f"req {'/'.join(check.missing)}", "bold red"))
        if tracks:
            remaining = max(0, len(tracks) - len(shown_tracks))
            if remaining:
                parts.append(f"({remaining} more...)")
        if not parts:
            return ["none"]
        return parts

    def _requirements_line(self, result: InspectionResult) -> Text | None:
        parts: list[RenderablePart] = []
        audio_summary = self._requirement_summary("audio", result.audio_languages)
        if audio_summary:
            parts.append(audio_summary)
        subtitle_summary = self._requirement_summary("subs", result.subtitle_languages)
        if subtitle_summary:
            parts.append(subtitle_summary)
        if not parts:
            return None
        return self._section_line("!", "red", self._compact_join(parts))

    def _select_tracks_for_compact_output(self, tracks, check) -> list:
        if not tracks:
            return []

        max_tracks = 1 if check.missing else 2
        selected = []
        selected_indexes = set()

        default_track = next((track for track in tracks if track.is_default), None)
        if default_track is not None:
            selected.append(default_track)
            selected_indexes.add(id(default_track))

        if len(selected) < max_tracks:
            for required in check.required:
                match = next(
                    (
                        track
                        for track in tracks
                        if id(track) not in selected_indexes and self._track_matches_requirement(track, required)
                    ),
                    None,
                )
                if match is None:
                    continue
                selected.append(match)
                selected_indexes.add(id(match))
                if len(selected) >= max_tracks:
                    break

        if len(selected) < max_tracks:
            for track in tracks:
                if id(track) in selected_indexes:
                    continue
                selected.append(track)
                selected_indexes.add(id(track))
                if len(selected) >= max_tracks:
                    break

        return selected

    def _track_matches_requirement(self, track, requirement: str) -> bool:
        required_code, required_name = normalize_language(requirement)
        track_code, track_name = normalize_language(
            getattr(track, "language_code", None) or getattr(track, "language_name", None)
        )
        if required_code and track_code and required_code == track_code:
            return True
        if required_name and track_name and required_name == track_name:
            return True
        return False

    def _requirement_summary(self, label: str, check) -> Text | None:
        if not check.required:
            return None
        needed = "/".join(check.required)
        if not check.missing:
            symbol = "✓" if self.use_unicode else "ok"
            return self._styled(f"{label} req {needed} {symbol}", "green")
        missing = "/".join(check.missing)
        symbol = "✖" if self.use_unicode else "x"
        return self._styled(f"{label} req {needed} {symbol} missing {missing}", "bold red")

    def _issue_line(self, issues: list[InspectionIssue], compact: bool) -> Text | None:
        tokens = [self._compact_issue(issue, compact=compact) for issue in issues]
        tokens = [token for token in tokens if token is not None and self._to_text(token).plain]
        if not tokens:
            return None
        return self._section_line("!", "red", self._compact_join(tokens))

    def _issues_parts(self, issues: list[InspectionIssue], compact: bool) -> list[RenderablePart]:
        tokens = [self._compact_issue(issue, compact=compact) for issue in issues]
        return [token for token in tokens if token is not None and self._to_text(token).plain]

    def _compact_issue(self, issue: InspectionIssue, compact: bool) -> RenderablePart:
        if issue.code in {"missing_audio_languages", "missing_subtitle_languages"}:
            return None
        if issue.code == "nfo_out_of_sync":
            return self._styled("nfo drift", "red")
        if issue.code == "probe_error":
            if compact:
                return self._styled("probe error", "red")
            return self._styled(issue.message, "red")
        return self._styled(issue.message, "red")


class DetailRenderer(BaseTerminalRenderer):
    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[Text]:
        color = self._status_color(result.status)
        lines = [self._styled(f"{self._status_icon(result.status)} {self._result_title(result)}", f"bold {color}")]
        if config.report.show_path:
            lines.append(Text(f"  Path: {result.display_path}"))

        flags_line = Text("  Flags: ")
        if result.issues:
            flags_line.append_text(self._styled("; ".join(issue.message for issue in result.issues), color))
        else:
            flags_line.append_text(self._styled("none", "green"))
        lines.append(flags_line)

        section_builders = {
            "meta": self._render_meta,
            "video": self._render_video,
            "audio": self._render_audio,
            "subtitles": self._render_subtitles,
        }
        for section in config.report.sections:
            builder = section_builders.get(section)
            if builder is not None:
                lines.extend(builder(result))
        return lines

    def _render_meta(self, result: InspectionResult) -> list[Text]:
        nfo = result.nfo
        title = (nfo.title if nfo else None) or result.path.stem
        date_value = (nfo.aired or nfo.premiered) if nfo and (nfo.aired or nfo.premiered) else "unknown"
        return [
            Text("  Meta"),
            Text(f"    Title: {title}"),
            Text(f"    Rating: {(nfo.rating if nfo else None) or 'unknown'}"),
            Text(f"    Season: {nfo.season if nfo and nfo.season is not None else 'n/a'}"),
            Text(f"    Episode: {nfo.episode if nfo and nfo.episode is not None else 'n/a'}"),
            Text(f"    Aired/Premiered: {date_value}"),
        ]

    def _render_video(self, result: InspectionResult) -> list[Text]:
        lines = [Text("  Video")]
        if not result.media.video_tracks:
            lines.append(Text("    No video streams detected"))
            return lines
        for index, track in enumerate(result.media.video_tracks, start=1):
            label = f"Track {index}"
            if track.is_default:
                label += " [default]"
            lines.extend(
                [
                    Text(f"    {label}"),
                    Text(
                        "      Duration: "
                        f"{format_duration_minutes(result.media.duration_seconds)} "
                        f"({format_duration_exact(result.media.duration_seconds)} exact)"
                    ),
                    Text(f"      Codec: {track.codec_display or track.codec or 'unknown'}"),
                    Text(f"      Resolution: {track.resolution_label or 'unknown'}"),
                    Text(f"      Exact Resolution: {self._exact_resolution(track)}"),
                    Text(f"      Aspect Ratio: {track.aspect_ratio or 'unknown'}"),
                    Text(f"      FPS: {format_fps(track.fps)}"),
                    Text(f"      Bitrate: {format_bitrate(track.bitrate)}"),
                    Text(f"      Dynamic Range: {track.dynamic_range or 'unknown'}"),
                ]
            )
        return lines

    def _render_audio(self, result: InspectionResult) -> list[Text]:
        lines = [Text("  Audio")]
        if not result.media.audio_tracks:
            lines.append(Text("    No audio streams detected"))
            return lines
        for index, track in enumerate(result.media.audio_tracks, start=1):
            label = f"Track {index}"
            if track.is_default:
                label += " [default]"
            lines.extend(
                [
                    Text(f"    {label}"),
                    Text(f"      Language: {track.language_name or track.language_code or 'unknown'}"),
                    Text(f"      Channel Format: {track.channel_label or 'unknown'}"),
                    Text(f"      Codec: {track.codec_display or track.codec or 'unknown'}"),
                    Text(f"      Branding: {track.branding or 'unknown'}"),
                    Text(f"      Sample Rate: {format_sample_rate(track.sample_rate)}"),
                    Text(f"      Bitrate: {format_bitrate(track.bitrate)}"),
                ]
            )
            if track.title:
                lines.append(Text(f"      Extra: {track.title}"))
        if result.audio_languages.required:
            lines.append(Text(f"    Required Languages: {', '.join(result.audio_languages.required)}"))
            lines.append(Text(f"    Missing Languages: {', '.join(result.audio_languages.missing) or 'none'}"))
        return lines

    def _render_subtitles(self, result: InspectionResult) -> list[Text]:
        lines = [Text("  Subtitles")]
        if not result.media.subtitle_tracks:
            lines.append(Text("    No subtitle streams detected"))
        else:
            for index, track in enumerate(result.media.subtitle_tracks, start=1):
                label = f"Track {index}"
                if track.is_default:
                    label += " [default]"
                lines.extend(
                    [
                        Text(f"    {label}"),
                        Text(f"      Language: {track.language_name or track.language_code or 'unknown'}"),
                        Text(f"      Format: {track.codec_display or track.codec or 'unknown'}"),
                        Text(f"      Extra: {track.extra_info or 'none'}"),
                    ]
                )
        if result.subtitle_languages.required:
            lines.append(Text(f"    Required Languages: {', '.join(result.subtitle_languages.required)}"))
            lines.append(Text(f"    Missing Languages: {', '.join(result.subtitle_languages.missing) or 'none'}"))
        return lines


class BriefRenderer(BaseTerminalRenderer):
    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[Text]:
        lines: list[Text] = []
        if "meta" in config.report.sections:
            meta_body = self._compact_join([self._status_icon(result.status)] + self._meta_parts(result, config.report.show_path))
            lines.append(self._section_line("M", "cyan", meta_body))
        if "video" in config.report.sections:
            lines.append(self._section_line("V", "blue", self._compact_join(self._video_parts(result, compact=False))))
        if "audio" in config.report.sections:
            lines.append(self._section_line("A", "green", self._compact_join(self._audio_parts(result, compact=False))))
        if "subtitles" in config.report.sections:
            lines.append(self._section_line("S", "yellow", self._compact_join(self._subtitle_parts(result, compact=False))))
        requirements_line = self._requirements_line(result)
        if requirements_line:
            lines.append(requirements_line)
        issue_line = self._issue_line(result.issues, compact=False)
        if issue_line:
            lines.append(issue_line)
        return lines


class TerseRenderer(BaseTerminalRenderer):
    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[Text]:
        lines: list[Text] = []
        header_parts: list[RenderablePart] = [
            self._status_icon(result.status),
            self._styled(self._result_title(result), f"bold {self._title_color(result.status)}"),
        ]
        nfo = result.nfo
        if "meta" in config.report.sections:
            if nfo and nfo.rating:
                header_parts.append(nfo.rating)
            if nfo and (nfo.aired or nfo.premiered):
                header_parts.append(nfo.aired or nfo.premiered or "")
        if config.report.show_path:
            header_parts.append(result.display_path)
        lines.append(self._compact_join(header_parts))

        if "video" in config.report.sections:
            lines.append(self._section_line("V", "blue", self._compact_join(self._video_parts(result, compact=True))))
        if "audio" in config.report.sections:
            lines.append(self._section_line("A", "green", self._compact_join(self._audio_parts(result, compact=True))))
        if "subtitles" in config.report.sections:
            subtitle_parts = self._subtitle_parts(result, compact=True)
            non_requirement_issues = [
                issue
                for issue in result.issues
                if issue.code not in {"missing_audio_languages", "missing_subtitle_languages"}
            ]
            issue_tokens = [
                self._compact_issue(issue, compact=True)
                for issue in non_requirement_issues
            ]
            issue_tokens = [token for token in issue_tokens if token is not None and self._to_text(token).plain]
            if issue_tokens:
                subtitle_parts.append(self._compact_join(issue_tokens))
            lines.append(self._section_line("S", "yellow", self._compact_join(subtitle_parts)))
        else:
            issue_line = self._issue_line(result.issues, compact=True)
            if issue_line:
                lines.append(issue_line)

        requirements_line = self._requirements_line(result)
        if requirements_line:
            lines.append(requirements_line)
        return lines


class TableRenderer(BaseTerminalRenderer):
    def render(self, results: list[InspectionResult], config: AppConfig) -> str:
        buffer = io.StringIO()
        console = self._build_console(buffer)
        table = Table(
            box=box.SIMPLE_HEAVY if self.use_unicode else box.ASCII,
            header_style="bold cyan",
            show_lines=False,
            expand=False,
            pad_edge=False,
        )

        table.add_column("St", no_wrap=True, justify="center")
        table.add_column("Title", no_wrap=False)
        if "meta" in config.report.sections:
            table.add_column("Date", no_wrap=True)
        if "video" in config.report.sections:
            table.add_column("Video", no_wrap=False)
        if "audio" in config.report.sections:
            table.add_column("Audio", no_wrap=False)
        if "subtitles" in config.report.sections:
            table.add_column("Subs", no_wrap=False)
        if result_has_requirements(results):
            table.add_column("Req", no_wrap=False)
        if result_has_non_requirement_issues(results):
            table.add_column("Issues", no_wrap=False)
        if config.report.show_path:
            table.add_column("Path", no_wrap=False)

        for result in results:
            row: list[RenderablePart] = [self._styled(self._status_icon(result.status), self._status_color(result.status))]
            row.append(self._styled(self._result_title(result), f"bold {self._title_color(result.status)}"))

            if "meta" in config.report.sections:
                row.append(self._table_date_cell(result))
            if "video" in config.report.sections:
                row.append(self._compact_join(self._video_parts(result, compact=True)))
            if "audio" in config.report.sections:
                row.append(
                    self._compact_join(
                        self._track_preview_parts(
                            result.media.audio_tracks,
                            result.audio_languages,
                            compact=True,
                            formatter=self._audio_track_summary,
                            include_requirement_marker=False,
                        )
                    )
                )
            if "subtitles" in config.report.sections:
                row.append(
                    self._compact_join(
                        self._track_preview_parts(
                            result.media.subtitle_tracks,
                            result.subtitle_languages,
                            compact=True,
                            formatter=self._subtitle_track_summary,
                            include_requirement_marker=False,
                        )
                    )
                )
            if result_has_requirements(results):
                row.append(self._table_requirements_cell(result))
            if result_has_non_requirement_issues(results):
                row.append(self._table_issues_cell(result))
            if config.report.show_path:
                row.append(result.display_path)

            table.add_row(*(self._to_text(cell) for cell in row))

        console.print(table)
        if config.report.show_summary:
            console.print()
            for line in self._render_summary(results):
                console.print(line)
        return buffer.getvalue().rstrip("\n")

    def _table_date_cell(self, result: InspectionResult) -> str:
        if result.nfo and (result.nfo.aired or result.nfo.premiered):
            return result.nfo.aired or result.nfo.premiered or "-"
        return "-"

    def _table_requirements_cell(self, result: InspectionResult) -> Text:
        parts: list[RenderablePart] = []
        audio_summary = self._table_requirement_summary("A", result.audio_languages)
        if audio_summary:
            parts.append(audio_summary)
        subtitle_summary = self._table_requirement_summary("S", result.subtitle_languages)
        if subtitle_summary:
            parts.append(subtitle_summary)
        if not parts:
            return Text("-")
        return self._compact_join(parts)

    def _table_requirement_summary(self, label: str, check) -> RenderablePart:
        if not check.required:
            return None
        needed = "/".join(check.required)
        if not check.missing:
            symbol = "✓" if self.use_unicode else "ok"
            return self._styled(f"{label}:{needed} {symbol}", "green")
        missing = "/".join(check.missing)
        symbol = "✖" if self.use_unicode else "x"
        return self._styled(f"{label}:{needed} {symbol} {missing}", "bold red")

    def _table_issues_cell(self, result: InspectionResult) -> Text:
        parts = self._issues_parts(result.issues, compact=True)
        if not parts:
            return Text("-")
        return self._compact_join(parts)


class JsonRenderer:
    def render(self, results: list[InspectionResult], config: AppConfig) -> str:
        del config
        payload = []
        for result in results:
            data = asdict(result)
            data["path"] = result.display_path
            data["media"]["path"] = result.display_path
            if result.nfo is not None:
                data["nfo"]["path"] = result.nfo_display_path or result.display_path
            payload.append(data)
        return json.dumps(payload, indent=2)


def get_renderer(name: str, use_color: bool, use_unicode: bool):
    normalized = {"terminal": "detail"}.get(name, name)
    if normalized == "json":
        return JsonRenderer()
    if normalized == "table":
        return TableRenderer(use_color=use_color, use_unicode=use_unicode)
    if normalized == "detail":
        return DetailRenderer(use_color=use_color, use_unicode=use_unicode)
    if normalized == "brief":
        return BriefRenderer(use_color=use_color, use_unicode=use_unicode)
    return TerseRenderer(use_color=use_color, use_unicode=use_unicode)


def result_has_requirements(results: list[InspectionResult]) -> bool:
    return any(result.audio_languages.required or result.subtitle_languages.required for result in results)


def result_has_non_requirement_issues(results: list[InspectionResult]) -> bool:
    return any(
        any(issue.code not in {"missing_audio_languages", "missing_subtitle_languages"} for issue in result.issues)
        for result in results
    )
