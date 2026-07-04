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


@dataclass(frozen=True)
class PotCandidate:
    cx: float
    cy: float
    radius: float


@dataclass(frozen=True)
class AxisGrid:
    origin: float
    pitch: float
    score: float


@dataclass(frozen=True)
class PotGrid:
    x_axis: AxisGrid
    y_axis: AxisGrid
    matched_cells: int
    matched_candidates: tuple[PotCandidate, ...]
    score: float


def load_and_rotate_image(image_path: Path, angle: float) -> np.ndarray:
    img, _, _ = pcv.readimage(filename=str(image_path))  # type: ignore[misc]

    if angle != 0:
        img = pcv.transform.rotate(img, angle, crop=True)

    return cast(np.ndarray, img)


def segment_plants(img: np.ndarray, cfg: AnalysisConfig) -> np.ndarray:
    channel = pcv.rgb2gray_lab(rgb_img=img, channel=cfg.sepchannel)
    pcv.visualize.histogram(img=channel, bins=25)
    mask = pcv.threshold.binary(
        gray_img=channel,
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
            "Segmentation mask is empty, so crop bounds could not be "
            "determined. Check threshold settings or provide manual ROI "
            "bounds with --grid-x, --grid-y, --grid-width, and --grid-height."
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


def crop_to_bounds(
    img: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[int, int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    x, y, width, height = bounds
    img_h, img_w = img.shape[:2]

    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError(
            "ROI bounds must use non-negative x/y and positive width/height."
        )

    if x + width > img_w or y + height > img_h:
        raise ValueError(
            "ROI bounds must fit within the rotated image "
            f"({img_w}x{img_h}); got x={x}, y={y}, "
            f"width={width}, height={height}."
        )

    img_crop = cast(
        np.ndarray, pcv.crop(img=img, x=x, y=y, h=height, w=width)
    )
    mask_crop = cast(
        np.ndarray, pcv.crop(img=mask, x=x, y=y, h=height, w=width)
    )

    return img_crop, mask_crop


def _resize_for_detection(img: np.ndarray) -> tuple[np.ndarray, float]:
    max_dim = max(img.shape[:2])

    if max_dim <= 1600:
        return img, 1.0

    scale = 1600 / max_dim
    resized = cv2.resize(
        img,
        (int(round(img.shape[1] * scale)), int(round(img.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _deduplicate_pot_candidates(
    candidates: list[PotCandidate],
) -> list[PotCandidate]:
    deduped: list[PotCandidate] = []

    for candidate in sorted(candidates, key=lambda item: item.radius, reverse=True):
        if all(
            (candidate.cx - kept.cx) ** 2 + (candidate.cy - kept.cy) ** 2
            > (0.55 * max(candidate.radius, kept.radius)) ** 2
            for kept in deduped
        ):
            deduped.append(candidate)

    return deduped


def _detect_circle_pot_candidates(
    img: np.ndarray,
    scale: float,
) -> list[PotCandidate]:
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.medianBlur(gray, 5)
    min_dim = min(img.shape[:2])

    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(20, int(min_dim * 0.05)),
        param1=100,
        param2=35,
        minRadius=max(8, int(min_dim * 0.035)),
        maxRadius=max(12, int(min_dim * 0.10)),
    )

    if circles is None:
        return []

    return [
        PotCandidate(
            cx=float(circle[0]) / scale,
            cy=float(circle[1]) / scale,
            radius=float(circle[2]) / scale,
        )
        for circle in circles[0]
    ]


def _detect_square_pot_candidates(
    img: np.ndarray,
    scale: float,
) -> list[PotCandidate]:
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    min_dim = min(img.shape[:2])
    min_size = min_dim * 0.05
    max_size = min_dim * 0.25
    candidates: list[PotCandidate] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if w < min_size or h < min_size or w > max_size or h > max_size:
            continue

        aspect_ratio = w / h if h > 0 else 0.0

        if not 0.70 <= aspect_ratio <= 1.40:
            continue

        area = cv2.contourArea(contour)
        rectangularity = area / (w * h) if w * h else 0.0

        if rectangularity < 0.45:
            continue

        candidates.append(
            PotCandidate(
                cx=(x + w / 2) / scale,
                cy=(y + h / 2) / scale,
                radius=(max(w, h) / 2) / scale,
            )
        )

    return candidates


def detect_pot_candidates(img: np.ndarray) -> list[PotCandidate]:
    detection_img, scale = _resize_for_detection(img)
    candidates = [
        *_detect_circle_pot_candidates(detection_img, scale),
        *_detect_square_pot_candidates(detection_img, scale),
    ]
    return _deduplicate_pot_candidates(candidates)


def _axis_grid_candidates(
    values: list[float],
    n_positions: int,
    image_span: int,
    limit: int = 30,
) -> list[AxisGrid]:
    if n_positions <= 0 or not values:
        return []

    pitch_min = image_span / (n_positions + 4)
    pitch_max = image_span / max(n_positions - 0.75, 1)
    models: list[AxisGrid] = []

    for pitch in np.linspace(pitch_min, pitch_max, 55):
        origins: dict[int, list[float]] = {}

        for value in values:
            for idx in range(n_positions):
                origin = value - idx * pitch

                if -0.30 * pitch <= origin <= image_span - (
                    n_positions - 0.70
                ) * pitch:
                    origin_key = int(round(origin / 10) * 10)
                    origins.setdefault(origin_key, []).append(origin)

        for origin_values in origins.values():
            if len(origin_values) < 3:
                continue

            origin = float(np.median(origin_values))
            tolerance = 0.22 * pitch
            used_positions: set[int] = set()
            score = 0.0

            for value in values:
                idx = int(round((value - origin) / pitch))

                if not 0 <= idx < n_positions:
                    continue

                distance = abs(value - (origin + idx * pitch))

                if distance <= tolerance:
                    used_positions.add(idx)
                    score += 1.0 - distance / tolerance

            if len(used_positions) >= n_positions - 1:
                models.append(
                    AxisGrid(
                        origin=origin,
                        pitch=float(pitch),
                        score=score + len(used_positions) * 5,
                    )
                )

    models.sort(key=lambda model: model.score, reverse=True)
    filtered: list[AxisGrid] = []

    for model in models:
        if all(
            abs(model.origin - kept.origin) > 30
            or abs(model.pitch - kept.pitch) > 25
            for kept in filtered
        ):
            filtered.append(model)

        if len(filtered) >= limit:
            break

    return filtered


def _fit_pot_grid(
    candidates: list[PotCandidate],
    nrows: int,
    ncols: int,
    image_shape: tuple[int, ...],
) -> PotGrid | None:
    if len(candidates) < max(nrows, ncols):
        return None

    img_h, img_w = image_shape[:2]
    x_axes = _axis_grid_candidates(
        [candidate.cx for candidate in candidates],
        ncols,
        img_w,
    )
    y_axes = _axis_grid_candidates(
        [candidate.cy for candidate in candidates],
        nrows,
        img_h,
    )

    best_grid: PotGrid | None = None

    for x_axis in x_axes:
        for y_axis in y_axes:
            tolerance_x = 0.24 * x_axis.pitch
            tolerance_y = 0.24 * y_axis.pitch
            expected_radius = 0.45 * min(x_axis.pitch, y_axis.pitch)
            min_radius = 0.22 * min(x_axis.pitch, y_axis.pitch)
            max_radius = 0.70 * min(x_axis.pitch, y_axis.pitch)
            matched_cells: set[tuple[int, int]] = set()
            matched_candidates: list[PotCandidate] = []
            score = 0.0

            for candidate in candidates:
                if not min_radius <= candidate.radius <= max_radius:
                    continue

                col = int(round((candidate.cx - x_axis.origin) / x_axis.pitch))
                row = int(round((candidate.cy - y_axis.origin) / y_axis.pitch))

                if not (0 <= row < nrows and 0 <= col < ncols):
                    continue

                expected_x = x_axis.origin + col * x_axis.pitch
                expected_y = y_axis.origin + row * y_axis.pitch
                dx = abs(candidate.cx - expected_x)
                dy = abs(candidate.cy - expected_y)

                if dx <= tolerance_x and dy <= tolerance_y:
                    matched_cells.add((row, col))
                    radius_error = abs(candidate.radius - expected_radius)
                    radius_score = max(0.0, 1.0 - radius_error / expected_radius)
                    position_score = 1.0 - (
                        (dx / tolerance_x) + (dy / tolerance_y)
                    ) / 2
                    matched_candidates.append(candidate)
                    score += position_score + radius_score

            total_score = len(matched_cells) * 10 + score

            if best_grid is None or total_score > best_grid.score:
                best_grid = PotGrid(
                    x_axis=x_axis,
                    y_axis=y_axis,
                    matched_cells=len(matched_cells),
                    matched_candidates=tuple(matched_candidates),
                    score=total_score,
                )

    min_required_cells = max(nrows * ncols // 2, nrows + ncols)

    if best_grid is None or best_grid.matched_cells < min_required_cells:
        return None

    return best_grid


def detect_pot_grid_bounds(
    img: np.ndarray,
    cfg: AnalysisConfig,
) -> tuple[int, int, int, int]:
    candidates = detect_pot_candidates(img)
    grid = _fit_pot_grid(candidates, cfg.roi_rows, cfg.roi_cols, img.shape)

    if grid is None:
        raise ValueError(
            "Pot-grid ROI bounds could not be determined. Check image "
            "quality, provide manual ROI bounds with --grid-x, --grid-y, "
            "--grid-width, and --grid-height, or use "
            "--frame-source plant-mask."
        )

    radius = float(np.median([item.radius for item in grid.matched_candidates]))
    grid_x0 = grid.x_axis.origin - radius
    grid_x1 = grid.x_axis.origin + (cfg.roi_cols - 1) * grid.x_axis.pitch + radius
    grid_y0 = grid.y_axis.origin - radius
    grid_y1 = grid.y_axis.origin + (cfg.roi_rows - 1) * grid.y_axis.pitch + radius

    candidate_x0 = min(item.cx - item.radius for item in grid.matched_candidates)
    candidate_x1 = max(item.cx + item.radius for item in grid.matched_candidates)
    candidate_y0 = min(item.cy - item.radius for item in grid.matched_candidates)
    candidate_y1 = max(item.cy + item.radius for item in grid.matched_candidates)

    # Use only matched pot-sized candidates for final bounds, but do not allow
    # one noisy candidate to expand beyond the regularized grid envelope.
    x0 = int(round(max(candidate_x0, grid_x0)))
    x1 = int(round(min(candidate_x1, grid_x1)))
    y0 = int(round(max(candidate_y0, grid_y0)))
    y1 = int(round(min(candidate_y1, grid_y1)))

    x0 = max(0, x0 - cfg.pot_frame_padding_x)
    y0 = max(0, y0 - cfg.pot_frame_padding_y)
    x1 = min(img.shape[1], x1 + cfg.pot_frame_padding_x)
    y1 = min(img.shape[0], y1 + cfg.pot_frame_padding_y)

    return x0, y0, x1 - x0, y1 - y0


def _manual_grid_bounds(cfg: AnalysisConfig) -> tuple[int, int, int, int] | None:
    bounds = (cfg.grid_x, cfg.grid_y, cfg.grid_width, cfg.grid_height)

    if all(value is None for value in bounds):
        return None

    if any(value is None for value in bounds):
        raise ValueError(
            "Manual ROI bounds require all of --grid-x, --grid-y, "
            "--grid-width, and --grid-height."
        )

    return cast(tuple[int, int, int, int], bounds)


def resolve_analysis_frame(
    img: np.ndarray,
    mask: np.ndarray,
    crop_mask: np.ndarray,
    cfg: AnalysisConfig,
) -> tuple[np.ndarray, np.ndarray]:
    manual_bounds = _manual_grid_bounds(cfg)

    if manual_bounds is None:
        if cfg.frame_source == "plant-mask":
            return crop_to_mask(img, crop_mask, cfg.margin_x, cfg.margin_y)

        if cfg.frame_source == "pot-grid":
            bounds = detect_pot_grid_bounds(img, cfg)
            return crop_to_bounds(img, mask, bounds)

        raise ValueError(
            "Frame source must be 'pot-grid' or 'plant-mask'; got "
            f"{cfg.frame_source!r}."
        )

    return crop_to_bounds(img, mask, manual_bounds)


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
