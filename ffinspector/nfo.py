from __future__ import annotations

from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

from .models import NfoMetadata, NfoStreamDetails


def find_sidecar_nfo(media_path: Path) -> Optional[Path]:
    candidate = media_path.with_suffix(".nfo")
    if candidate.exists():
        return candidate
    return None


def load_nfo_for_media(media_path: Path) -> Optional[NfoMetadata]:
    nfo_path = find_sidecar_nfo(media_path)
    if nfo_path is None:
        return None
    return parse_nfo(nfo_path)


def parse_nfo(path: Path) -> Optional[NfoMetadata]:
    try:
        tree = ElementTree.parse(path)
    except ElementTree.ParseError:
        return None
    root = tree.getroot()
    media_type = root.tag.lower()
    fileinfo = _parse_fileinfo(root)
    return NfoMetadata(
        path=path,
        media_type=media_type,
        title=_pick_text(root, "title", "sorttitle", "showtitle"),
        rating=_pick_text(root, "mpaa", "certification"),
        season=_to_int(_text(root, "season")),
        episode=_to_int(_text(root, "episode")),
        aired=_pick_text(root, "aired", "premiered"),
        premiered=_pick_text(root, "premiered", "aired"),
        fileinfo=fileinfo,
    )


def _parse_fileinfo(root: ElementTree.Element) -> NfoStreamDetails:
    details = NfoStreamDetails()
    streamdetails = root.find("./fileinfo/streamdetails")
    if streamdetails is None:
        return details

    video = streamdetails.find("video")
    if video is not None:
        details.video = {
            "codec": _text(video, "codec"),
            "width": _to_int(_text(video, "width")),
            "height": _to_int(_text(video, "height")),
            "aspect": _text(video, "aspect"),
            "duration_seconds": _to_float(_pick_text(video, "durationinseconds", "duration")),
        }

    for audio in streamdetails.findall("audio"):
        details.audio.append(
            {
                "codec": _text(audio, "codec"),
                "language": _text(audio, "language"),
                "channels": _to_int(_text(audio, "channels")),
            }
        )

    for subtitle in streamdetails.findall("subtitle"):
        details.subtitles.append(
            {
                "language": _text(subtitle, "language"),
                "codec": _pick_text(subtitle, "codec", "format"),
            }
        )
    return details


def _pick_text(element: ElementTree.Element, *tags: str) -> Optional[str]:
    for tag in tags:
        value = _text(element, tag)
        if value:
            return value
    return None


def _text(element: ElementTree.Element, tag: str) -> Optional[str]:
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _to_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _to_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
