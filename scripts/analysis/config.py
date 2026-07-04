from dataclasses import dataclass


@dataclass
class AnalysisConfig:
    rotate_angle: float = 1.0
    sepchannel: str = "a"
    threshold: int = 100
    fill_size: int = 200
    margin_x: int = 200
    margin_y: int = 200
    frame_source: str = "pot-grid"
    pot_frame_padding_x: int = 0
    pot_frame_padding_y: int = 0
    grid_x: int | None = None
    grid_y: int | None = None
    grid_width: int | None = None
    grid_height: int | None = None
    roi_rows: int = 5
    roi_cols: int = 9
    grid_margin_x: int = 0
    grid_margin_y: int = 0
    grid_cell_padding_x: int = 0
    grid_cell_padding_y: int = 0
    min_component_area: int = 50
    pot_diameter_cm: float = 5.0
    pot_diameter_px: float = 250.0
    debug: str | None = None
    dpi: int = 300
