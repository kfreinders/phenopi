from dataclasses import dataclass
from pathlib import Path

from plantcv import plantcv as pcv


@dataclass
class AnalysisConfig:
    rotate_angle: float = 1.0
    threshold: int = 100
    fill_size: int = 200
    margin_x: int = 200
    margin_y: int = 200
    roi_rows: int = 5
    roi_cols: int = 9
    pot_diameter_cm: float = 5.0
    pot_diameter_px: float = 250.0
    debug: str | None = None
    dpi: int = 300


def configure_plantcv(cfg: AnalysisConfig, output_dir: Path) -> None:
    pcv.params.debug = cfg.debug
    pcv.params.dpi = cfg.dpi
    pcv.params.text_size = 2
    pcv.params.text_thickness = 5
    cm_per_px = cfg.pot_diameter_cm / cfg.pot_diameter_px
    pcv.params.pixel_to_cm = cm_per_px  # type: ignore[attr-defined]

    if cfg.debug == "print":
        debug_dir = output_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        pcv.params.debug_outdir = str(debug_dir)
