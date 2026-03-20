from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ffinspector.analysis import inspect_media_file
from ffinspector.config import AppConfig
from ffinspector.models import AudioTrack, MediaInfo, SubtitleTrack, VideoTrack
from ffinspector.probe import FFProbeRunner


class StubProbeRunner(FFProbeRunner):
    def __init__(self, media_info: MediaInfo) -> None:
        super().__init__("ffprobe")
        self.media_info = media_info

    def inspect(self, media_path: Path) -> MediaInfo:
        self.media_info.path = media_path
        return self.media_info


class AnalysisTests(unittest.TestCase):
    def test_flags_missing_required_subtitles_and_nfo_drift(self) -> None:
        media_info = MediaInfo(
            path=Path("dummy.mkv"),
            duration_seconds=2640,
            video_tracks=[
                VideoTrack(
                    index=0,
                    codec="hevc",
                    codec_display="H.265",
                    width=1920,
                    height=1080,
                    resolution_label="1080p",
                    aspect_ratio="16:9",
                    fps=23.976,
                    bitrate=6_500_000,
                    dynamic_range="HDR10",
                )
            ],
            audio_tracks=[
                AudioTrack(index=1, language_code="eng", language_name="English"),
                AudioTrack(index=2, language_code="jpn", language_name="Japanese"),
            ],
            subtitle_tracks=[
                SubtitleTrack(index=3, language_code="jpn", language_name="Japanese", codec="subrip"),
            ],
        )
        config = AppConfig()
        config.requirements.audio_languages = ["eng"]
        config.requirements.subtitle_languages = ["eng"]

        with TemporaryDirectory() as temp_dir:
            media_path = Path(temp_dir) / "Episode.mkv"
            nfo_path = Path(temp_dir) / "Episode.nfo"
            media_path.write_text("", encoding="utf-8")
            nfo_path.write_text(
                """\
<episodedetails>
  <title>Episode</title>
  <season>1</season>
  <episode>1</episode>
  <fileinfo>
    <streamdetails>
      <video>
        <codec>h264</codec>
        <width>1920</width>
        <height>1080</height>
        <aspect>1.78</aspect>
        <durationinseconds>2630</durationinseconds>
      </video>
      <audio>
        <language>eng</language>
      </audio>
      <subtitle>
        <language>eng</language>
      </subtitle>
    </streamdetails>
  </fileinfo>
</episodedetails>
""",
                encoding="utf-8",
            )
            result = inspect_media_file(media_path, StubProbeRunner(media_info), config)

        messages = [issue.message for issue in result.issues]
        self.assertTrue(any("Missing subtitle languages" in message for message in messages))
        self.assertTrue(any("NFO out of sync" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
