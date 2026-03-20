from __future__ import annotations

import json
from dataclasses import asdict

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


class BaseTerminalRenderer:
    def __init__(self, use_color: bool = True, use_unicode: bool = True) -> None:
        self.use_color = use_color
        self.use_unicode = use_unicode

    def render(self, results: list[InspectionResult], config: AppConfig) -> str:
        lines: list[str] = []
        for result in results:
            if lines:
                lines.append("")
            lines.extend(self._render_result(result, config))
        if config.report.show_summary:
            if lines:
                lines.append("")
            lines.extend(self._render_summary(results))
        return "\n".join(lines)

    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[str]:
        raise NotImplementedError

    def _render_summary(self, results: list[InspectionResult]) -> list[str]:
        ok = sum(1 for result in results if result.status == "ok")
        warnings = sum(1 for result in results if result.status == "warning")
        errors = sum(1 for result in results if result.status == "error")
        lines = ["Summary"]
        lines.append(f"  Files: {len(results)}")
        lines.append(f"  OK: {ok}")
        lines.append(f"  Warnings: {warnings}")
        lines.append(f"  Errors: {errors}")
        return lines

    def _status_icon(self, status: str) -> str:
        if status == "ok":
            return "✓" if self.use_unicode else "OK"
        if status == "warning":
            return "⚠" if self.use_unicode else "!"
        return "✖" if self.use_unicode else "x"

    def _status_color(self, status: str) -> str:
        return {"ok": "green", "warning": "yellow", "error": "red"}[status]

    def _bullet(self) -> str:
        return " · " if self.use_unicode else " - "

    def _divider(self) -> str:
        return " │ " if self.use_unicode else " | "

    def _compact_join(self, parts: list[str]) -> str:
        return self._bullet().join(part for part in parts if part)

    def _section_label(self, label: str, color: str) -> str:
        return self._colorize(label, color, bold=True)

    def _section_line(self, label: str, color: str, body: str) -> str:
        return f"{self._section_label(label, color)}{self._divider()}{body}"

    def _result_title(self, result: InspectionResult) -> str:
        title = self._base_title(result)
        if result.nfo and result.nfo.season is not None and result.nfo.episode is not None:
            return f"{title} S{result.nfo.season:02d}E{result.nfo.episode:02d}"
        return title

    def _base_title(self, result: InspectionResult) -> str:
        return result.nfo.title if result.nfo and result.nfo.title else result.path.stem

    def _meta_parts(self, result: InspectionResult, show_path: bool) -> list[str]:
        nfo = result.nfo
        parts = [self._colorize(self._base_title(result), self._status_color(result.status), bold=True)]
        if nfo and nfo.rating:
            parts.append(nfo.rating)
        if nfo and nfo.season is not None and nfo.episode is not None:
            parts.append(f"S{nfo.season:02d}E{nfo.episode:02d}")
        if nfo and (nfo.aired or nfo.premiered):
            parts.append(nfo.aired or nfo.premiered or "")
        if show_path:
            parts.append(result.display_path)
        return parts

    def _video_parts(self, result: InspectionResult, compact: bool) -> list[str]:
        if not result.media.video_tracks:
            return ["none"]
        track = result.media.video_tracks[0]
        if compact:
            parts = [
                f"{format_duration_minutes(result.media.duration_seconds)}",
                track.codec_display or track.codec or "unknown",
                self._compact_resolution(track),
            ]
            if track.dynamic_range:
                parts.append(track.dynamic_range)
            if track.fps is not None:
                parts.append(f"{format_fps(track.fps)} fps")
            return parts
        parts = [
            f"{format_duration_exact(result.media.duration_seconds)} (~{format_duration_minutes(result.media.duration_seconds)})",
            track.codec_display or track.codec or "unknown",
            track.resolution_label or "unknown",
            self._exact_resolution(track),
            track.aspect_ratio or "unknown",
            f"{format_fps(track.fps)} fps",
            format_bitrate(track.bitrate),
            track.dynamic_range or "unknown",
        ]
        return parts

    def _audio_parts(self, result: InspectionResult, compact: bool) -> list[str]:
        return self._limited_track_parts(
            result.media.audio_tracks,
            result.audio_languages,
            compact=compact,
            formatter=self._audio_track_summary,
        )

    def _subtitle_parts(self, result: InspectionResult, compact: bool) -> list[str]:
        return self._limited_track_parts(
            result.media.subtitle_tracks,
            result.subtitle_languages,
            compact=compact,
            formatter=self._subtitle_track_summary,
        )

    def _audio_track_summary(self, track: AudioTrack, compact: bool) -> str:
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

    def _subtitle_track_summary(self, track: SubtitleTrack, compact: bool) -> str:
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

    def _limited_track_parts(self, tracks, check, compact: bool, formatter) -> list[str]:
        shown_tracks = self._select_tracks_for_compact_output(tracks, check)
        parts = [formatter(track, compact=compact) for track in shown_tracks]
        if check.missing:
            parts.append(self._colorize(f"req {'/'.join(check.missing)}", "red"))
        if tracks:
            remaining = max(0, len(tracks) - len(shown_tracks))
            if remaining:
                parts.append(f"({remaining} more...)")
        if not parts:
            return ["none"]
        return parts

    def _requirements_line(self, result: InspectionResult) -> str | None:
        parts = []
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

        missing_present = bool(check.missing)
        max_tracks = 1 if missing_present else 2
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

    def _requirement_fragment(self, check) -> str | None:
        if not check.required:
            return None
        needed = "/".join(check.required)
        if not check.missing:
            symbol = "✓" if self.use_unicode else "ok"
            return self._colorize(f"req {needed} {symbol}", "green")
        missing = "/".join(check.missing)
        symbol = "✖" if self.use_unicode else "x"
        return self._colorize(f"req {needed} {symbol} {missing}", "yellow")

    def _requirement_summary(self, label: str, check) -> str | None:
        if not check.required:
            return None
        needed = "/".join(check.required)
        if not check.missing:
            symbol = "✓" if self.use_unicode else "ok"
            return self._colorize(f"{label} req {needed} {symbol}", "green")
        missing = "/".join(check.missing)
        symbol = "✖" if self.use_unicode else "x"
        return self._colorize(f"{label} req {needed} {symbol} missing {missing}", "red")

    def _issue_line(self, issues: list[InspectionIssue], compact: bool) -> str | None:
        tokens = [self._compact_issue(issue, compact=compact) for issue in issues]
        tokens = [token for token in tokens if token]
        if not tokens:
            return None
        return self._section_line("!", "red", self._compact_join(tokens))

    def _compact_issue(self, issue: InspectionIssue, compact: bool) -> str | None:
        if issue.code in {"missing_audio_languages", "missing_subtitle_languages"}:
            return None
        if issue.code == "nfo_out_of_sync":
            return "nfo drift"
        if issue.code == "probe_error":
            if compact:
                return "probe error"
            return issue.message
        return issue.message

    def _colorize(self, text: str, color: str, bold: bool = False) -> str:
        if not self.use_color:
            return text
        color_codes = {
            "red": "31",
            "green": "32",
            "yellow": "33",
            "blue": "34",
            "magenta": "35",
            "cyan": "36",
        }
        prefix = "\033[1;" if bold else "\033["
        return f"{prefix}{color_codes.get(color, '0')}m{text}\033[0m"


class DetailRenderer(BaseTerminalRenderer):
    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[str]:
        icon = self._colorize(
            f"{self._status_icon(result.status)} {self._result_title(result)}",
            self._status_color(result.status),
            bold=True,
        )
        lines = [icon]
        if config.report.show_path:
            lines.append(f"  Path: {result.display_path}")
        if result.issues:
            lines.append(
                f"  Flags: {self._colorize('; '.join(issue.message for issue in result.issues), self._status_color(result.status))}"
            )
        else:
            lines.append(f"  Flags: {self._colorize('none', 'green')}")

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

    def _render_meta(self, result: InspectionResult) -> list[str]:
        nfo = result.nfo
        title = (nfo.title if nfo else None) or result.path.stem
        lines = ["  Meta"]
        lines.append(f"    Title: {title}")
        lines.append(f"    Rating: {(nfo.rating if nfo else None) or 'unknown'}")
        lines.append(f"    Season: {nfo.season if nfo and nfo.season is not None else 'n/a'}")
        lines.append(f"    Episode: {nfo.episode if nfo and nfo.episode is not None else 'n/a'}")
        lines.append(f"    Aired/Premiered: {(nfo.aired or nfo.premiered) if nfo and (nfo.aired or nfo.premiered) else 'unknown'}")
        return lines

    def _render_video(self, result: InspectionResult) -> list[str]:
        lines = ["  Video"]
        if not result.media.video_tracks:
            lines.append("    No video streams detected")
            return lines
        for index, track in enumerate(result.media.video_tracks, start=1):
            label = f"Track {index}"
            if track.is_default:
                label += " [default]"
            lines.append(f"    {label}")
            lines.append(
                "      Duration: "
                f"{format_duration_minutes(result.media.duration_seconds)} "
                f"({format_duration_exact(result.media.duration_seconds)} exact)"
            )
            lines.append(f"      Codec: {track.codec_display or track.codec or 'unknown'}")
            lines.append(f"      Resolution: {track.resolution_label or 'unknown'}")
            lines.append(f"      Exact Resolution: {self._exact_resolution(track)}")
            lines.append(f"      Aspect Ratio: {track.aspect_ratio or 'unknown'}")
            lines.append(f"      FPS: {format_fps(track.fps)}")
            lines.append(f"      Bitrate: {format_bitrate(track.bitrate)}")
            lines.append(f"      Dynamic Range: {track.dynamic_range or 'unknown'}")
        return lines

    def _render_audio(self, result: InspectionResult) -> list[str]:
        lines = ["  Audio"]
        if not result.media.audio_tracks:
            lines.append("    No audio streams detected")
            return lines
        for index, track in enumerate(result.media.audio_tracks, start=1):
            label = f"Track {index}"
            if track.is_default:
                label += " [default]"
            lines.append(f"    {label}")
            lines.append(f"      Language: {track.language_name or track.language_code or 'unknown'}")
            lines.append(f"      Channel Format: {track.channel_label or 'unknown'}")
            lines.append(f"      Codec: {track.codec_display or track.codec or 'unknown'}")
            lines.append(f"      Branding: {track.branding or 'unknown'}")
            lines.append(f"      Sample Rate: {format_sample_rate(track.sample_rate)}")
            lines.append(f"      Bitrate: {format_bitrate(track.bitrate)}")
            if track.title:
                lines.append(f"      Extra: {track.title}")
        if result.audio_languages.required:
            lines.append(
                f"    Required Languages: {', '.join(result.audio_languages.required)}"
            )
            lines.append(
                f"    Missing Languages: {', '.join(result.audio_languages.missing) or 'none'}"
            )
        return lines

    def _render_subtitles(self, result: InspectionResult) -> list[str]:
        lines = ["  Subtitles"]
        if not result.media.subtitle_tracks:
            lines.append("    No subtitle streams detected")
        else:
            for index, track in enumerate(result.media.subtitle_tracks, start=1):
                label = f"Track {index}"
                if track.is_default:
                    label += " [default]"
                lines.append(f"    {label}")
                lines.append(f"      Language: {track.language_name or track.language_code or 'unknown'}")
                lines.append(f"      Format: {track.codec_display or track.codec or 'unknown'}")
                lines.append(f"      Extra: {track.extra_info or 'none'}")
        if result.subtitle_languages.required:
            lines.append(
                f"    Required Languages: {', '.join(result.subtitle_languages.required)}"
            )
            lines.append(
                f"    Missing Languages: {', '.join(result.subtitle_languages.missing) or 'none'}"
            )
        return lines


class BriefRenderer(BaseTerminalRenderer):
    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[str]:
        lines: list[str] = []
        if "meta" in config.report.sections:
            meta_body = self._compact_join(
                [f"{self._status_icon(result.status)}"] + self._meta_parts(result, config.report.show_path)
            )
            lines.append(self._section_line("M", "cyan", meta_body))
        if "video" in config.report.sections:
            lines.append(self._section_line("V", "blue", self._compact_join(self._video_parts(result, compact=False))))
        if "audio" in config.report.sections:
            lines.append(self._section_line("A", "green", self._compact_join(self._audio_parts(result, compact=False))))
        if "subtitles" in config.report.sections:
            lines.append(
                self._section_line("S", "yellow", self._compact_join(self._subtitle_parts(result, compact=False)))
            )
        requirements_line = self._requirements_line(result)
        if requirements_line:
            lines.append(requirements_line)
        issue_line = self._issue_line(result.issues, compact=False)
        if issue_line:
            lines.append(issue_line)
        return lines


class TerseRenderer(BaseTerminalRenderer):
    def _render_result(self, result: InspectionResult, config: AppConfig) -> list[str]:
        lines: list[str] = []
        header_parts = [f"{self._status_icon(result.status)}", self._colorize(self._result_title(result), self._status_color(result.status), bold=True)]
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
            non_requirement_issues = [issue for issue in result.issues if issue.code not in {"missing_audio_languages", "missing_subtitle_languages"}]
            issue_fragment = self._compact_join(
                [token for token in (self._compact_issue(issue, compact=True) for issue in non_requirement_issues) if token]
            )
            if issue_fragment:
                subtitle_parts.append(self._colorize(issue_fragment, "red"))
            lines.append(self._section_line("S", "yellow", self._compact_join(subtitle_parts)))
        else:
            issue_line = self._issue_line(result.issues, compact=True)
            if issue_line:
                lines.append(issue_line)
        requirements_line = self._requirements_line(result)
        if requirements_line:
            lines.append(requirements_line)
        return lines


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
    if normalized == "detail":
        return DetailRenderer(use_color=use_color, use_unicode=use_unicode)
    if normalized == "brief":
        return BriefRenderer(use_color=use_color, use_unicode=use_unicode)
    return TerseRenderer(use_color=use_color, use_unicode=use_unicode)
