from pathlib import Path

import numpy as np
import pandas as pd
from plantcv import plantcv as pcv  # type: ignore[import-not-found]

from .config import AnalysisConfig


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


def analyze_shape(
    img: np.ndarray,
    labeled_mask: np.ndarray,
    num_plants: int,
) -> None:
    pcv.analyze.size(
        img=img,
        labeled_mask=labeled_mask,
        n_labels=num_plants,
    )


def observations_to_dataframe() -> pd.DataFrame:
    rows = []

    for plant_name, plant_data in pcv.outputs.observations.items():
        row = {"plant": plant_name}

        for trait_name, trait_info in plant_data.items():
            if isinstance(trait_info, dict) and "value" in trait_info:
                row[trait_name] = trait_info["value"]

        rows.append(row)

    return pd.DataFrame(rows)


def add_metric_units(df: pd.DataFrame, cfg: AnalysisConfig) -> pd.DataFrame:
    df = df.copy()
    cm_per_px = cfg.pot_diameter_cm / cfg.pot_diameter_px

    length_traits = [
        "width",
        "height",
        "perimeter",
        "longest_path",
        "ellipse_major_axis",
        "ellipse_minor_axis",
    ]

    area_traits = [
        "area",
        "convex_hull_area",
    ]

    for trait in length_traits:
        if trait in df.columns:
            df[f"{trait}_cm"] = df[trait] * cm_per_px

    for trait in area_traits:
        if trait in df.columns:
            df[f"{trait}_cm2"] = df[trait] * (cm_per_px**2)

    return df
