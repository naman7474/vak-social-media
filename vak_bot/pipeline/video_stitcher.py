"""Video utilities — concatenation, first-frame extraction, compression via ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import structlog

from vak_bot.config import get_settings

logger = structlog.get_logger(__name__)


def _ffmpeg() -> str:
    configured = get_settings().ffmpeg_path
    if configured:
        cfg_path = Path(configured)
        if cfg_path.exists():
            return str(cfg_path)
        if configured == "ffmpeg":
            resolved = shutil.which("ffmpeg")
            if resolved:
                return resolved

    resolved = shutil.which("ffmpeg")
    if resolved:
        return resolved

    raise FileNotFoundError(
        "ffmpeg binary not found. Set FFMPEG_PATH to a valid path or install ffmpeg."
    )


def concatenate_clips(clip_paths: list[str]) -> str:
    """Concatenate multiple video clips into one using ffmpeg concat demuxer."""

    if len(clip_paths) == 1:
        return clip_paths[0]

    # Build concat list file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for path in clip_paths:
            f.write(f"file '{path}'\n")
        list_path = f.name

    output_path = f"/tmp/veo_concat_{uuid.uuid4().hex[:8]}.mp4"

    cmd = [
        _ffmpeg(),
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("ffmpeg_concat_failed", stderr=result.stderr[:500])
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr[:200]}")
        logger.info("ffmpeg_concat_success", output=output_path, clip_count=len(clip_paths))
        return output_path
    finally:
        Path(list_path).unlink(missing_ok=True)


def extract_first_frame(video_path: str) -> bytes:
    """Extract the first frame of a video as JPEG bytes (for SSIM comparison)."""

    output_path = f"/tmp/frame0_{uuid.uuid4().hex[:8]}.jpg"

    cmd = [
        _ffmpeg(),
        "-y",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc
    if result.returncode != 0:
        stderr_preview = (result.stderr or "")[:500]
        stdout_preview = (result.stdout or "")[:500]
        logger.error(
            "ffmpeg_extract_frame_failed",
            returncode=result.returncode,
            stderr=stderr_preview,
            stdout=stdout_preview,
        )
        err_msg = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"ffmpeg frame extraction failed: {err_msg[:200]}")

    frame_bytes = Path(output_path).read_bytes()
    Path(output_path).unlink(missing_ok=True)
    return frame_bytes


def compress_video(video_path: str, max_size_mb: int = 950) -> str:
    """Compress a video to fit within Instagram's size limit (default ~950 MB safety margin)."""

    file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        return video_path  # Already small enough

    output_path = f"/tmp/veo_compressed_{uuid.uuid4().hex[:8]}.mp4"

    cmd = [
        _ffmpeg(),
        "-y",
        "-i", video_path,
        "-c:v", "libx264",
        "-crf", "28",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        logger.error("ffmpeg_missing_for_compress", configured_path=get_settings().ffmpeg_path)
        return video_path
    if result.returncode != 0:
        logger.error("ffmpeg_compress_failed", stderr=result.stderr[:500])
        return video_path  # Fallback: return original

    logger.info(
        "ffmpeg_compress_success",
        original_mb=round(file_size_mb, 1),
        compressed_mb=round(Path(output_path).stat().st_size / (1024 * 1024), 1),
    )
    return output_path
