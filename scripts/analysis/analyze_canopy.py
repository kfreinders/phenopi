import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from plantcv import plantcv as pcv  # type: ignore[import-not-found]


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


def load_and_rotate_image(image_path: Path, angle: float) -> np.ndarray:
    img, _, _ = pcv.readimage(filename=str(image_path))  # type: ignore[misc]

    if angle != 0:
        img = pcv.transform.rotate(img, angle, crop=True)

    return cast(np.ndarray, img)


def segment_plants(img: np.ndarray, cfg: AnalysisConfig) -> np.ndarray:
    a_channel = pcv.rgb2gray_lab(rgb_img=img, channel="a")
    mask = pcv.threshold.binary(
        gray_img=a_channel,
        threshold=cfg.threshold,
        object_type="dark",
    )
    mask = pcv.fill(bin_img=mask, size=cfg.fill_size)
    return mask


def crop_to_mask(
    img: np.ndarray,
    mask: np.ndarray,
    margin_x: int,
    margin_y: int,
) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(mask > 0)

    if len(xs) == 0 or len(ys) == 0:
        raise ValueError(
            "Segmentation mask is empty. Check threshold settings."
        )

    x_min = xs.min()
    x_max = xs.max()
    y_min = ys.min()
    y_max = ys.max()

    x0 = max(0, x_min - margin_x)
    x1 = min(img.shape[1], x_max + margin_x)

    y0 = max(0, y_min - margin_y)
    y1 = min(img.shape[0], y_max + margin_y)

    width = x1 - x0
    height = y1 - y0

    img_crop = cast(
        np.ndarray, pcv.crop(img=img, x=x0, y=y0, h=height, w=width)
    )
    mask_crop = cast(
        np.ndarray, pcv.crop(img=mask, x=x0, y=y0, h=height, w=width)
    )

    return img_crop, mask_crop


def make_labeled_mask(
    img: np.ndarray,
    mask: np.ndarray,
    cfg: AnalysisConfig,
) -> tuple[np.ndarray, int]:
    rois = pcv.roi.auto_grid(
        img=img,
        mask=mask,
        nrows=cfg.roi_rows,
        ncols=cfg.roi_cols,
    )

    labeled_mask, num_plants = pcv.create_labels(
        mask=mask,
        rois=rois,
        roi_type="partial",
    )

    return labeled_mask, num_plants


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


def analyze_image(
    image_path: Path, output_dir: Path, cfg: AnalysisConfig
) -> pd.DataFrame:
    configure_plantcv(cfg, output_dir)
    pcv.outputs.clear()

    img = load_and_rotate_image(image_path, cfg.rotate_angle)
    mask = segment_plants(img, cfg)
    img_crop, mask_crop = crop_to_mask(img, mask, cfg.margin_x, cfg.margin_y)
    labeled_mask, num_plants = make_labeled_mask(img_crop, mask_crop, cfg)

    analyze_shape(img_crop, labeled_mask, num_plants)
    df = observations_to_dataframe()
    df = add_metric_units(df, cfg)

    stem = image_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{stem}_traits.csv"
    df.to_csv(csv_path, index=False)

    return df


def analyze_images(
    image_paths: list[Path], output_dir: Path, cfg: AnalysisConfig
) -> pd.DataFrame:
    all_results: list[pd.DataFrame] = []

    for image_path in image_paths:
        df = analyze_image(image_path, output_dir, cfg)
        df.insert(0, "image", image_path.name)
        all_results.append(df)

    if not all_results:
        raise ValueError("No images were provided for analysis.")

    combined = pd.concat(all_results, ignore_index=True)
    combined_path = output_dir / "combined_traits.csv"
    combined.to_csv(combined_path, index=False)

    return combined


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Arabidopsis canopy area from top-view images."
    )

    parser.add_argument(
        "images",
        nargs="+",
        type=Path,
        help="Input image path(s).",
    )

    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("results"),
        help="Output directory.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed debug logging.",
    )

    parser.add_argument("--rotate-angle", type=float, default=1.0)
    parser.add_argument("--threshold", type=int, default=100)
    parser.add_argument("--fill-size", type=int, default=200)
    parser.add_argument("--roi-rows", type=int, default=5)
    parser.add_argument("--roi-cols", type=int, default=9)
    parser.add_argument("--pot-diameter-cm", type=float, default=5.0)
    parser.add_argument("--pot-diameter-px", type=float, default=250.0)
    parser.add_argument("--debug", default=None)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = AnalysisConfig(
        rotate_angle=args.rotate_angle,
        threshold=args.threshold,
        fill_size=args.fill_size,
        roi_rows=args.roi_rows,
        roi_cols=args.roi_cols,
        pot_diameter_cm=args.pot_diameter_cm,
        pot_diameter_px=args.pot_diameter_px,
        debug=args.debug,
    )
    args.outdir.mkdir(parents=True, exist_ok=True)

    config_path = args.outdir / "analysis_config.json"

    with config_path.open("w") as f:
        json.dump(cfg.__dict__, f, indent=2)

    analyze_images(args.images, args.outdir, cfg)


if __name__ == "__main__":
    main()
