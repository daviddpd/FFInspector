from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .models import AudioTrack, MediaInfo, SubtitleTrack, VideoTrack
from .utils import (
    aspect_ratio,
    channel_label,
    detect_dynamic_range,
    infer_audio_branding,
    normalize_codec_display,
    normalize_language,
    normalize_video_codec,
    resolution_label,
    safe_fraction,
)


class FFProbeRunner:
    def __init__(self, probe_path: str = "ffprobe") -> None:
        self.probe_path = probe_path
        self._resolved_binary: Optional[str] = None
        self._availability_error: Optional[str] = None

    def inspect(self, media_path: Path) -> MediaInfo:
        info = MediaInfo(path=media_path)
        probe_binary = self._resolve_binary()
        if probe_binary is None:
            info.probe_error = self._availability_error or "ffprobe is not available."
            return info

        command = [
            probe_binary,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(media_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            info.probe_error = stderr or "ffprobe could not inspect this file."
            return info
        except OSError as exc:
            info.probe_error = str(exc)
            return info

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            info.probe_error = "ffprobe returned invalid JSON."
            return info

        return self._parse_payload(media_path, payload)

    def _resolve_binary(self) -> Optional[str]:
        if self._resolved_binary is not None:
            return self._resolved_binary
        if self._availability_error is not None:
            return None

        if Path(self.probe_path).is_absolute():
            if Path(self.probe_path).exists():
                self._resolved_binary = self.probe_path
                return self._resolved_binary
            self._availability_error = f"ffprobe binary not found at {self.probe_path}."
            return None

        resolved = shutil.which(self.probe_path)
        if resolved:
            self._resolved_binary = resolved
            return resolved
        self._availability_error = (
            f"ffprobe was not found on PATH. Install FFmpeg or set ffprobe_path in config."
        )
        return None

    def _parse_payload(self, media_path: Path, payload: dict) -> MediaInfo:
        format_info = payload.get("format") or {}
        streams = payload.get("streams") or []
        info = MediaInfo(
            path=media_path,
            format_name=format_info.get("format_name"),
            duration_seconds=_to_float(format_info.get("duration")),
            container_bitrate=_to_int(format_info.get("bit_rate")),
        )

        for stream in streams:
            stream_type = stream.get("codec_type")
            if stream_type == "video":
                info.video_tracks.append(self._parse_video_track(stream, info.container_bitrate))
            elif stream_type == "audio":
                info.audio_tracks.append(self._parse_audio_track(stream))
            elif stream_type in {"subtitle", "data"}:
                subtitle = self._parse_subtitle_track(stream)
                if subtitle is not None:
                    info.subtitle_tracks.append(subtitle)
        return info

    def _parse_video_track(self, stream: dict, container_bitrate: Optional[int]) -> VideoTrack:
        width = _to_int(stream.get("width"))
        height = _to_int(stream.get("height"))
        return VideoTrack(
            index=_to_int(stream.get("index"), 0),
            codec=stream.get("codec_name"),
            codec_display=normalize_video_codec(stream.get("codec_name")),
            width=width,
            height=height,
            resolution_label=resolution_label(width, height),
            aspect_ratio=aspect_ratio(width, height, stream.get("display_aspect_ratio")),
            fps=safe_fraction(stream.get("avg_frame_rate")) or safe_fraction(stream.get("r_frame_rate")),
            bitrate=_to_int(stream.get("bit_rate"), container_bitrate),
            dynamic_range=detect_dynamic_range(stream),
            is_default=bool((stream.get("disposition") or {}).get("default")),
        )

    def _parse_audio_track(self, stream: dict) -> AudioTrack:
        tags = stream.get("tags") or {}
        language_code, language_name = _extract_language(tags)
        title = tags.get("title") or tags.get("handler_name")
        codec_name = stream.get("codec_name")
        return AudioTrack(
            index=_to_int(stream.get("index"), 0),
            codec=codec_name,
            codec_display=normalize_codec_display(codec_name),
            branding=infer_audio_branding(
                codec_name,
                stream.get("codec_long_name"),
                stream.get("profile"),
                title,
            ),
            channels=_to_int(stream.get("channels")),
            channel_layout=stream.get("channel_layout"),
            channel_label=channel_label(_to_int(stream.get("channels")), stream.get("channel_layout")),
            sample_rate=_to_int(stream.get("sample_rate")),
            bitrate=_to_int(stream.get("bit_rate")),
            language_code=language_code,
            language_name=language_name,
            title=title,
            is_default=bool((stream.get("disposition") or {}).get("default")),
        )

    def _parse_subtitle_track(self, stream: dict) -> Optional[SubtitleTrack]:
        tags = stream.get("tags") or {}
        title = tags.get("title") or tags.get("handler_name")
        language_code, language_name = _extract_language(tags)
        if stream.get("codec_name") is None and title is None and language_code is None:
            return None

        disposition = stream.get("disposition") or {}
        extra_bits = []
        if disposition.get("forced"):
            extra_bits.append("forced")
        if disposition.get("hearing_impaired"):
            extra_bits.append("hearing impaired")
        if title:
            extra_bits.append(title)

        return SubtitleTrack(
            index=_to_int(stream.get("index"), 0),
            codec=stream.get("codec_name"),
            codec_display=normalize_codec_display(stream.get("codec_name")),
            language_code=language_code,
            language_name=language_name,
            title=title,
            extra_info=", ".join(extra_bits) if extra_bits else None,
            is_default=bool(disposition.get("default")),
        )


def _extract_language(tags: dict) -> tuple[Optional[str], Optional[str]]:
    language_value = tags.get("language") or tags.get("LANGUAGE")
    if language_value:
        return normalize_language(str(language_value))
    title = tags.get("title") or tags.get("handler_name")
    return normalize_language(str(title)) if title else (None, None)


def _to_int(value, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
