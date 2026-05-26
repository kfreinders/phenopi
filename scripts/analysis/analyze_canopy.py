import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import logging

import pandas as pd
from plantcv import plantcv as pcv  # type: ignore[import-not-found]
from .config import AnalysisConfig
from .image_preprocessing import (
    load_and_rotate_image,
    segment_plants,
    remove_square_components,
    crop_to_mask,
    make_labeled_mask,
    save_roi_circle_overlay
)
from .measurements import (
    configure_plantcv,
    analyze_shape,
    observations_to_dataframe,
    add_metric_units
)


def setup_logging(verbose: bool = False) -> None:
    root_level = logging.INFO
    script_level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=root_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger(__name__).setLevel(script_level)


def _analyze_image_worker(
    image_path: Path,
    output_dir: Path,
    cfg: AnalysisConfig,
) -> pd.DataFrame:
    df = analyze_image(image_path, output_dir, cfg)
    df.insert(0, "image", image_path.name)
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

    labeled_mask, num_plants, grid_cells = make_labeled_mask(mask_crop, cfg)
    logger.info("Detected %d plant labels", num_plants)

    stem = image_path.stem

    logger.info("Saving ROI overlay")
    save_roi_circle_overlay(
        img_crop,
        grid_cells,
        output_dir / f"{stem}_roi_overlay.png",
    )

    logger.info("Measuring plant shape traits")
    analyze_shape(img_crop, labeled_mask, num_plants)
    df = observations_to_dataframe()
    df = add_metric_units(df, cfg)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{stem}_traits.csv"
    logger.info("Writing traits CSV: %s", csv_path)
    df.to_csv(csv_path, index=False)

    logger.info("Finished analysis: %s", image_path)

    return df


def analyze_images(
    image_paths: list[Path],
    output_dir: Path,
    cfg: AnalysisConfig,
    n_workers: int | None = None,
) -> pd.DataFrame:
    logger = logging.getLogger(__name__)
    all_results: list[pd.DataFrame] = []

    if not image_paths:
        raise ValueError("No images were provided for analysis.")

    logger.info(f"Starting batch analysis for {len(image_paths)} image(s)")
    logger.info(f"Using {n_workers} worker(s)")

    if n_workers and n_workers <= 1:
        for i, image_path in enumerate(image_paths, start=1):
            logger.info(
                f"Processing image {i}/{len(image_paths)}: {image_path}"
            )
            df = _analyze_image_worker(image_path, output_dir, cfg)
            all_results.append(df)

    else:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(
                    _analyze_image_worker,
                    image_path,
                    output_dir,
                    cfg,
                ): image_path
                for image_path in image_paths
            }

            for i, future in enumerate(as_completed(futures), start=1):
                image_path = futures[future]

                try:
                    df = future.result()
                except Exception:
                    logger.exception("Failed to analyze image: %s", image_path)
                    raise

                logger.info(
                    "Finished image %d/%d: %s", i, len(image_paths), image_path
                )
                all_results.append(df)

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
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel worker processes (default: cores - 1).",
    )

    parser.add_argument(
        "--sepchannel",
        choices=["l", "a", "b"],
        default="a",
        help=(
            "LAB channel to use: l=lightness, a=green-magenta, "
            "b=blue-yellow."
        ),
    )

    parser.add_argument("--rotate-angle", type=float, default=1.0)
    parser.add_argument("--threshold", type=int, default=100)
    parser.add_argument("--fill-size", type=int, default=200)
    parser.add_argument("--roi-rows", type=int, default=5)
    parser.add_argument("--roi-cols", type=int, default=9)
    parser.add_argument("--grid-margin-x", type=int, default=0)
    parser.add_argument("--grid-margin-y", type=int, default=0)
    parser.add_argument("--grid-cell-padding-x", type=int, default=0)
    parser.add_argument("--grid-cell-padding-y", type=int, default=0)
    parser.add_argument("--min-component-area", type=int, default=50)
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
        sepchannel=args.sepchannel,
        threshold=args.threshold,
        fill_size=args.fill_size,
        roi_rows=args.roi_rows,
        roi_cols=args.roi_cols,
        grid_margin_x=args.grid_margin_x,
        grid_margin_y=args.grid_margin_y,
        grid_cell_padding_x=args.grid_cell_padding_x,
        grid_cell_padding_y=args.grid_cell_padding_y,
        min_component_area=args.min_component_area,
        pot_diameter_cm=args.pot_diameter_cm,
        pot_diameter_px=args.pot_diameter_px,
        debug=args.debug,
    )
    args.outdir.mkdir(parents=True, exist_ok=True)

    config_path = args.outdir / "analysis_config.json"
    logger.info("Writing analysis config: %s", config_path)

    with config_path.open("w") as f:
        json.dump(cfg.__dict__, f, indent=2)

    cpu_count = os.cpu_count() or 1

    if (n_workers := args.workers) is None:
        n_workers = max(1, cpu_count - 1)

    logger.info(f"Using {n_workers} workers")

    analyze_images(args.images, args.outdir, cfg, n_workers)
    logger.info("Workflow finished successfully")


if __name__ == "__main__":
    main()
