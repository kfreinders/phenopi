import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import cast
import logging

import cv2
import numpy as np
import pandas as pd
from plantcv import plantcv as pcv  # type: ignore[import-not-found]


def setup_logging(verbose: bool = False) -> None:
    root_level = logging.INFO
    script_level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=root_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger(__name__).setLevel(script_level)


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


def remove_square_components(
    mask: np.ndarray,
    min_area: int = 200,
    max_area: int = 20_000,
    min_rectangularity: float = 0.75,
    min_aspect_ratio: float = 0.75,
    max_aspect_ratio: float = 1.35,
) -> np.ndarray:
    """
    Remove square/rectangular connected components from a binary mask.

    Intended to remove ColorChecker patches before computing crop bounds.
    Plants should usually survive because they are less rectangular.
    """
    binary = (mask > 0).astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary,
        connectivity=8,
    )

    cleaned = binary.copy()

    for label_id in range(1, num_labels):
        w = stats[label_id, cv2.CC_STAT_WIDTH]
        h = stats[label_id, cv2.CC_STAT_HEIGHT]
        area = stats[label_id, cv2.CC_STAT_AREA]

        if area < min_area or area > max_area:
            continue

        aspect_ratio = w / h if h > 0 else 0
        bbox_area = w * h
        rectangularity = area / bbox_area if bbox_area > 0 else 0

        looks_square = (
            min_aspect_ratio <= aspect_ratio <= max_aspect_ratio
            and rectangularity >= min_rectangularity
        )

        if looks_square:
            cleaned[labels == label_id] = 0

    return (cleaned * 255).astype(mask.dtype)


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
    logger = logging.getLogger(__name__)

    logger.info("Starting analysis: %s", image_path)
    configure_plantcv(cfg, output_dir)

    logger.debug("Clearing previous PlantCV outputs")
    pcv.outputs.clear()

    logger.info(
        f"Reading "
        f"{'and rotating ' if cfg.rotate_angle != 0.0 else ''}"
        f"image: {image_path}"
    )
    img = load_and_rotate_image(image_path, cfg.rotate_angle)

    logger.info("Segmenting plants")
    mask = segment_plants(img, cfg)

    logger.info("Removing square-like components before cropping")
    crop_mask = remove_square_components(mask)

    logger.info("Cropping image to detected plant mask")
    img_crop, mask_crop = crop_to_mask(
        img, crop_mask, cfg.margin_x, cfg.margin_y
    )

    logger.info(
        f"Creating ROI grid: {cfg.roi_rows} rows x {cfg.roi_cols} cols"
    )
    labeled_mask, num_plants = make_labeled_mask(img_crop, mask_crop, cfg)
    logger.info("Detected %d plant labels", num_plants)

    logger.info("Measuring plant shape traits")
    analyze_shape(img_crop, labeled_mask, num_plants)
    df = observations_to_dataframe()
    df = add_metric_units(df, cfg)

    stem = image_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{stem}_traits.csv"
    logger.info("Writing traits CSV: %s", csv_path)
    df.to_csv(csv_path, index=False)

    logger.info("Finished analysis: %s", image_path)

    return df


def analyze_images(
    image_paths: list[Path], output_dir: Path, cfg: AnalysisConfig
) -> pd.DataFrame:
    logger = logging.getLogger(__name__)
    all_results: list[pd.DataFrame] = []

    logger.info("Starting batch analysis for %d image(s)", len(image_paths))

    for i, image_path in enumerate(image_paths):
        logger.info(f"Processing image {i}/{len(image_paths)}: {image_path}")
        df = analyze_image(image_path, output_dir, cfg)
        df.insert(0, "image", image_path.name)
        all_results.append(df)

    if not all_results:
        raise ValueError("No images were provided for analysis.")

    combined = pd.concat(all_results, ignore_index=True)
    combined_path = output_dir / "combined_traits.csv"
    logger.info("Writing combined results: %s", combined_path)
    combined.to_csv(combined_path, index=False)

    logger.info("Batch analysis complete")

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
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger(__name__)
    logger.info("Starting canopy analysis workflow")
    logger.info("Output directory: %s", args.outdir)

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
    logger.info("Writing analysis config: %s", config_path)

    with config_path.open("w") as f:
        json.dump(cfg.__dict__, f, indent=2)

    analyze_images(args.images, args.outdir, cfg)
    logger.info("Workflow finished successfully")


if __name__ == "__main__":
    main()
