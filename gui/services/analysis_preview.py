from __future__ import annotations

import base64
import binascii

from scripts.analysis.config import AnalysisConfig
from scripts.analysis.preview import encode_png, generate_analysis_preview


MAX_CALIBRATION_IMAGE_BYTES = 8_500_000


def build_analysis_preview(image_data: str, config_data: dict) -> dict:
    image_bytes = _decode_image_data(image_data)
    config = AnalysisConfig.from_dict(config_data)
    preview = generate_analysis_preview(image_bytes, config)
    return {
        "config": config.to_dict(),
        "config_fingerprint": config.fingerprint,
        "stages": {
            "original": _png_data_url(encode_png(preview.original)),
            "channel": _png_data_url(encode_png(preview.channel)),
            "mask": _png_data_url(encode_png(preview.mask)),
            "overlay": _png_data_url(encode_png(preview.overlay)),
        },
    }


def _decode_image_data(value: str) -> bytes:
    prefix, separator, payload = value.partition(",")
    if not separator or not prefix.startswith("data:image/"):
        raise ValueError("Provide a valid image data URL.")
    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The calibration image is not valid base64 data.") from exc
    if not decoded:
        raise ValueError("The calibration image is empty.")
    if len(decoded) > MAX_CALIBRATION_IMAGE_BYTES:
        raise ValueError("The calibration image must be smaller than 8.5 MB.")
    return decoded


def _png_data_url(value: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(value).decode('ascii')}"
