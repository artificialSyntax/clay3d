"""History > Start Recording: one frame per edit, exported as a time-lapse.

Frames are downscaled PNG bytes so a long session stays small in memory.
Export writes MP4 through ffmpeg when it is installed, otherwise an animated GIF.
"""

from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from io import BytesIO

import numpy as np
from PIL import Image

FRAME_SIDE = 720        # longest side of a recorded frame, px
FRAMES_PER_SECOND = 8   # one edit per frame
MAX_FRAMES = 3000


class HistoryRecorder:
    def __init__(self):
        self.recording = False
        # PNG encoding happens off the UI thread; export waits for it.
        self.frames: list[Future] = []
        self._encoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clay3d-record")

    def start(self) -> None:
        self.recording = True
        self.frames = []

    def stop(self) -> None:
        self.recording = False

    def capture(self, pixels: np.ndarray) -> None:
        if not self.recording or len(self.frames) >= MAX_FRAMES:
            return
        # Shrink first (cheap, and a copy the canvas can't change under us),
        # then flatten and compress the small frame in the background.
        small = _shrink(pixels)
        self.frames.append(self._encoder.submit(_encode_frame, small))

    def export(self, path: str, final_pixels: np.ndarray) -> str:
        """Write the time-lapse; returns the path actually written (suffix may change)."""
        self.capture_final(final_pixels)
        frames = [Image.open(BytesIO(frame.result())).convert("RGB") for frame in self.frames]
        if not frames:
            raise ValueError("nothing recorded")
        if path.lower().endswith(".mp4") and shutil.which("ffmpeg"):
            _write_mp4(path, frames)
            return path
        if path.lower().endswith(".mp4"):
            path = path[:-4] + ".gif"
        frames[0].save(
            path, save_all=True, append_images=frames[1:],
            duration=int(1000 / FRAMES_PER_SECOND), loop=0,
        )
        return path

    def capture_final(self, pixels: np.ndarray) -> None:
        was = self.recording
        self.recording = True
        self.capture(pixels)
        self.recording = was


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _shrink(pixels: np.ndarray) -> np.ndarray:
    import cv2

    height, width = pixels.shape[:2]
    k = min(1.0, FRAME_SIDE / max(width, height))
    if k >= 1.0:
        return pixels.copy()
    size = (max(1, round(width * k)), max(1, round(height * k)))
    return cv2.resize(pixels, size, interpolation=cv2.INTER_AREA)


def _encode_frame(pixels: np.ndarray) -> bytes:
    buffer = BytesIO()
    _flatten(pixels).save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


def _flatten(pixels: np.ndarray) -> Image.Image:
    alpha = pixels[:, :, 3:4].astype(np.float32) / 255.0
    rgb = pixels[:, :, :3].astype(np.float32) * alpha + 255.0 * (1.0 - alpha)
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def _write_mp4(path: str, frames: list[Image.Image]) -> None:
    # H.264 wants even dimensions; every frame is padded to the largest.
    width = max(f.width for f in frames) // 2 * 2 + 2
    height = max(f.height for f in frames) // 2 * 2 + 2
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
        "-r", str(FRAMES_PER_SECOND), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path,
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    for frame in frames:
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        canvas.paste(frame, ((width - frame.width) // 2, (height - frame.height) // 2))
        process.stdin.write(canvas.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise OSError("ffmpeg failed")
