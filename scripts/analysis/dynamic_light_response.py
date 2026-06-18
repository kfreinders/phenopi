from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import logging
import re
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass
class ExperimentConfig:
    name: str
    path: Path
    low_start: pd.Timestamp
    low_end: pd.Timestamp
    recovery_end: pd.Timestamp | None = None


def load_experiment_config(path: Path) -> list[ExperimentConfig]:
    raw = json.loads(path.read_text())

    experiments = []
    for item in raw["experiments"]:
        experiments.append(
            ExperimentConfig(
                name=item["name"],
                path=Path(item["path"]),
                low_start=pd.to_datetime(item["low_start"]),
                low_end=pd.to_datetime(item["low_end"]),
                recovery_end=(
                    pd.to_datetime(item["recovery_end"])
                    if item.get("recovery_end") is not None
                    else None
                ),
            )
        )

    return experiments


# -----------------------------------------------------------------------------
# Data preparation
# -----------------------------------------------------------------------------

def extract_timestamp_from_image_name(image_name: str) -> pd.Timestamp:
    match = re.search(r"(\d{8}_\d{6})", str(image_name))
    if match is None:
        raise ValueError(f"Could not extract timestamp from image name: {image_name}")

    return pd.to_datetime(match.group(1), format="%Y%m%d_%H%M%S")


def load_experiment_data(
    cfg: ExperimentConfig,
    area_col: str = "area_cm2",
    plant_col: str = "plant",
    image_col: str = "image",
) -> pd.DataFrame:
    df = pd.read_csv(cfg.path)

    required = {area_col, plant_col, image_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{cfg.path} is missing required columns: {missing}")

    df = df.copy()
    df["experiment"] = cfg.name
    df["timestamp"] = df[image_col].apply(extract_timestamp_from_image_name)
    df["plant_id"] = cfg.name + "__" + df[plant_col].astype(str)

    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[area_col, "timestamp"])
    df = df[df[area_col] > 0]

    return df


def collapse_triplicates(
    df: pd.DataFrame,
    area_col: str = "area_cm2",
    window: str = "3min",
) -> pd.DataFrame:
    df = df.copy()
    df["time_bin"] = df["timestamp"].dt.floor(window)

    grouped = (
        df.groupby(["experiment", "plant_id", "time_bin"], as_index=False)
        .agg(
            area_mean=(area_col, "mean"),
            area_sd=(area_col, "std"),
            n_replicates=(area_col, "count"),
        )
    )

    grouped = grouped.rename(columns={"time_bin": "timestamp"})
    grouped["area_cv"] = grouped["area_sd"] / grouped["area_mean"]

    return grouped


def add_piecewise_time_variables(
    df: pd.DataFrame,
    cfgs: list[ExperimentConfig],
) -> pd.DataFrame:
    df = df.copy()

    cfg_lookup = {cfg.name: cfg for cfg in cfgs}

    rows = []
    for experiment, sub in df.groupby("experiment", sort=False):
        cfg = cfg_lookup[experiment]
        sub = sub.copy()

        t0 = sub["timestamp"].min()

        low_start_days = (cfg.low_start - t0).total_seconds() / 86400
        low_end_days = (cfg.low_end - t0).total_seconds() / 86400

        sub["time_days"] = (
            sub["timestamp"] - t0
        ).dt.total_seconds() / 86400

        t = sub["time_days"].to_numpy()

        # Piecewise basis:
        # baseline_time increases throughout
        # low_time increases only during low-light period
        # recovery_time increases only after low-light period
        sub["baseline_time"] = t

        sub["low_time"] = np.clip(
            t - low_start_days,
            a_min=0,
            a_max=low_end_days - low_start_days,
        )

        sub["recovery_time"] = np.clip(
            t - low_end_days,
            a_min=0,
            a_max=None,
        )

        sub["phase"] = "pre"
        sub.loc[
            (sub["time_days"] >= low_start_days)
            & (sub["time_days"] < low_end_days),
            "phase",
        ] = "low"
        sub.loc[sub["time_days"] >= low_end_days, "phase"] = "recovery"

        sub["low_start_days"] = low_start_days
        sub["low_end_days"] = low_end_days

        rows.append(sub)

    return pd.concat(rows, ignore_index=True)


def prepare_model_data(
    cfgs: list[ExperimentConfig],
    area_col: str = "area_cm2",
    triplicate_window: str = "3min",
) -> pd.DataFrame:
    dfs = [
        load_experiment_data(cfg, area_col=area_col)
        for cfg in cfgs
    ]

    raw = pd.concat(dfs, ignore_index=True)
    collapsed = collapse_triplicates(
        raw,
        area_col=area_col,
        window=triplicate_window,
    )

    collapsed = add_piecewise_time_variables(collapsed, cfgs)
    collapsed["log_area"] = np.log(collapsed["area_mean"])

    collapsed["experiment"] = collapsed["experiment"].astype("category")
    collapsed["phase"] = pd.Categorical(
        collapsed["phase"],
        categories=["pre", "low", "recovery"],
        ordered=True,
    )

    return collapsed


# -----------------------------------------------------------------------------
# Modeling
# -----------------------------------------------------------------------------

def fit_dynamic_response_model(df: pd.DataFrame):
    """
    Model interpretation:

    baseline_time:
        Growth slope before treatment.

    low_time:
        Change in slope during low-light period.

    recovery_time:
        Change in slope after returning to normal light.

    Interactions with experiment:
        Whether these slopes differ between light perturbation experiments.
    """

    formula = (
        "log_area ~ experiment * baseline_time "
        "+ experiment * low_time "
        "+ experiment * recovery_time"
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        model = smf.mixedlm(
            formula=formula,
            data=df,
            groups=df["plant_id"],
            re_formula="1",
        )

        result = model.fit(
            method="lbfgs",
            maxiter=1000,
            reml=False,
        )

    return result


def save_model_summary(result, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "dynamic_response_model_summary.txt"
    summary_path.write_text(str(result.summary()))

    params_path = output_dir / "dynamic_response_model_parameters.csv"
    result.params.to_csv(params_path, header=["estimate"])


def compute_experiment_slopes(
    result,
    experiments: list[str],
) -> pd.DataFrame:
    """
    Convert model coefficients into phase-specific slopes.

    Because the model is piecewise linear in log(area), slopes are approximately
    relative growth rates per day.
    """
    params = result.params

    rows = []

    reference = experiments[0]

    for exp in experiments:
        baseline = params.get("baseline_time", 0.0)
        low_delta = params.get("low_time", 0.0)
        recovery_delta = params.get("recovery_time", 0.0)

        if exp != reference:
            baseline += params.get(f"experiment[T.{exp}]:baseline_time", 0.0)
            low_delta += params.get(f"experiment[T.{exp}]:low_time", 0.0)
            recovery_delta += params.get(f"experiment[T.{exp}]:recovery_time", 0.0)

        low_slope = baseline + low_delta
        recovery_slope = baseline + low_delta + recovery_delta

        rows.append(
            {
                "experiment": exp,
                "pre_slope_log_area_per_day": baseline,
                "low_slope_log_area_per_day": low_slope,
                "recovery_slope_log_area_per_day": recovery_slope,
                "pre_rgr_percent_per_day": baseline * 100,
                "low_rgr_percent_per_day": low_slope * 100,
                "recovery_rgr_percent_per_day": recovery_slope * 100,
                "low_change_percent_per_day": low_delta * 100,
                "recovery_change_percent_per_day": recovery_delta * 100,
            }
        )

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Plotting
# -----------------------------------------------------------------------------

def predict_population_curve(result, df: pd.DataFrame) -> pd.DataFrame:
    pred_df = df.copy()
    pred_df["log_area_pred"] = result.predict(pred_df)
    pred_df["area_pred"] = np.exp(pred_df["log_area_pred"])

    return pred_df


def plot_area_curves(
    df: pd.DataFrame,
    pred_df: pd.DataFrame,
    cfgs: list[ExperimentConfig],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    n_exp = df["experiment"].nunique()
    fig, axes = plt.subplots(
        n_exp,
        1,
        figsize=(9, 4 * n_exp),
        sharex=False,
        squeeze=False,
    )

    cfg_lookup = {cfg.name: cfg for cfg in cfgs}

    for ax, (experiment, sub) in zip(axes[:, 0], df.groupby("experiment")):
        cfg = cfg_lookup[experiment]
        pred_sub = pred_df[pred_df["experiment"] == experiment].copy()

        for _, plant_df in sub.groupby("plant_id"):
            ax.plot(
                plant_df["timestamp"],
                plant_df["area_mean"],
                linewidth=0.8,
                alpha=0.2,
            )

        summary = (
            sub.groupby("timestamp", as_index=False)
            .agg(
                median_area=("area_mean", "median"),
                q25=("area_mean", lambda x: x.quantile(0.25)),
                q75=("area_mean", lambda x: x.quantile(0.75)),
            )
            .sort_values("timestamp")
        )

        pred_summary = (
            pred_sub.groupby("timestamp", as_index=False)
            .agg(pred_area=("area_pred", "median"))
            .sort_values("timestamp")
        )

        ax.fill_between(
            summary["timestamp"],
            summary["q25"],
            summary["q75"],
            alpha=0.2,
            linewidth=0,
        )

        ax.plot(
            summary["timestamp"],
            summary["median_area"],
            linewidth=2,
            label="Median observed",
        )

        ax.plot(
            pred_summary["timestamp"],
            pred_summary["pred_area"],
            linewidth=2,
            linestyle="--",
            label="Model prediction",
        )

        ax.axvspan(
            cfg.low_start,
            cfg.low_end,
            alpha=0.15,
            label="Low-light period",
        )

        ax.set_title(experiment)
        ax.set_ylabel("Canopy area (cm2)")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(frameon=False)

    axes[-1, 0].set_xlabel("Time")
    plt.tight_layout()
    fig.savefig(output_dir / "dynamic_response_area_curves.png", dpi=300)
    plt.close(fig)


def plot_phase_slopes(slopes: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_df = slopes.melt(
        id_vars="experiment",
        value_vars=[
            "pre_rgr_percent_per_day",
            "low_rgr_percent_per_day",
            "recovery_rgr_percent_per_day",
        ],
        var_name="phase",
        value_name="rgr_percent_per_day",
    )

    plot_df["phase"] = plot_df["phase"].replace(
        {
            "pre_rgr_percent_per_day": "Pre",
            "low_rgr_percent_per_day": "Low light",
            "recovery_rgr_percent_per_day": "Recovery",
        }
    )

    fig, ax = plt.subplots(figsize=(7, 4))

    phases = ["Pre", "Low light", "Recovery"]
    x = np.arange(len(phases))

    width = 0.8 / slopes["experiment"].nunique()

    for i, (experiment, sub) in enumerate(plot_df.groupby("experiment")):
        offsets = x - 0.4 + width / 2 + i * width

        values = [
            sub.loc[sub["phase"] == phase, "rgr_percent_per_day"].iloc[0]
            for phase in phases
        ]

        ax.bar(
            offsets,
            values,
            width=width,
            label=experiment,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(phases)
    ax.set_ylabel("Estimated RGR (% per day)")
    ax.set_title("Phase-specific growth rates")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False)

    plt.tight_layout()
    fig.savefig(output_dir / "dynamic_response_phase_slopes.png", dpi=300)
    plt.close(fig)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit dynamic response model to low-light perturbation experiments."
    )

    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="JSON config describing experiments and low-light intervals.",
    )

    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("results/dynamic_response"),
        help="Output directory.",
    )

    parser.add_argument(
        "--area-col",
        type=str,
        default="area_cm2",
        help="Column containing canopy area.",
    )

    parser.add_argument(
        "--triplicate-window",
        type=str,
        default="3min",
        help="Time window used to collapse triplicate captures.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed logging.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger(__name__)
    args.outdir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading experiment config: %s", args.config)
    cfgs = load_experiment_config(args.config)

    logger.info("Preparing model data")
    df = prepare_model_data(
        cfgs,
        area_col=args.area_col,
        triplicate_window=args.triplicate_window,
    )

    model_data_path = args.outdir / "dynamic_response_model_data.csv"
    logger.info("Writing model data: %s", model_data_path)
    df.to_csv(model_data_path, index=False)

    logger.info("Fitting dynamic response model")
    result = fit_dynamic_response_model(df)

    logger.info("Writing model summary")
    save_model_summary(result, args.outdir)

    experiments = list(df["experiment"].cat.categories)
    slopes = compute_experiment_slopes(result, experiments)

    slopes_path = args.outdir / "phase_specific_growth_rates.csv"
    logger.info("Writing phase-specific growth rates: %s", slopes_path)
    slopes.to_csv(slopes_path, index=False)

    logger.info("Generating predictions")
    pred_df = predict_population_curve(result, df)

    pred_path = args.outdir / "dynamic_response_predictions.csv"
    pred_df.to_csv(pred_path, index=False)

    logger.info("Writing plots")
    plot_area_curves(df, pred_df, cfgs, args.outdir)
    plot_phase_slopes(slopes, args.outdir)

    logger.info("Done")


if __name__ == "__main__":
    main()
