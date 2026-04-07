# FF Inspector

`ffinspect` is a Python CLI for auditing video files with `ffprobe`, reading sidecar `.nfo` metadata, and flagging things like missing languages or stale NFO stream details.

## What it does

- Scans a file or directory for common video container formats.
- Uses `ffprobe` as the source of truth for video, audio, and subtitle streams.
- Reads same-name `.nfo` files and surfaces title, rating, season/episode, and air date metadata.
- Flags `.nfo` stream details that drift from the actual media, with tolerance for rounded durations and aspect ratios.
- Audits required audio and subtitle languages, so checks like “missing English dub/subtitles” stay generic.
- Keeps the reporting path modular so additional output formats can be added later.

## Usage

```bash
pip install -r requirements.txt
python3 -m ffinspector /path/to/media
python3 -m ffinspector /path/to/show --require-audio-language eng --require-subtitle-language eng
python3 -m ffinspector /path/to/show --config ffinspector.example.yaml
python3 -m ffinspector /path/to/show --format terse
python3 -m ffinspector /path/to/show --format brief
python3 -m ffinspector /path/to/show --format detail
python3 -m ffinspector /path/to/show --format table
python3 -m ffinspector /path/to/show --format json
python3 -m ffinspector arr-date-sync radarr /path/to/radarr.db
python3 -m ffinspector arr-date-sync sonarr /path/to/sonarr.db --mode oldest-media
python3 -m ffinspector arr-date-sync radarr /path/to/radarr.db --mode oldest-any --apply
python3 -m ffinspector arr-date-sync radarr /path/to/radarr.db --map-root /z/media=/Volumes/media
```

## Report Formats

- `terse` is the default terminal view and aims for a 3-4 line per-file summary.
- `brief` keeps the same sections but compresses each block into a single monospace-friendly line.
- `detail` is the original expanded block view for full per-track details.
- `table` renders each file as a compact Rich table row with separate columns for video, track, requirement, and issue fields.
- `json` emits structured machine-readable output.
- `brief` and `terse` cap audio/subtitle previews to two key items, then append an `X more...` tail when extra tracks exist.
- Displayed media paths are rendered relative to the target path you inspect.

## Configuration

The CLI accepts YAML config via `--config`. If `PyYAML` is installed it will use full YAML parsing. Without it, the bundled fallback parser supports the simple nested mapping/list structure shown below.

```yaml
ffprobe_path: ffprobe

scan:
  recursive: true
  extensions:
    - .mkv
    - .mp4

report:
  format: terse
  color: true
  sections:
    - meta
    - video
    - audio
    - subtitles

requirements:
  audio_languages:
    - eng
  subtitle_languages:
    - eng

comparison:
  duration_tolerance_seconds: 60
  aspect_ratio_tolerance: 0.03
```

## Notes

- `ffprobe` must be installed and available on `PATH`, or configured explicitly with `ffprobe_path`.
- Terminal output is rendered with [Rich](https://github.com/Textualize/rich).
- In environments where `ffprobe` is missing, the tool still reports the file and emits a probe error instead of crashing.
- The repo includes a stdlib `unittest` suite that mocks `ffprobe`, so the logic can be verified without FFmpeg on the machine.
- `arr-date-sync` is dry-run by default and updates `Movies.Added` for Radarr or `Series.Added` for Sonarr only when `--apply` is passed.
- The date source precedence for `arr-date-sync` is always `birth -> modified -> access`.
- `first-media` uses the movie file for Radarr and prefers `S01E01` for Sonarr when present, otherwise it falls back to the numerically first episode file on disk.
- `oldest-media` scans only video files using the configured media extensions, while `oldest-any` scans every file type in the movie or series folder tree.
- `--map-root SOURCE=TARGET` rewrites database path prefixes before probing the filesystem, which is useful when testing copied Radarr or Sonarr databases on a different machine or mount point.
