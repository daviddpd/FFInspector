from __future__ import annotations

from pathlib import Path

from .config import ScanConfig


def discover_media_paths(target: Path, scan_config: ScanConfig) -> list[Path]:
    if not target.exists():
        raise FileNotFoundError(f"Target does not exist: {target}")
    if target.is_file():
        return [target]

    results: list[Path] = []
    extensions = {extension.lower() for extension in scan_config.extensions}
    iterator = target.rglob("*") if scan_config.recursive else target.glob("*")
    for candidate in iterator:
        if not candidate.is_file():
            continue
        if not scan_config.follow_symlinks and candidate.is_symlink():
            continue
        if candidate.suffix.lower() in extensions:
            results.append(candidate)
    return sorted(results)
