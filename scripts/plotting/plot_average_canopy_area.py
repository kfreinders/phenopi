from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
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


def add_absolute_growth_rates(
    plant_curves: pd.DataFrame,
    window_hours: float,
    min_points: int,
) -> pd.DataFrame:
    """Add plant-level absolute growth rates.

    Parameters
    ----------
    plant_curves
        Plant-level canopy-area time series.
    window_hours
        Width of the centered fitting window in hours.
    min_points
        Minimum number of points required in a local fit.

    Returns
    -------
    pandas.DataFrame
        Copy of ``plant_curves`` with ``plant_agr_cm2_per_day`` added.
    """
    out = plant_curves.copy()
    out["plant_agr_cm2_per_day"] = np.nan

    for _, plant_df in out.groupby("plant", observed=True):
        out.loc[plant_df.index, "plant_agr_cm2_per_day"] = (
            fit_local_absolute_growth(
                plant_df,
                window_hours=window_hours,
                min_points=min_points,
            )
        )

    return out


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


def iter_chunks(
    df: pd.DataFrame,
    max_gap: pd.Timedelta | None = None,
) -> list[pd.DataFrame]:
    """Split a time series into chunks separated by large gaps.

    Parameters
    ----------
    df
        Data frame containing ``time_bin``.
    max_gap
        Maximum allowed time gap before starting a new chunk.

    Returns
    -------
    list of pandas.DataFrame
        Continuous observed chunks.
    """
    if max_gap is None:
        max_gap = pd.Timedelta(1, unit="h")

    if df.empty:
        return []

    df = df.sort_values("time_bin")
    chunk_id = (df["time_bin"].diff() > max_gap).cumsum()

    return [chunk for _, chunk in df.groupby(chunk_id, sort=False)]


def shade_treatment(
    ax: Axes,
    treatment_start: pd.Timestamp | None,
    treatment_end: pd.Timestamp | None,
) -> None:
    """Shade a treatment interval if provided.

    Parameters
    ----------
    ax
        Axis to annotate.
    treatment_start
        Optional treatment start timestamp.
    treatment_end
        Optional treatment end timestamp.

    Returns
    -------
    None
    """
    if treatment_start is None or treatment_end is None:
        return

    ax.axvspan(
        mdates.date2num(treatment_start),
        mdates.date2num(treatment_end),
        color="#f2c14e",
        alpha=0.18,
        linewidth=0,
    )


def plot_summary(
    summary: pd.DataFrame,
    plant_curves: pd.DataFrame,
    output_path: Path,
    treatment_start: pd.Timestamp | None = None,
    treatment_end: pd.Timestamp | None = None,
    show: bool = False,
) -> None:
    """Plot canopy area and plant-level absolute growth rate.

    Parameters
    ----------
    summary
        Time-level area and absolute-growth-rate summary.
    plant_curves
        Plant-level canopy-area and absolute-growth-rate time series.
    output_path
        Output plot path.
    treatment_start
        Optional treatment start timestamp.
    treatment_end
        Optional treatment end timestamp.
    show
        Whether to show the plot interactively.

    Returns
    -------
    None
    """
    summary = summary.copy()
    plant_curves = plant_curves.copy()

    summary["x"] = mdates.date2num(summary["time_bin"])
    plant_curves["x"] = mdates.date2num(plant_curves["time_bin"])

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
    )
    area_ax, growth_ax = axes

    shade_treatment(area_ax, treatment_start, treatment_end)
    shade_treatment(growth_ax, treatment_start, treatment_end)

    for _, plant_df in plant_curves.groupby("plant", observed=True):
        for chunk in iter_chunks(plant_df):
            area_ax.plot(
                chunk["x"],
                chunk["area_cm2"],
                color="0.7",
                linewidth=0.5,
                alpha=0.18,
            )

    for chunk in iter_chunks(summary):
        area_ax.fill_between(
            chunk["x"],
            chunk["q25_area_cm2"],
            chunk["q75_area_cm2"],
            color="#1f77b4",
            alpha=0.14,
            linewidth=0,
        )
        area_ax.plot(
            chunk["x"],
            chunk["median_area_cm2"],
            color="black",
            linewidth=1.8,
        )

        growth_ax.fill_between(
            chunk["x"],
            chunk["q025_agr_cm2_per_day"],
            chunk["q975_agr_cm2_per_day"],
            color="#2ca02c",
            alpha=0.10,
            linewidth=0,
        )
        growth_ax.fill_between(
            chunk["x"],
            chunk["q25_agr_cm2_per_day"],
            chunk["q75_agr_cm2_per_day"],
            color="#2ca02c",
            alpha=0.22,
            linewidth=0,
        )
        growth_ax.plot(
            chunk["x"],
            chunk["median_agr_cm2_per_day"],
            color="black",
            linewidth=1.8,
        )

    growth_ax.axhline(0, color="0.4", linestyle="--", linewidth=1)

    legend_handles = [
        Patch(
            facecolor="#1f77b4",
            alpha=0.14,
            edgecolor="none",
            label="Area plant IQR",
        ),
        Patch(
            facecolor="#2ca02c",
            alpha=0.10,
            edgecolor="none",
            label="AGR plant 95% interval",
        ),
        Patch(
            facecolor="#2ca02c",
            alpha=0.22,
            edgecolor="none",
            label="AGR plant IQR",
        ),
        Line2D(
            [0],
            [0],
            color="black",
            linewidth=1.8,
            label="Median",
        ),
    ]

    if treatment_start is not None and treatment_end is not None:
        legend_handles.insert(
            0,
            Patch(
                facecolor="#f2c14e",
                alpha=0.18,
                edgecolor="none",
                label="Treatment",
            ),
        )

    fig.legend(
        handles=legend_handles,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=len(legend_handles),
        fontsize=9,
    )

    for ax in axes:
        ax.xaxis_date()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    growth_values = summary["median_agr_cm2_per_day"].dropna()
    if not growth_values.empty:
        y_min = float(growth_values.quantile(0.02))
        y_max = float(growth_values.quantile(0.98))
        y_pad = max(0.1, 0.25 * (y_max - y_min))
        growth_ax.set_ylim(0, y_max + y_pad)

    area_ax.set_title("Canopy area and absolute growth rate over time", pad=22)
    area_ax.set_ylabel("Canopy area (cm²)")
    growth_ax.set_ylabel("Absolute growth rate\n(cm² day⁻¹)")
    growth_ax.set_xlabel("Clock time; overnight periods not imaged")

    growth_ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    growth_ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

    growth_ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[8, 20]))
    growth_ax.tick_params(axis="x", which="major", length=5)
    growth_ax.tick_params(axis="x", which="minor", length=2, labelbottom=False)

    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300)

    if show:
        plt.show()

    plt.close(fig)


def parse_optional_timestamp(value: str | None) -> pd.Timestamp | None:
    """Parse an optional timestamp argument.

    Parameters
    ----------
    value
        Timestamp string or ``None``.

    Returns
    -------
    pandas.Timestamp or None
        Parsed timestamp, or ``None`` when no value was provided.
    """
    if value is None:
        return None

    timestamp = pd.Timestamp(value)
    if not isinstance(timestamp, pd.Timestamp):
        raise ValueError(f"Invalid timestamp: {value!r}")

    return timestamp


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a CSV file, creating parent directories if needed.

    Parameters
    ----------
    df
        Data frame to write.
    path
        Output path.

    Returns
    -------
    None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
