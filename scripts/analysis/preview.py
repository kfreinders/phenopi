from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import AnalysisConfig


@dataclass(frozen=True)
class AnalysisPreview:
    original: np.ndarray
    channel: np.ndarray
    mask: np.ndarray
    overlay: np.ndarray


def generate_analysis_preview(
    image_bytes: bytes,
    config: AnalysisConfig,
    *,
    max_dimension: int = 960,
) -> AnalysisPreview:
    """Generate display-sized segmentation stages without measuring traits."""
    if not image_bytes:
        raise ValueError("The calibration image is empty.")
    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("The calibration image could not be decoded.")

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rotated = _rotate_image(rgb, config.rotate_angle)
    lab = cv2.cvtColor(rotated, cv2.COLOR_RGB2LAB)
    channel_index = {"l": 0, "a": 1, "b": 2}[config.sepchannel]
    channel = lab[:, :, channel_index]
    mask = np.where(channel <= config.threshold, 255, 0).astype(np.uint8)
    mask = _remove_small_components(mask, config.fill_size)

    overlay = rotated.copy()
    selected = mask > 0
    green = np.array([67, 190, 113], dtype=np.float32)
    overlay[selected] = (
        overlay[selected].astype(np.float32) * 0.45 + green * 0.55
    ).astype(np.uint8)

    return AnalysisPreview(
        original=_fit_for_display(rotated, max_dimension),
        channel=_fit_for_display(channel, max_dimension),
        mask=_fit_for_display(
            mask, max_dimension, interpolation=cv2.INTER_NEAREST
        ),
        overlay=_fit_for_display(overlay, max_dimension),
    )


def encode_png(image: np.ndarray) -> bytes:
    """Encode an RGB or grayscale preview as PNG."""
    source = (
        cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if image.ndim == 3
        else image
    )
    success, encoded = cv2.imencode(".png", source)
    if not success:
        raise ValueError("An analysis preview image could not be encoded.")
    return encoded.tobytes()


def _rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    if angle == 0:
        return image
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def _remove_small_components(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    if minimum_area <= 1:
        return mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )
    cleaned = np.zeros_like(mask)
    for label_id in range(1, count):
        if stats[label_id, cv2.CC_STAT_AREA] >= minimum_area:
            cleaned[labels == label_id] = 255
    return cleaned


def _fit_for_display(
    image: np.ndarray,
    max_dimension: int,
    *,
    interpolation: int = cv2.INTER_AREA,
) -> np.ndarray:
    if max_dimension <= 0:
        raise ValueError("Preview maximum dimension must be positive.")
    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(height, width))
    if scale == 1:
        return image
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=interpolation,
    )
