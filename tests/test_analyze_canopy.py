from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

# Keep orchestration tests independent of the optional PlantCV runtime.
plantcv_package = ModuleType("plantcv")
plantcv_package.plantcv = SimpleNamespace(
    outputs=SimpleNamespace(clear=lambda: None, observations={}),
    visualize=SimpleNamespace(colorspaces=lambda **_: None),
    params=SimpleNamespace(),
)
sys.modules.setdefault("plantcv", plantcv_package)

from scripts.analysis import analyze_canopy
from scripts.analysis.config import AnalysisConfig


def test_analyze_image_returns_identified_atomic_outputs(tmp_path, monkeypatch):
    image_path = tmp_path / "capture.jpg"
    image_path.touch()
    output_dir = tmp_path / "analysis"
    traits = pd.DataFrame([{"plant": "plant_1", "area": 42}])

    monkeypatch.setattr(analyze_canopy, "configure_plantcv", lambda *_: None)
    monkeypatch.setattr(analyze_canopy.pcv.outputs, "clear", lambda: None)
    monkeypatch.setattr(
        analyze_canopy, "load_and_rotate_image", lambda *_: np.zeros((2, 2, 3))
    )
    monkeypatch.setattr(
        analyze_canopy.pcv.visualize, "colorspaces", lambda **_: None
    )
    monkeypatch.setattr(
        analyze_canopy, "segment_plants", lambda *_: np.zeros((2, 2))
    )
    monkeypatch.setattr(
        analyze_canopy, "remove_square_components", lambda mask: mask
    )
    monkeypatch.setattr(
        analyze_canopy,
        "resolve_analysis_frame",
        lambda image, mask, *_: (image, mask),
    )
    monkeypatch.setattr(
        analyze_canopy,
        "make_labeled_mask",
        lambda *_: (np.zeros((2, 2)), 1, []),
    )

    def write_overlay(_image, _cells, path):
        Path(path).write_bytes(b"overlay")

    monkeypatch.setattr(
        analyze_canopy, "save_roi_circle_overlay", write_overlay
    )
    monkeypatch.setattr(analyze_canopy, "analyze_shape", lambda *_: None)
    monkeypatch.setattr(
        analyze_canopy, "observations_to_dataframe", lambda: traits
    )
    monkeypatch.setattr(
        analyze_canopy, "add_metric_units", lambda frame, _cfg: frame
    )

    config = AnalysisConfig()
    result = analyze_canopy.analyze_image(image_path, output_dir, config)

    assert result.image_path == image_path
    assert result.traits_path == output_dir / "capture_traits.csv"
    assert result.overlay_path == output_dir / "capture_roi_overlay.png"
    assert result.config_fingerprint == config.fingerprint
    pd.testing.assert_frame_equal(result.traits, traits)
    assert result.overlay_path.read_bytes() == b"overlay"
    assert not list(output_dir.glob(".*"))


def test_analyze_image_rejects_missing_input(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        analyze_canopy.analyze_image(
            tmp_path / "missing.jpg",
            tmp_path / "analysis",
            AnalysisConfig(),
        )
