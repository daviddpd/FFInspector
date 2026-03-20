from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class VideoTrack:
    index: int
    codec: Optional[str] = None
    codec_display: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    resolution_label: Optional[str] = None
    aspect_ratio: Optional[str] = None
    fps: Optional[float] = None
    bitrate: Optional[int] = None
    dynamic_range: Optional[str] = None
    is_default: bool = False


@dataclass
class AudioTrack:
    index: int
    codec: Optional[str] = None
    codec_display: Optional[str] = None
    branding: Optional[str] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None
    channel_label: Optional[str] = None
    sample_rate: Optional[int] = None
    bitrate: Optional[int] = None
    language_code: Optional[str] = None
    language_name: Optional[str] = None
    title: Optional[str] = None
    is_default: bool = False


@dataclass
class SubtitleTrack:
    index: int
    codec: Optional[str] = None
    codec_display: Optional[str] = None
    language_code: Optional[str] = None
    language_name: Optional[str] = None
    title: Optional[str] = None
    extra_info: Optional[str] = None
    is_default: bool = False


@dataclass
class MediaInfo:
    path: Path
    format_name: Optional[str] = None
    duration_seconds: Optional[float] = None
    container_bitrate: Optional[int] = None
    video_tracks: list[VideoTrack] = field(default_factory=list)
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)
    probe_error: Optional[str] = None


@dataclass
class NfoStreamDetails:
    video: dict[str, Any] = field(default_factory=dict)
    audio: list[dict[str, Any]] = field(default_factory=list)
    subtitles: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NfoMetadata:
    path: Path
    media_type: str
    title: Optional[str] = None
    rating: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    aired: Optional[str] = None
    premiered: Optional[str] = None
    fileinfo: NfoStreamDetails = field(default_factory=NfoStreamDetails)


@dataclass
class RequirementCheck:
    required: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class InspectionIssue:
    code: str
    severity: str
    message: str


@dataclass
class InspectionResult:
    path: Path
    display_path: str
    display_title: str
    media: MediaInfo
    nfo: Optional[NfoMetadata]
    nfo_display_path: Optional[str] = None
    audio_languages: RequirementCheck = field(default_factory=RequirementCheck)
    subtitle_languages: RequirementCheck = field(default_factory=RequirementCheck)
    issues: list[InspectionIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(issue.severity == "error" for issue in self.issues):
            return "error"
        if self.issues:
            return "warning"
        return "ok"
