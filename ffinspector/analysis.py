from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .models import InspectionIssue, InspectionResult, MediaInfo, NfoMetadata, RequirementCheck
from .nfo import load_nfo_for_media
from .probe import FFProbeRunner
from .utils import canonicalize_text, normalize_language


def inspect_media_file(
    media_path: Path,
    probe_runner: FFProbeRunner,
    config: AppConfig,
    display_path: str | None = None,
    nfo_display_path: str | None = None,
) -> InspectionResult:
    media = probe_runner.inspect(media_path)
    nfo = load_nfo_for_media(media_path)
    issues: list[InspectionIssue] = []

    if media.probe_error:
        issues.append(InspectionIssue("probe_error", "error", media.probe_error))

    audio_check = _check_required_languages(
        config.requirements.audio_languages,
        [track.language_code or track.language_name for track in media.audio_tracks],
    )
    if audio_check.missing:
        issues.append(
            InspectionIssue(
                "missing_audio_languages",
                "warning",
                f"Missing audio languages: {', '.join(audio_check.missing)}",
            )
        )

    subtitle_check = _check_required_languages(
        config.requirements.subtitle_languages,
        [track.language_code or track.language_name for track in media.subtitle_tracks],
    )
    if subtitle_check.missing:
        issues.append(
            InspectionIssue(
                "missing_subtitle_languages",
                "warning",
                f"Missing subtitle languages: {', '.join(subtitle_check.missing)}",
            )
        )

    nfo_issue = _compare_nfo(nfo, media, config)
    if nfo_issue is not None:
        issues.append(nfo_issue)

    title = _display_title(media_path, nfo)
    return InspectionResult(
        path=media_path,
        display_path=display_path or media_path.name,
        display_title=title,
        media=media,
        nfo=nfo,
        nfo_display_path=nfo_display_path,
        audio_languages=audio_check,
        subtitle_languages=subtitle_check,
        issues=issues,
    )


def _display_title(media_path: Path, nfo: NfoMetadata | None) -> str:
    if nfo and nfo.title:
        if nfo.season is not None and nfo.episode is not None:
            return f"{nfo.title} S{nfo.season:02d}E{nfo.episode:02d}"
        return nfo.title
    return media_path.stem


def _check_required_languages(required: list[str], present_values: list[str | None]) -> RequirementCheck:
    required_names = [_normalize_language_label(value) for value in required]
    present_codes = []
    present_names = []
    for value in present_values:
        code, name = normalize_language(value)
        if code:
            present_codes.append(code)
        if name:
            present_names.append(name)

    missing = []
    seen = set()
    for value in required:
        code, name = normalize_language(value)
        canonical = code or (name.lower() if name else value.lower())
        if canonical in seen:
            continue
        seen.add(canonical)
        if code and code in present_codes:
            continue
        if name and name in present_names:
            continue
        missing.append(name or value)
    return RequirementCheck(
        required=required_names,
        present=sorted(set(name for name in present_names if name)),
        missing=missing,
    )


def _normalize_language_label(value: str) -> str:
    _, name = normalize_language(value)
    return name or value


def _compare_nfo(nfo: NfoMetadata | None, media: MediaInfo, config: AppConfig) -> InspectionIssue | None:
    if nfo is None:
        return None
    mismatches: list[str] = []
    video_details = nfo.fileinfo.video
    actual_video = media.video_tracks[0] if media.video_tracks else None
    if video_details and actual_video:
        expected_codec = canonicalize_text(video_details.get("codec"))
        actual_codec = canonicalize_text(actual_video.codec_display or actual_video.codec)
        if expected_codec and actual_codec and expected_codec != actual_codec:
            mismatches.append(
                f"video codec NFO={video_details.get('codec')} actual={actual_video.codec_display or actual_video.codec}"
            )

        expected_width = video_details.get("width")
        expected_height = video_details.get("height")
        if expected_width and actual_video.width and expected_width != actual_video.width:
            mismatches.append(f"width NFO={expected_width} actual={actual_video.width}")
        if expected_height and actual_video.height and expected_height != actual_video.height:
            mismatches.append(f"height NFO={expected_height} actual={actual_video.height}")

        expected_aspect = _aspect_to_float(video_details.get("aspect"))
        actual_aspect = _aspect_to_float(actual_video.aspect_ratio)
        if (
            expected_aspect is not None
            and actual_aspect is not None
            and abs(expected_aspect - actual_aspect) > config.comparison.aspect_ratio_tolerance
        ):
            mismatches.append(f"aspect NFO={video_details.get('aspect')} actual={actual_video.aspect_ratio}")

        expected_duration = video_details.get("duration_seconds")
        actual_duration = media.duration_seconds
        if (
            expected_duration is not None
            and actual_duration is not None
            and abs(expected_duration - actual_duration) > config.comparison.duration_tolerance_seconds
        ):
            mismatches.append(
                f"duration NFO={int(expected_duration)}s actual={int(round(actual_duration))}s"
            )

    if nfo.fileinfo.audio:
        expected_audio_languages = sorted(
            {
                code
                for code, _ in (normalize_language(track.get("language")) for track in nfo.fileinfo.audio)
                if code
            }
        )
        actual_audio_languages = sorted(
            {track.language_code for track in media.audio_tracks if track.language_code}
        )
        if expected_audio_languages and expected_audio_languages != actual_audio_languages:
            mismatches.append(
                f"audio languages NFO={', '.join(expected_audio_languages)} actual={', '.join(actual_audio_languages)}"
            )

    if nfo.fileinfo.subtitles:
        expected_subtitles = sorted(
            {
                code
                for code, _ in (normalize_language(track.get("language")) for track in nfo.fileinfo.subtitles)
                if code
            }
        )
        actual_subtitles = sorted(
            {track.language_code for track in media.subtitle_tracks if track.language_code}
        )
        if expected_subtitles and expected_subtitles != actual_subtitles:
            mismatches.append(
                f"subtitle languages NFO={', '.join(expected_subtitles)} actual={', '.join(actual_subtitles)}"
            )

    if not mismatches:
        return None
    return InspectionIssue(
        "nfo_out_of_sync",
        "warning",
        "NFO out of sync: " + "; ".join(mismatches),
    )


def _aspect_to_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        left, right = text.split(":", 1)
        try:
            denominator = float(right)
            if denominator == 0:
                return None
            return float(left) / denominator
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None
