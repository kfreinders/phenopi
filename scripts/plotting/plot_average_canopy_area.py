from pathlib import Path

import pandas as pd


def load_traits(
    input_csv: Path,
    input_dir: Path | None = None
) -> pd.DataFrame:
    """Load canopy trait data.

    Parameters
    ----------
    input_csv
        Path to a combined traits CSV.
    input_dir
        Optional directory containing ``capture_*_traits.csv`` files. When
        provided, this is used instead of ``input_csv``.

    Returns
    -------
    pandas.DataFrame
        Combined trait table with ``image``, ``plant``, and ``area_cm2``
        columns.
    """
    if input_dir is None:
        return pd.read_csv(input_csv)

    paths = sorted(input_dir.glob("capture_*_traits.csv"))
    if not paths:
        raise ValueError(f"No capture trait CSV files found in {input_dir}.")

    frames = []
    for path in paths:
        df = pd.read_csv(path)
        df.insert(0, "image", path.name.removesuffix("_traits.csv") + ".jpg")
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def add_time_bins(df: pd.DataFrame, time_window: str) -> pd.DataFrame:
    """Add capture timestamps and rounded time bins.

    Parameters
    ----------
    df
        Trait table containing an ``image`` column.
    time_window
        Pandas-compatible time rounding interval.

    Returns
    -------
    pandas.DataFrame
        Copy of ``df`` with ``timestamp`` and ``time_bin`` columns.
    """
    out = df.copy()

    timestamp_text = out["image"].str.extract(r"(\d{8}_\d{6})")[0]
    if timestamp_text.isna().any():
        bad = out.loc[timestamp_text.isna(), "image"].unique()[:5]
        raise ValueError(
            f"Could not parse timestamps from image names like {bad!r}."
        )

    out["timestamp"] = pd.to_datetime(timestamp_text, format="%Y%m%d_%H%M%S")
    out["time_bin"] = out["timestamp"].dt.round(time_window)

    return out


def build_plant_curves(df: pd.DataFrame, time_window: str) -> pd.DataFrame:
    """Collapse replicate observations into plant-level time series.

    Parameters
    ----------
    df
        Raw trait table with ``image``, ``plant``, and ``area_cm2`` columns.
    time_window
        Time bin used to collapse replicate images.

    Returns
    -------
    pandas.DataFrame
        Plant-level canopy-area time series.
    """
    required = {"image", "plant", "area_cm2"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Input is missing required columns: {sorted(missing)}"
        )

    binned = add_time_bins(df, time_window)

    return (
        binned.groupby(["plant", "time_bin"], observed=True)
        .agg(
            area_cm2=("area_cm2", "mean"),
            n_images=("image", "nunique"),
            n_rows=("area_cm2", "size"),
        )
        .reset_index()
        .sort_values(["plant", "time_bin"])
    )
