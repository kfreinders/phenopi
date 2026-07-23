from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .config import AnalysisConfig


@dataclass(frozen=True)
class RoiCircle:
    row: int
    column: int
    center_x: float
    center_y: float
    radius: float


@dataclass(frozen=True)
class RoiDefinition:
    """A resolution-independent ROI grid calibrated from one run image."""

    schema_version: int
    rows: int
    columns: int
    source_width: int
    source_height: int
    config_fingerprint: str
    circles: tuple[RoiCircle, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported ROI definition version.")
        if self.rows <= 0 or self.columns <= 0:
            raise ValueError("ROI rows and columns must be positive.")
        if self.source_width <= 0 or self.source_height <= 0:
            raise ValueError("ROI source dimensions must be positive.")
        if len(self.circles) != self.rows * self.columns:
            raise ValueError("ROI definition does not contain the expected grid.")
        for circle in self.circles:
            if not (
                0 <= circle.row < self.rows
                and 0 <= circle.column < self.columns
                and 0 <= circle.center_x <= 1
                and 0 <= circle.center_y <= 1
                and 0 < circle.radius <= 1
                and all(
                    math.isfinite(value)
                    for value in (
                        circle.center_x,
                        circle.center_y,
                        circle.radius,
                    )
                )
            ):
                raise ValueError("ROI definition contains an invalid circle.")

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rows": self.rows,
            "columns": self.columns,
            "source_width": self.source_width,
            "source_height": self.source_height,
            "config_fingerprint": self.config_fingerprint,
            "circles": [asdict(circle) for circle in self.circles],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RoiDefinition:
        try:
            circles = tuple(
                RoiCircle(
                    row=int(circle["row"]),
                    column=int(circle["column"]),
                    center_x=float(circle["center_x"]),
                    center_y=float(circle["center_y"]),
                    radius=float(circle["radius"]),
                )
                for circle in value["circles"]
            )
            return cls(
                schema_version=int(value["schema_version"]),
                rows=int(value["rows"]),
                columns=int(value["columns"]),
                source_width=int(value["source_width"]),
                source_height=int(value["source_height"]),
                config_fingerprint=str(value["config_fingerprint"]),
                circles=circles,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("ROI definition is invalid.") from exc

    def save(self, path: Path) -> None:
        from scripts.scheduling.make_schedule import atomic_write_text

        atomic_write_text(
            path, json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        )

    @classmethod
    def load(cls, path: Path) -> RoiDefinition:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("ROI definition could not be read.") from exc
        if not isinstance(value, dict):
            raise ValueError("ROI definition must be a JSON object.")
        return cls.from_dict(value)

    def pixel_circles(
        self, image_shape: tuple[int, ...]
    ) -> list[tuple[int, int, int]]:
        height, width = image_shape[:2]
        radius_scale = min(width, height)
        return [
            (
                round(circle.center_x * width),
                round(circle.center_y * height),
                max(1, round(circle.radius * radius_scale)),
            )
            for circle in self.circles
        ]

    def labeled_mask(self, mask: np.ndarray) -> tuple[np.ndarray, int]:
        labels = np.zeros(mask.shape[:2], dtype=np.int32)
        for label_id, (center_x, center_y, radius) in enumerate(
            self.pixel_circles(mask.shape), start=1
        ):
            roi_mask = np.zeros(mask.shape[:2], dtype=np.uint8)
            cv2.circle(
                roi_mask, (center_x, center_y), radius, 255, thickness=-1
            )
            labels[(roi_mask > 0) & (mask > 0)] = label_id
        return labels, len(self.circles)

    def draw_overlay(self, image: np.ndarray) -> np.ndarray:
        overlay = image.copy()
        for label_id, (center_x, center_y, radius) in enumerate(
            self.pixel_circles(image.shape), start=1
        ):
            cv2.circle(
                overlay,
                (center_x, center_y),
                radius,
                (35, 196, 116),
                max(2, round(min(image.shape[:2]) / 500)),
            )
            cv2.putText(
                overlay,
                str(label_id),
                (center_x - 8, center_y + 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.4, min(image.shape[:2]) / 1600),
                (255, 255, 255),
                max(1, round(min(image.shape[:2]) / 700)),
                cv2.LINE_AA,
            )
        return overlay


def detect_roi_definition(
    image: np.ndarray,
    mask: np.ndarray,
    config: AnalysisConfig,
) -> RoiDefinition:
    """Use PlantCV once to locate the ROI grid in a calibration image."""
    from plantcv import plantcv as pcv  # type: ignore[import-not-found]

    objects = pcv.roi.auto_grid(
        mask=mask,
        nrows=config.roi_rows,
        ncols=config.roi_cols,
        img=image,
    )
    detected: list[tuple[float, float, float]] = []
    for contours in objects.contours:
        contour = np.asarray(contours[0])
        (center_x, center_y), radius = cv2.minEnclosingCircle(contour)
        detected.append((center_x, center_y, radius))
    expected = config.roi_rows * config.roi_cols
    if len(detected) != expected:
        raise ValueError(
            f"PlantCV detected {len(detected)} ROIs; expected {expected}."
        )

    ordered: list[tuple[float, float, float]] = []
    by_y = sorted(detected, key=lambda circle: circle[1])
    for row in range(config.roi_rows):
        start = row * config.roi_cols
        ordered.extend(
            sorted(
                by_y[start : start + config.roi_cols],
                key=lambda circle: circle[0],
            )
        )

    height, width = image.shape[:2]
    radius_scale = min(width, height)
    circles = tuple(
        RoiCircle(
            row=index // config.roi_cols,
            column=index % config.roi_cols,
            center_x=center_x / width,
            center_y=center_y / height,
            radius=radius / radius_scale,
        )
        for index, (center_x, center_y, radius) in enumerate(ordered)
    )
    return RoiDefinition(
        schema_version=1,
        rows=config.roi_rows,
        columns=config.roi_cols,
        source_width=width,
        source_height=height,
        config_fingerprint=config.fingerprint,
        circles=circles,
    )
