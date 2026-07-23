# from __future__ import annotations
#
# import argparse
# from datetime import datetime
# from pathlib import Path
# import time
#
# import numpy as np
# from PIL import Image
# from picamera2 import Picamera2
#
#
# def capture_image(
#     size: tuple[int, int] = (4608, 2592),
#     warmup_time: float = 10
# ) -> np.ndarray:
#     """
#     Capture a single image from the camera as a NumPy array.
#
#     Initializes the camera, applies a still configuration, and waits for a
#     warmup period to allow auto-exposure and white balance to stabilize. The
#     captured frame is returned as a contiguous array suitable for further
#     processing or saving with PIL.
#
#     Parameters
#     ----------
#     size : tuple[int, int]
#         Resolution of the captured image as (width, height).
#     warmup_time : float
#         Number of seconds to wait after starting the camera before capturing
#         the image, allowing camera settings to stabilize.
#
#     Returns
#     -------
#     np.ndarray
#         Image array in RGB-compatible format with shape (height, width, 3) and
#         dtype uint8.
#     """
#     picam2 = Picamera2(0)
#
#     config = picam2.create_still_configuration(
#         main={"size": size, "format": "BGR888"}
#     )
#     picam2.configure(config)
#
#     picam2.start()
#     time.sleep(warmup_time)
#
#     frame = picam2.capture_array()
#
#     picam2.stop()
#     picam2.close()
#
#     rgb = np.ascontiguousarray(frame)
#     return rgb
#
#
# def main() -> None:
#     parser = argparse.ArgumentParser(
#         description="Capture a single image from the camera."
#     )
#     parser.add_argument(
#         "--output-dir",
#         type=Path,
#         required=True,
#         help="Directory where the captured image will be saved.",
#     )
#     parser.add_argument(
#         "--warmup-time",
#         type=float,
#         default=10.0,
#         help=(
#             "Seconds to wait for camera auto-exposure and white balance "
#             "to settle."
#         ),
#     )
#     args = parser.parse_args()
#
#     output_dir: Path = args.output_dir
#
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     output_dir.mkdir(parents=True, exist_ok=True)
#     output_path = output_dir / f"capture_{timestamp}.jpg"
#
#     print(f"[capture] Starting capture at {timestamp}")
#     print(f"[capture] Output path: {output_path}")
#
#     try:
#         img = capture_image(warmup_time=args.warmup_time)
#         Image.fromarray(img, mode="RGB").save(output_path, quality=100)
#         print(f"[capture] Saved image to {output_path}")
#     except Exception as exc:
#         print(f"[capture] ERROR: {exc}")
#         raise

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def write_placeholder_capture(
    output_dir: Path,
    *,
    captured_at: datetime | None = None,
) -> Path:
    """Write an empty development capture using the production filename."""
    timestamp = (captured_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"capture_{timestamp}.jpg"
    output_path.write_bytes(b"")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write an empty placeholder image for local development."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the placeholder capture will be saved.",
    )
    args = parser.parse_args()

    output_path = write_placeholder_capture(args.output_dir)
    print(f"[capture] Wrote placeholder image to {output_path}")


if __name__ == "__main__":
    main()
