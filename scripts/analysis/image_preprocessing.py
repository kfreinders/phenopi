from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from plantcv import plantcv as pcv  # type: ignore[import-not-found]
from scipy import ndimage as ndi

from .config import AnalysisConfig


@dataclass(frozen=True)
class GridCell:
    label_id: int
    row: int
    col: int
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def cx(self) -> int:
        return (self.x0 + self.x1) // 2

    @property
    def cy(self) -> int:
        return (self.y0 + self.y1) // 2

    @property
    def radius(self) -> int:
        return min(self.x1 - self.x0, self.y1 - self.y0) // 2


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
    mask: np.ndarray,
    cfg: AnalysisConfig,
) -> tuple[np.ndarray, int, list[GridCell]]:
    return make_manual_grid_labeled_mask(
        mask=mask,
        nrows=cfg.roi_rows,
        ncols=cfg.roi_cols,
        margin_x=cfg.grid_margin_x,
        margin_y=cfg.grid_margin_y,
        padding_x=cfg.grid_cell_padding_x,
        padding_y=cfg.grid_cell_padding_y,
        min_component_area=cfg.min_component_area,
    )


def make_manual_grid_labeled_mask(
    mask: np.ndarray,
    nrows: int,
    ncols: int,
    margin_x: int = 0,
    margin_y: int = 0,
    padding_x: int = 0,
    padding_y: int = 0,
    min_component_area: int = 50,
) -> tuple[np.ndarray, int, list[GridCell]]:
    h, w = mask.shape[:2]

    x_start = margin_x
    x_end = w - margin_x
    y_start = margin_y
    y_end = h - margin_y

    if x_start >= x_end or y_start >= y_end:
        raise ValueError(
            "Manual grid margins are too large for the cropped image."
        )

    grid_w = x_end - x_start
    grid_h = y_end - y_start

    labeled_out = np.zeros(mask.shape, dtype=np.int32)
    cells: list[GridCell] = []
    label_id = 1

    for row in range(nrows):
        for col in range(ncols):
            x0 = x_start + int(round(col * grid_w / ncols))
            x1 = x_start + int(round((col + 1) * grid_w / ncols))
            y0 = y_start + int(round(row * grid_h / nrows))
            y1 = y_start + int(round((row + 1) * grid_h / nrows))

            cell = GridCell(
                label_id=label_id,
                row=row,
                col=col,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
            )
            cells.append(cell)

            # Optional padding shrinks each grid cell slightly.
            x0p = min(max(x0 + padding_x, 0), w)
            x1p = min(max(x1 - padding_x, 0), w)
            y0p = min(max(y0 + padding_y, 0), h)
            y1p = min(max(y1 - padding_y, 0), h)

            if x0p >= x1p or y0p >= y1p:
                label_id += 1
                continue

            submask = mask[y0p:y1p, x0p:x1p] > 0
            components, n_components = ndi.label(submask)

            if n_components == 0:
                label_id += 1
                continue

            component_ids = np.arange(1, n_components + 1)
            sizes = ndi.sum(submask, components, index=component_ids)

            largest_idx = int(np.argmax(sizes))
            largest_label = int(component_ids[largest_idx])
            largest_area = float(sizes[largest_idx])

            if largest_area >= min_component_area:
                target = labeled_out[y0p:y1p, x0p:x1p]
                target[components == largest_label] = label_id

            label_id += 1

    return labeled_out, nrows * ncols, cells


def save_roi_circle_overlay(
    img: np.ndarray,
    cells: list[GridCell],
    output_path: Path,
) -> None:
    overlay = img.copy()

    for cell in cells:
        cv2.circle(
            overlay,
            (cell.cx, cell.cy),
            cell.radius,
            (0, 255, 255),
            3,
        )
        cv2.putText(
            overlay,
            str(cell.label_id),
            (cell.cx - 15, cell.cy + 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
