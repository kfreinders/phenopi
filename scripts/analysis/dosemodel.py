from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


@dataclass
class LowLightExperiment:
    name: str
    csv_path: Path
    normal_light: float
    low_light: float
    treatment_start_day: float = 5.0
    treatment_duration_days: float = 3.0


def extract_timestamp(image_name: str) -> pd.Timestamp:
    match = re.search(r"(\d{8}_\d{6})", str(image_name))
    if match is None:
        raise ValueError(f"Could not extract timestamp from: {image_name}")

    return pd.to_datetime(match.group(1), format="%Y%m%d_%H%M%S")


def load_growth_data(
    exp: LowLightExperiment,
    area_col: str = "area_cm2",
    plant_col: str = "plant",
    image_col: str = "image",
    triplicate_window: str = "3min",
) -> pd.DataFrame:
    df = pd.read_csv(exp.csv_path).copy()

    required_cols = {area_col, plant_col, image_col}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"{exp.csv_path} is missing columns: {missing_cols}")

    df["timestamp"] = df[image_col].apply(extract_timestamp)
    df["time_bin"] = df["timestamp"].dt.floor(triplicate_window)

    grouped = (
        df.groupby([plant_col, "time_bin"], as_index=False)
        .agg(area=(area_col, "mean"))
        .rename(columns={plant_col: "plant", "time_bin": "timestamp"})
    )

    grouped = grouped[grouped["area"] > 0].copy()

    grouped["experiment"] = exp.name
    grouped["normal_light"] = exp.normal_light
    grouped["low_light"] = exp.low_light
    grouped["dose"] = 1.0 - exp.low_light / exp.normal_light
    grouped["treatment_start_day"] = exp.treatment_start_day
    grouped["treatment_duration_days"] = exp.treatment_duration_days

    t0 = grouped["timestamp"].min()
    grouped["time_days"] = (
        grouped["timestamp"] - t0
    ).dt.total_seconds() / 86400

    grouped["period"] = assign_period(
        grouped["time_days"].to_numpy(),
        treatment_start_day=exp.treatment_start_day,
        treatment_duration_days=exp.treatment_duration_days,
    )

    return grouped


def assign_period(
    t: np.ndarray,
    treatment_start_day: float,
    treatment_duration_days: float,
) -> np.ndarray:
    treatment_end_day = treatment_start_day + treatment_duration_days

    period = np.full(len(t), "pre", dtype=object)
    period[(t >= treatment_start_day) & (t < treatment_end_day)] = "low_light"
    period[t >= treatment_end_day] = "recovery"

    return period


def piecewise_time_terms(
    t: np.ndarray,
    treatment_start_day: float,
    treatment_duration_days: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    treatment_end_day = treatment_start_day + treatment_duration_days

    pre_time = np.minimum(t, treatment_start_day)

    treatment_time = np.clip(
        t - treatment_start_day,
        0.0,
        treatment_duration_days,
    )

    recovery_time = np.clip(
        t - treatment_end_day,
        0.0,
        None,
    )

    return pre_time, treatment_time, recovery_time


def piecewise_log_area_model(
    t: np.ndarray,
    log_a0: float,
    r_pre: float,
    r_treatment: float,
    r_recovery: float,
    treatment_start_day: float = 5.0,
    treatment_duration_days: float = 3.0,
) -> np.ndarray:
    pre_time, treatment_time, recovery_time = piecewise_time_terms(
        t,
        treatment_start_day=treatment_start_day,
        treatment_duration_days=treatment_duration_days,
    )

    return (
        log_a0
        + r_pre * pre_time
        + r_treatment * treatment_time
        + r_recovery * recovery_time
    )


def summarize_experiment_median(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(
            [
                "experiment",
                "dose",
                "normal_light",
                "low_light",
                "time_days",
                "period",
                "treatment_start_day",
                "treatment_duration_days",
            ],
            as_index=False,
        )
        .agg(
            median_area=("area", "median"),
            mean_area=("area", "mean"),
            q25_area=("area", lambda values: values.quantile(0.25)),
            q75_area=("area", lambda values: values.quantile(0.75)),
            n_plants=("plant", "nunique"),
        )
        .sort_values(["experiment", "time_days"])
    )


def fit_piecewise_experiment_model(
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    prediction_frames = []

    for experiment, sub in summary.groupby("experiment", observed=True):
        sub = sub.sort_values("time_days").copy()

        t = sub["time_days"].to_numpy(dtype=float)
        y_area = sub["median_area"].to_numpy(dtype=float)
        y = np.log(y_area)

        treatment_start_day = float(sub["treatment_start_day"].iloc[0])
        treatment_duration_days = float(sub["treatment_duration_days"].iloc[0])

        p0 = [
            np.log(max(y_area[0], 1e-6)),  # log_a0
            0.35,                          # r_pre
            0.15,                          # r_treatment
            0.25,                          # r_recovery
        ]

        bounds = (
            [-np.inf, -2.0, -2.0, -2.0],
            [np.inf, 5.0, 5.0, 5.0],
        )

        popt, pcov = curve_fit(
            lambda t, log_a0, r_pre, r_treatment, r_recovery: piecewise_log_area_model(
                t,
                log_a0=log_a0,
                r_pre=r_pre,
                r_treatment=r_treatment,
                r_recovery=r_recovery,
                treatment_start_day=treatment_start_day,
                treatment_duration_days=treatment_duration_days,
            ),
            t,
            y,
            p0=p0,
            bounds=bounds,
            maxfev=10000,
        )

        standard_errors = np.sqrt(np.diag(pcov))

        parameter_names = [
            "log_a0",
            "r_pre",
            "r_treatment",
            "r_recovery",
        ]

        for name, estimate, std_error in zip(parameter_names, popt, standard_errors):
            rows.append(
                {
                    "experiment": experiment,
                    "parameter": name,
                    "estimate": estimate,
                    "std_error": std_error,
                    "dose": float(sub["dose"].iloc[0]),
                    "normal_light": float(sub["normal_light"].iloc[0]),
                    "low_light": float(sub["low_light"].iloc[0]),
                }
            )

        log_a0, r_pre, r_treatment, r_recovery = popt

        rows.extend(
            [
                {
                    "experiment": experiment,
                    "parameter": "treatment_rgr_change_vs_pre",
                    "estimate": r_treatment - r_pre,
                    "std_error": np.nan,
                    "dose": float(sub["dose"].iloc[0]),
                    "normal_light": float(sub["normal_light"].iloc[0]),
                    "low_light": float(sub["low_light"].iloc[0]),
                },
                {
                    "experiment": experiment,
                    "parameter": "recovery_rgr_change_vs_pre",
                    "estimate": r_recovery - r_pre,
                    "std_error": np.nan,
                    "dose": float(sub["dose"].iloc[0]),
                    "normal_light": float(sub["normal_light"].iloc[0]),
                    "low_light": float(sub["low_light"].iloc[0]),
                },
                {
                    "experiment": experiment,
                    "parameter": "recovery_rgr_change_vs_treatment",
                    "estimate": r_recovery - r_treatment,
                    "std_error": np.nan,
                    "dose": float(sub["dose"].iloc[0]),
                    "normal_light": float(sub["normal_light"].iloc[0]),
                    "low_light": float(sub["low_light"].iloc[0]),
                },
            ]
        )

        t_pred = np.linspace(t.min(), t.max(), 500)
        log_pred = piecewise_log_area_model(
            t_pred,
            log_a0=log_a0,
            r_pre=r_pre,
            r_treatment=r_treatment,
            r_recovery=r_recovery,
            treatment_start_day=treatment_start_day,
            treatment_duration_days=treatment_duration_days,
        )

        pred = pd.DataFrame(
            {
                "experiment": experiment,
                "time_days": t_pred,
                "predicted_area": np.exp(log_pred),
                "predicted_log_area": log_pred,
                "dose": float(sub["dose"].iloc[0]),
                "normal_light": float(sub["normal_light"].iloc[0]),
                "low_light": float(sub["low_light"].iloc[0]),
            }
        )
        pred["period"] = assign_period(
            pred["time_days"].to_numpy(),
            treatment_start_day=treatment_start_day,
            treatment_duration_days=treatment_duration_days,
        )
        prediction_frames.append(pred)

    parameters = pd.DataFrame(rows)
    predictions = pd.concat(prediction_frames, ignore_index=True)

    return parameters, predictions


def fit_plant_level_period_slopes(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for (experiment, plant), sub in df.groupby(["experiment", "plant"], observed=True):
        sub = sub.sort_values("time_days").copy()

        for period, period_df in sub.groupby("period", observed=True):
            if len(period_df) < 3:
                continue

            elapsed = period_df["time_days"].to_numpy(dtype=float)
            elapsed = elapsed - elapsed.min()

            if np.unique(elapsed).size < 2:
                continue

            log_area = np.log(period_df["area"].to_numpy(dtype=float))
            slope, intercept = np.polyfit(elapsed, log_area, 1)

            rows.append(
                {
                    "experiment": experiment,
                    "plant": plant,
                    "period": period,
                    "rgr_per_day": slope,
                    "intercept": intercept,
                    "n_timepoints": len(period_df),
                    "start_time_days": period_df["time_days"].min(),
                    "end_time_days": period_df["time_days"].max(),
                    "start_area": period_df["area"].iloc[0],
                    "end_area": period_df["area"].iloc[-1],
                    "dose": period_df["dose"].iloc[0],
                    "normal_light": period_df["normal_light"].iloc[0],
                    "low_light": period_df["low_light"].iloc[0],
                }
            )

    return pd.DataFrame(rows)


def summarize_plant_level_slopes(plant_slopes: pd.DataFrame) -> pd.DataFrame:
    if plant_slopes.empty:
        return pd.DataFrame()

    return (
        plant_slopes.groupby(["experiment", "period"], as_index=False)
        .agg(
            n_plants=("plant", "nunique"),
            median_rgr_per_day=("rgr_per_day", "median"),
            mean_rgr_per_day=("rgr_per_day", "mean"),
            sd_rgr_per_day=("rgr_per_day", "std"),
            q25_rgr_per_day=("rgr_per_day", lambda values: values.quantile(0.25)),
            q75_rgr_per_day=("rgr_per_day", lambda values: values.quantile(0.75)),
            dose=("dose", "first"),
            normal_light=("normal_light", "first"),
            low_light=("low_light", "first"),
        )
    )


def plot_piecewise_fit(
    summary: pd.DataFrame,
    predictions: pd.DataFrame,
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))

    for experiment, sub in summary.groupby("experiment", observed=True):
        sub = sub.sort_values("time_days")

        ax.fill_between(
            sub["time_days"],
            sub["q25_area"],
            sub["q75_area"],
            alpha=0.20,
            linewidth=0,
        )

        ax.plot(
            sub["time_days"],
            sub["median_area"],
            marker="o",
            markersize=2,
            linewidth=1.3,
            label=f"{experiment} observed median",
        )

    for experiment, sub in predictions.groupby("experiment", observed=True):
        sub = sub.sort_values("time_days")

        ax.plot(
            sub["time_days"],
            sub["predicted_area"],
            linestyle="--",
            linewidth=2,
            label=f"{experiment} piecewise fit",
        )

        treatment_start = 5.0
        treatment_end = 8.0
        treatment = summary.loc[summary["experiment"] == experiment]
        if not treatment.empty:
            treatment_start = float(treatment["treatment_start_day"].iloc[0])
            treatment_end = treatment_start + float(
                treatment["treatment_duration_days"].iloc[0]
            )

        ax.axvspan(
            treatment_start,
            treatment_end,
            alpha=0.12,
            linewidth=0,
            label="Low-light period" if experiment == summary["experiment"].iloc[0] else None,
        )

    ax.set_xlabel("Time since first image (days)")
    ax.set_ylabel("Projected canopy area (cm²)")
    ax.set_title("Piecewise relative growth-rate model")
    ax.legend(frameon=False)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(outpath, dpi=300)
    plt.close(fig)


def plot_period_rgr_summary(
    plant_slope_summary: pd.DataFrame,
    outpath: Path,
) -> None:
    if plant_slope_summary.empty:
        return

    period_order = ["pre", "low_light", "recovery"]
    plot_df = plant_slope_summary.copy()
    plot_df["period"] = pd.Categorical(
        plot_df["period"],
        categories=period_order,
        ordered=True,
    )
    plot_df = plot_df.sort_values(["experiment", "period"])

    fig, ax = plt.subplots(figsize=(7, 4.5))

    experiments = list(plot_df["experiment"].unique())
    x_base = np.arange(len(period_order))
    width = 0.8 / max(len(experiments), 1)

    for i, experiment in enumerate(experiments):
        sub = plot_df[plot_df["experiment"] == experiment].copy()
        sub = sub.set_index("period").reindex(period_order).reset_index()

        x = x_base - 0.4 + width / 2 + i * width

        y = sub["median_rgr_per_day"].to_numpy(dtype=float)
        lower = y - sub["q25_rgr_per_day"].to_numpy(dtype=float)
        upper = sub["q75_rgr_per_day"].to_numpy(dtype=float) - y

        ax.bar(
            x,
            y,
            width=width,
            alpha=0.75,
            label=experiment,
        )
        ax.errorbar(
            x,
            y,
            yerr=np.vstack([lower, upper]),
            fmt="none",
            linewidth=1,
            capsize=3,
        )

    ax.axhline(0, color="0.4", linewidth=1)
    ax.set_xticks(x_base)
    ax.set_xticklabels(["Pre", "Low light", "Recovery"])
    ax.set_ylabel("Plant-level RGR\n(log cm² day⁻¹)")
    ax.set_title("Plant-level fitted RGR by period")
    ax.legend(frameon=False)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(outpath, dpi=300)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fit a simple piecewise log-area growth model to low-light "
            "plant canopy-area data."
        )
    )
    parser.add_argument("--mild-csv", type=Path, required=True)
    parser.add_argument("--strong-csv", type=Path, default=None)
    parser.add_argument("--control-csv", type=Path, default=None)
    parser.add_argument("--outdir", type=Path, default=Path("results/dose_response"))

    parser.add_argument("--mild-normal-light", type=float, default=250.0)
    parser.add_argument("--mild-low-light", type=float, default=150.0)

    parser.add_argument("--strong-normal-light", type=float, default=150.0)
    parser.add_argument("--strong-low-light", type=float, default=50.0)

    parser.add_argument("--control-light", type=float, default=250.0)

    parser.add_argument("--treatment-start-day", type=float, default=5.0)
    parser.add_argument("--treatment-duration-days", type=float, default=3.0)

    parser.add_argument("--triplicate-window", default="3min")

    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    experiments: list[LowLightExperiment] = []

    if args.control_csv is not None:
        experiments.append(
            LowLightExperiment(
                name="control",
                csv_path=args.control_csv,
                normal_light=args.control_light,
                low_light=args.control_light,
                treatment_start_day=args.treatment_start_day,
                treatment_duration_days=args.treatment_duration_days,
            )
        )

    experiments.append(
        LowLightExperiment(
            name="mild",
            csv_path=args.mild_csv,
            normal_light=args.mild_normal_light,
            low_light=args.mild_low_light,
            treatment_start_day=args.treatment_start_day,
            treatment_duration_days=args.treatment_duration_days,
        )
    )

    if args.strong_csv is not None:
        experiments.append(
            LowLightExperiment(
                name="strong",
                csv_path=args.strong_csv,
                normal_light=args.strong_normal_light,
                low_light=args.strong_low_light,
                treatment_start_day=args.treatment_start_day,
                treatment_duration_days=args.treatment_duration_days,
            )
        )

    df = pd.concat(
        [
            load_growth_data(
                exp,
                triplicate_window=args.triplicate_window,
            )
            for exp in experiments
        ],
        ignore_index=True,
    )

    summary = summarize_experiment_median(df)

    parameters, predictions = fit_piecewise_experiment_model(summary)

    plant_slopes = fit_plant_level_period_slopes(df)
    plant_slope_summary = summarize_plant_level_slopes(plant_slopes)

    df.to_csv(args.outdir / "piecewise_model_data.csv", index=False)
    summary.to_csv(args.outdir / "piecewise_model_summary.csv", index=False)
    parameters.to_csv(args.outdir / "piecewise_model_parameters.csv", index=False)
    predictions.to_csv(args.outdir / "piecewise_model_predictions.csv", index=False)
    plant_slopes.to_csv(args.outdir / "plant_level_period_slopes.csv", index=False)
    plant_slope_summary.to_csv(
        args.outdir / "plant_level_period_slope_summary.csv",
        index=False,
    )

    plot_piecewise_fit(
        summary,
        predictions,
        args.outdir / "piecewise_model_fit.png",
    )
    plot_period_rgr_summary(
        plant_slope_summary,
        args.outdir / "plant_level_period_rgr_summary.png",
    )

    print("\nExperiment-level piecewise model parameters:")
    print(parameters.to_string(index=False))

    if not plant_slope_summary.empty:
        print("\nPlant-level period RGR summary:")
        print(plant_slope_summary.to_string(index=False))

    print(f"\nWrote results to: {args.outdir}")


if __name__ == "__main__":
    main()
