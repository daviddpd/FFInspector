from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ffinspector.nfo import parse_nfo


SAMPLE_NFO = """\
<episodedetails>
  <title>Foreign Show</title>
  <mpaa>TV-14</mpaa>
  <season>1</season>
  <episode>2</episode>
  <aired>2024-03-15</aired>
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
        <codec>eac3</codec>
        <language>eng</language>
        <channels>6</channels>
      </audio>
      <subtitle>
        <language>eng</language>
        <format>srt</format>
      </subtitle>
    </streamdetails>
  </fileinfo>
</episodedetails>
"""


class NfoTests(unittest.TestCase):
    def test_parses_episode_metadata_and_streamdetails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            nfo_path = Path(temp_dir) / "Foreign Show S01E02.nfo"
            nfo_path.write_text(SAMPLE_NFO, encoding="utf-8")
            parsed = parse_nfo(nfo_path)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.title, "Foreign Show")
        self.assertEqual(parsed.rating, "TV-14")
        self.assertEqual(parsed.season, 1)
        self.assertEqual(parsed.episode, 2)
        self.assertEqual(parsed.aired, "2024-03-15")
        self.assertEqual(parsed.fileinfo.video["width"], 1920)
        self.assertEqual(parsed.fileinfo.audio[0]["language"], "eng")
        self.assertEqual(parsed.fileinfo.subtitles[0]["codec"], "srt")


if __name__ == "__main__":
    unittest.main()
