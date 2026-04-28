from pathlib import Path
from typing import cast

import cv2
import numpy as np
from plantcv import plantcv as pcv  # type: ignore[import-not-found]

from .config import AnalysisConfig


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
