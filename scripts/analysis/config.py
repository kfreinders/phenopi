from dataclasses import dataclass


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
