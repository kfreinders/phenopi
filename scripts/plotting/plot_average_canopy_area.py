from pathlib import Path

import numpy as np
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


def fit_local_absolute_growth(
    plant_df: pd.DataFrame,
    window_hours: float,
    min_points: int,
) -> pd.Series:
    """Estimate plant-level absolute growth rate using local linear fits.

    Parameters
    ----------
    plant_df
        Time series for a single plant.
    window_hours
        Width of the centered fitting window in hours.
    min_points
        Minimum number of points required in a local fit.

    Returns
    -------
    pandas.Series
        Absolute growth rate estimates in square centimeters per day, indexed
        like ``plant_df``.
    """
    sorted_df = plant_df.sort_values("time_bin")
    growth_values: list[float] = []

    half_window = pd.Timedelta(window_hours / 2, unit="h")

    for _, row in sorted_df.iterrows():
        center = row["time_bin"]
        in_window = (
            (sorted_df["time_bin"] >= center - half_window)
            & (sorted_df["time_bin"] <= center + half_window)
        )
        window_df = sorted_df.loc[in_window]

        if len(window_df) < min_points:
            growth_values.append(np.nan)
            continue

        elapsed_days = (
            window_df["time_bin"] - window_df["time_bin"].iloc[0]
        ).dt.total_seconds() / 86400

        if elapsed_days.nunique() < 2:
            growth_values.append(np.nan)
            continue

        slope = np.polyfit(
            elapsed_days,
            window_df["area_cm2"],
            1,
        )[0]
        growth_values.append(float(slope))

    growth = pd.Series(
        growth_values,
        index=sorted_df.index,
        dtype=float,
        name="plant_agr_cm2_per_day",
    )

    return growth.reindex(plant_df.index)


def summarize_by_time(plant_curves: pd.DataFrame) -> pd.DataFrame:
    """Summarize plant-level area and absolute growth rate by time bin.

    Parameters
    ----------
    plant_curves
        Plant-level canopy-area and absolute-growth-rate time series.

    Returns
    -------
    pandas.DataFrame
        Time-level summary with area and absolute-growth-rate quantiles.
    """
    return (
        plant_curves.groupby("time_bin", observed=True)
        .agg(
            n_plants=("plant", "nunique"),
            mean_area_cm2=("area_cm2", "mean"),
            median_area_cm2=("area_cm2", "median"),
            sd_area_cm2=("area_cm2", "std"),
            q25_area_cm2=("area_cm2", lambda x: x.quantile(0.25)),
            q75_area_cm2=("area_cm2", lambda x: x.quantile(0.75)),
            n_growth_plants=("plant_agr_cm2_per_day", "count"),
            mean_agr_cm2_per_day=("plant_agr_cm2_per_day", "mean"),
            median_agr_cm2_per_day=("plant_agr_cm2_per_day", "median"),
            q25_agr_cm2_per_day=(
                "plant_agr_cm2_per_day",
                lambda x: x.quantile(0.25),
            ),
            q75_agr_cm2_per_day=(
                "plant_agr_cm2_per_day",
                lambda x: x.quantile(0.75),
            ),
            q025_agr_cm2_per_day=(
                "plant_agr_cm2_per_day",
                lambda x: x.quantile(0.025),
            ),
            q975_agr_cm2_per_day=(
                "plant_agr_cm2_per_day",
                lambda x: x.quantile(0.975),
            ),
        )
        .reset_index()
        .sort_values("time_bin")
        .assign(
            sem_area_cm2=lambda x: x["sd_area_cm2"] / np.sqrt(x["n_plants"]),
        )
    )


def summarize_growth_periods(
    summary: pd.DataFrame,
    treatment_start: pd.Timestamp | None,
    treatment_end: pd.Timestamp | None,
) -> pd.DataFrame:
    """Summarize absolute growth rates over broad periods.

    Parameters
    ----------
    summary
        Time-level summary table.
    treatment_start
        Optional treatment start timestamp.
    treatment_end
        Optional treatment end timestamp.

    Returns
    -------
    pandas.DataFrame
        Period-level absolute-growth-rate summary.
    """
    if treatment_start is None or treatment_end is None:
        periods = [("all", pd.Series(True, index=summary.index))]
    else:
        periods = [
            ("pre", summary["time_bin"] < treatment_start),
            (
                "treatment",
                (summary["time_bin"] >= treatment_start)
                & (summary["time_bin"] <= treatment_end),
            ),
            ("recovery", summary["time_bin"] > treatment_end),
        ]

    rows = []

    for name, mask in periods:
        period = summary.loc[mask].dropna(subset=["mean_area_cm2"])

        if len(period) < 2:
            continue

        elapsed_days = (
            period["time_bin"] - period["time_bin"].iloc[0]
        ).dt.total_seconds() / 86400

        if elapsed_days.nunique() < 2:
            continue

        fitted_agr = np.polyfit(
            elapsed_days,
            period["mean_area_cm2"],
            1,
        )[0]

        rows.append(
            {
                "period": name,
                "start": period["time_bin"].min(),
                "end": period["time_bin"].max(),
                "n_timepoints": len(period),
                "mean_area_start_cm2": period["mean_area_cm2"].iloc[0],
                "mean_area_end_cm2": period["mean_area_cm2"].iloc[-1],
                "fitted_agr_cm2_per_day": fitted_agr,
                "mean_agr_cm2_per_day": period["mean_agr_cm2_per_day"].mean(),
                "median_agr_cm2_per_day": period[
                    "median_agr_cm2_per_day"
                ].median(),
            }
        )

    return pd.DataFrame(rows)
