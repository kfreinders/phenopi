import sys
from types import ModuleType, SimpleNamespace

import cv2
import numpy as np
import pytest

from scripts.analysis.config import AnalysisConfig
from scripts.analysis.roi import (
    RoiCircle,
    RoiDefinition,
    detect_roi_definition,
)


def definition(config: AnalysisConfig) -> RoiDefinition:
    return RoiDefinition(
        schema_version=1,
        rows=1,
        columns=2,
        source_width=200,
        source_height=100,
        config_fingerprint=config.fingerprint,
        circles=(
            RoiCircle(0, 0, 0.25, 0.5, 0.2),
            RoiCircle(0, 1, 0.75, 0.5, 0.2),
        ),
    )


def test_roi_definition_round_trips_and_scales_to_image(tmp_path):
    config = AnalysisConfig(roi_rows=1, roi_cols=2)
    roi = definition(config)
    path = tmp_path / "roi-definition.json"

    roi.save(path)
    restored = RoiDefinition.load(path)

    assert restored == roi
    assert restored.fingerprint == roi.fingerprint
    assert restored.pixel_circles((200, 400, 3)) == [
        (100, 100, 40),
        (300, 100, 40),
    ]


def test_saved_roi_creates_labels_without_redetecting_grid():
    config = AnalysisConfig(roi_rows=1, roi_cols=2)
    mask = np.full((100, 200), 255, dtype=np.uint8)

    labels, count = definition(config).labeled_mask(mask)

    assert count == 2
    assert labels[50, 50] == 1
    assert labels[50, 150] == 2
    assert labels[0, 0] == 0


def test_plantcv_grid_is_normalized_and_ordered(monkeypatch):
    config = AnalysisConfig(roi_rows=1, roi_cols=2)

    def circle(center):
        points = cv2.ellipse2Poly(center, (10, 10), 0, 0, 360, 30)
        return [points.reshape(-1, 1, 2)]

    objects = SimpleNamespace(contours=[circle((150, 50)), circle((50, 50))])
    package = ModuleType("plantcv")
    package.plantcv = SimpleNamespace(
        roi=SimpleNamespace(auto_grid=lambda **_: objects)
    )
    monkeypatch.setitem(sys.modules, "plantcv", package)

    roi = detect_roi_definition(
        np.zeros((100, 200, 3), dtype=np.uint8),
        np.zeros((100, 200), dtype=np.uint8),
        config,
    )

    assert roi.circles[0].center_x == pytest.approx(0.25)
    assert roi.circles[1].center_x == pytest.approx(0.75)


def test_roi_definition_rejects_incomplete_grid():
    config = AnalysisConfig(roi_rows=1, roi_cols=2)
    with pytest.raises(ValueError, match="expected grid"):
        RoiDefinition(
            schema_version=1,
            rows=1,
            columns=2,
            source_width=100,
            source_height=100,
            config_fingerprint=config.fingerprint,
            circles=(RoiCircle(0, 0, 0.5, 0.5, 0.2),),
        )
