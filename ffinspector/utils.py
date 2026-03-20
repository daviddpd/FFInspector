from __future__ import annotations

import math
from fractions import Fraction
from typing import Optional


_LANGUAGE_ALIASES = {
    "en": ("eng", "English"),
    "eng": ("eng", "English"),
    "english": ("eng", "English"),
    "english sdh": ("eng", "English"),
    "es": ("spa", "Spanish"),
    "spa": ("spa", "Spanish"),
    "spanish": ("spa", "Spanish"),
    "ja": ("jpn", "Japanese"),
    "jpn": ("jpn", "Japanese"),
    "japanese": ("jpn", "Japanese"),
    "fr": ("fra", "French"),
    "fra": ("fra", "French"),
    "fre": ("fra", "French"),
    "french": ("fra", "French"),
    "de": ("deu", "German"),
    "deu": ("deu", "German"),
    "ger": ("deu", "German"),
    "german": ("deu", "German"),
    "it": ("ita", "Italian"),
    "ita": ("ita", "Italian"),
    "italian": ("ita", "Italian"),
    "pt": ("por", "Portuguese"),
    "por": ("por", "Portuguese"),
    "portuguese": ("por", "Portuguese"),
    "pt-br": ("por", "Portuguese"),
    "ru": ("rus", "Russian"),
    "rus": ("rus", "Russian"),
    "russian": ("rus", "Russian"),
    "ko": ("kor", "Korean"),
    "kor": ("kor", "Korean"),
    "korean": ("kor", "Korean"),
    "zh": ("zho", "Chinese"),
    "chi": ("zho", "Chinese"),
    "zho": ("zho", "Chinese"),
    "chinese": ("zho", "Chinese"),
    "zh-cn": ("zho", "Chinese"),
    "zh-hans": ("zho", "Chinese"),
    "zh-tw": ("zho", "Chinese"),
    "zh-hant": ("zho", "Chinese"),
    "pl": ("pol", "Polish"),
    "pol": ("pol", "Polish"),
    "polish": ("pol", "Polish"),
    "nl": ("nld", "Dutch"),
    "dut": ("nld", "Dutch"),
    "nld": ("nld", "Dutch"),
    "dutch": ("nld", "Dutch"),
    "sv": ("swe", "Swedish"),
    "swe": ("swe", "Swedish"),
    "swedish": ("swe", "Swedish"),
    "no": ("nor", "Norwegian"),
    "nor": ("nor", "Norwegian"),
    "norwegian": ("nor", "Norwegian"),
    "da": ("dan", "Danish"),
    "dan": ("dan", "Danish"),
    "danish": ("dan", "Danish"),
    "fi": ("fin", "Finnish"),
    "fin": ("fin", "Finnish"),
    "finnish": ("fin", "Finnish"),
    "tr": ("tur", "Turkish"),
    "tur": ("tur", "Turkish"),
    "turkish": ("tur", "Turkish"),
    "ar": ("ara", "Arabic"),
    "ara": ("ara", "Arabic"),
    "arabic": ("ara", "Arabic"),
    "hi": ("hin", "Hindi"),
    "hin": ("hin", "Hindi"),
    "hindi": ("hin", "Hindi"),
    "th": ("tha", "Thai"),
    "tha": ("tha", "Thai"),
    "thai": ("tha", "Thai"),
    "vi": ("vie", "Vietnamese"),
    "vie": ("vie", "Vietnamese"),
    "vietnamese": ("vie", "Vietnamese"),
    "und": ("und", "Unknown"),
    "unknown": ("und", "Unknown"),
}

_VIDEO_CODEC_LABELS = {
    "av1": "AV1",
    "h264": "H.264",
    "avc1": "H.264",
    "hevc": "H.265",
    "h265": "H.265",
    "mpeg2video": "MPEG-2",
    "mpeg4": "MPEG-4",
    "vp8": "VP8",
    "vp9": "VP9",
    "vc1": "VC-1",
}

_GENERIC_CODEC_LABELS = {
    "aac": "AAC",
    "ac3": "AC-3",
    "alac": "ALAC",
    "ass": "ASS",
    "dca": "DTS",
    "dts": "DTS",
    "eac3": "E-AC-3",
    "flac": "FLAC",
    "mov_text": "MOV_TEXT",
    "opus": "Opus",
    "pgs": "PGS",
    "srt": "SRT",
    "subrip": "SRT",
    "truehd": "TrueHD",
}


def normalize_language(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    cleaned = value.strip()
    if not cleaned:
        return None, None
    lookup = cleaned.lower().replace("_", "-")
    lookup = lookup.split("(")[0].strip()
    if lookup in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[lookup]
    if "-" in lookup:
        base = lookup.split("-", 1)[0]
        if base in _LANGUAGE_ALIASES:
            return _LANGUAGE_ALIASES[base]
    if len(lookup) == 2:
        return lookup, cleaned.title()
    if len(lookup) == 3:
        return lookup, cleaned.title()
    return lookup, cleaned.title()


def format_duration_exact(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_duration_minutes(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    rounded = max(0, int(round(seconds / 60.0)))
    hours, minutes = divmod(rounded, 60)
    return f"{hours:02d}:{minutes:02d}"


def format_bitrate(bits_per_second: Optional[int]) -> str:
    if not bits_per_second:
        return "unknown"
    if bits_per_second >= 1_000_000_000:
        return f"{bits_per_second / 1_000_000_000:.2f} Gbps"
    if bits_per_second >= 1_000_000:
        return f"{bits_per_second / 1_000_000:.2f} Mbps"
    if bits_per_second >= 1_000:
        return f"{bits_per_second / 1_000:.0f} kbps"
    return f"{bits_per_second} bps"


def format_sample_rate(hz: Optional[int]) -> str:
    if not hz:
        return "unknown"
    return f"{hz / 1000:.1f} kHz"


def format_fps(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def resolution_label(width: Optional[int], height: Optional[int]) -> Optional[str]:
    if not width or not height:
        return None
    max_side = max(width, height)
    min_side = min(width, height)
    if max_side >= 3840 or min_side >= 2160:
        return "4K"
    if min_side >= 1440:
        return "1440p"
    if min_side >= 1080:
        return "1080p"
    if min_side >= 720:
        return "720p"
    if min_side >= 480:
        return "480p"
    return f"{min_side}p"


def safe_fraction(value: Optional[str]) -> Optional[float]:
    if not value or value in {"0/0", "0", "N/A"}:
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
        except ValueError:
            return None


def aspect_ratio(width: Optional[int], height: Optional[int], display_ratio: Optional[str] = None) -> Optional[str]:
    if display_ratio and display_ratio not in {"0:1", "N/A"}:
        return display_ratio
    if not width or not height:
        return None
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def normalize_video_codec(codec_name: Optional[str]) -> Optional[str]:
    if not codec_name:
        return None
    return _VIDEO_CODEC_LABELS.get(codec_name.lower(), codec_name.upper())


def normalize_codec_display(codec_name: Optional[str]) -> Optional[str]:
    if not codec_name:
        return None
    lower = codec_name.lower()
    return _GENERIC_CODEC_LABELS.get(lower, _VIDEO_CODEC_LABELS.get(lower, codec_name.upper()))


def infer_audio_branding(
    codec_name: Optional[str],
    codec_long_name: Optional[str] = None,
    profile: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[str]:
    if not codec_name:
        return None
    lower = codec_name.lower()
    haystack = " ".join(part for part in [codec_long_name, profile, title] if part).lower()
    if "atmos" in haystack:
        if lower == "truehd":
            return "Dolby Atmos (TrueHD)"
        return "Dolby Atmos"
    if lower == "eac3":
        return "Dolby Digital Plus"
    if lower == "ac3":
        return "Dolby Digital"
    if lower == "truehd":
        return "Dolby TrueHD"
    if lower in {"dts", "dca"}:
        if "master audio" in haystack:
            return "DTS-HD MA"
        if "hd" in haystack:
            return "DTS-HD"
        return "DTS"
    return normalize_codec_display(codec_name)


def channel_label(channels: Optional[int], layout: Optional[str] = None) -> Optional[str]:
    if layout:
        lowered = layout.lower()
        if lowered == "mono":
            return "1.0"
        if lowered == "stereo":
            return "2.0"
        if "5.1" in lowered:
            return "5.1"
        if "7.1" in lowered:
            return "7.1"
        if "2.1" in lowered:
            return "2.1"
    mapping = {
        1: "1.0",
        2: "2.0",
        3: "2.1",
        4: "4.0",
        5: "5.0",
        6: "5.1",
        7: "6.1",
        8: "7.1",
    }
    return mapping.get(channels, str(channels) if channels else None)


def detect_dynamic_range(stream: dict) -> Optional[str]:
    for side_data in stream.get("side_data_list") or []:
        label = str(side_data.get("side_data_type", "")).lower()
        if "dovi" in label or "dolby vision" in label:
            return "Dolby Vision"
    transfer = str(stream.get("color_transfer", "")).lower()
    profile = str(stream.get("profile", "")).lower()
    if "dolby vision" in profile:
        return "Dolby Vision"
    if transfer == "smpte2084":
        return "HDR10"
    if transfer == "arib-std-b67":
        return "HLG"
    if transfer:
        return "SDR"
    return "SDR"


def canonicalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    lowered = value.lower()
    return "".join(character for character in lowered if character.isalnum())
