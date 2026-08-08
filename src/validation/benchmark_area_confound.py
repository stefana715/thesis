#!/usr/bin/env python3
"""
benchmark_area_confound.py

Circularity / confounding check for the pvlib benchmark validation.

Motivation
----------
`benchmark_robustness.py` reports a mean per-zone Spearman ρ of ~0.95 between the
proxy `solar_potential_score` and the pvlib reference yield. Because the pvlib
yield is computed as

    yield = footprint_area_m2 * ROOF_COVERAGE * shading_factor
            * PANEL_EFF * annual_poa * PERFORMANCE_RATIO / 1000

every term except `footprint_area_m2` and `shading_factor` is a global scalar.
The proxy score is 0.65 * minmax(log1p(area)) + 0.35 * minmax(log1p(height)),
also dominated by footprint area. A high ρ may therefore be an arithmetic
consequence of both quantities being monotone in footprint area, rather than
independent evidence that the proxy tracks physical yield.

This script tests whether ANY signal survives once footprint area is controlled.

Tests (per zone, on the same 20 stratified grids, seed=42)
----------------------------------------------------------
(a) Spearman ρ between proxy score and *unit-area* yield (yield / area).
    Note: because yield is exactly linear in area, yield/area reduces
    identically to shading_factor * const, so (a) is a direct test of whether
    the proxy score tracks the only other per-building term in the benchmark.

(b) Partial Spearman ρ between proxy score and yield, controlling for
    footprint area (Spearman rank-residual method: rank-transform all three
    variables, regress score-ranks and yield-ranks on area-ranks by OLS, then
    correlate the residuals). p-value from a t-test with df = n - 3.

(c) Control: Spearman ρ between footprint area alone and pvlib yield.
    If (c) ~ 1.0 while (a) and (b) collapse, the headline ρ is confounded.

Also reports shading diagnostics: how many buildings are actually shaded at all
(shading_factor < 1), and how many distinct height values exist per zone.

All data loading, grid stratification (seed=42), shading and yield computation
are imported directly from `benchmark_robustness.py` so the zone set and yield
values are bit-for-bit identical to the published robustness run.

Usage
-----
    python src/validation/benchmark_area_confound.py \
        --input      data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir outputs/validation/
"""

import argparse
import importlib.util
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

# ── Import the published benchmark module by path (src/ has no __init__.py) ───

_ROBUSTNESS_PATH = Path(__file__).resolve().parent / "benchmark_robustness.py"
_spec = importlib.util.spec_from_file_location("benchmark_robustness", _ROBUSTNESS_PATH)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

ALPHA = 0.05


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ── Statistics ────────────────────────────────────────────────────────────────

def denoise(a: np.ndarray, ndigits: int = 9) -> np.ndarray:
    """
    Collapse floating-point rounding noise into exact ties.

    `yield / area` reduces analytically to `shading_factor * const`, so in a zone
    where no building is shaded the only remaining spread is ~1e-16 relative
    rounding error from the multiply-then-divide. Without this, spearmanr would
    happily rank that noise and report a spurious "significant" correlation.
    Rounding to 9 significant digits relative to the median kills the noise while
    preserving any genuine shading difference (smallest observed: 1.0 vs 0.9968).
    """
    a = np.asarray(a, dtype=float)
    scale = np.median(np.abs(a))
    if not np.isfinite(scale) or scale == 0:
        return a
    return np.round(a / scale, ndigits)


def is_constant(a: np.ndarray) -> bool:
    a = denoise(a)
    return bool(np.ptp(a) == 0)


def spearman_safe(x: pd.Series, y: pd.Series):
    """
    Spearman ρ that returns (nan, nan) when either input is constant to within
    floating-point noise. Ranking is done on the denoised values so that
    numerically-tied observations are treated as genuine ties.
    """
    x = denoise(np.asarray(x, dtype=float))
    y = denoise(np.asarray(y, dtype=float))
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return float("nan"), float("nan")
    rho, p = stats.spearmanr(x, y)
    return float(rho), float(p)


def partial_spearman(x, y, z):
    """
    Partial Spearman correlation of x and y controlling for z, via the
    rank-residual method:
      1. rank-transform x, y, z (average ranks for ties)
      2. OLS-regress rank(x) on rank(z) and rank(y) on rank(z)
      3. Pearson-correlate the two residual vectors

    p-value: two-sided t-test, t = r * sqrt((n - 3) / (1 - r^2)), df = n - 3.

    Returns (rho, p). Returns (nan, nan) if the control explains one of the
    variables perfectly (zero residual variance) or n < 4.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    n = len(x)
    if n < 4:
        return float("nan"), float("nan")

    rx = stats.rankdata(denoise(x))
    ry = stats.rankdata(denoise(y))
    rz = stats.rankdata(denoise(z))

    if np.ptp(rz) == 0:
        # Nothing to control for — fall back to plain Spearman on ranks
        return spearman_safe(x, y)

    def residual(r):
        slope, intercept = np.polyfit(rz, r, 1)
        return r - (slope * rz + intercept)

    ex = residual(rx)
    ey = residual(ry)

    # Zero residual variance => control fully determines that variable
    if np.std(ex) < 1e-12 or np.std(ey) < 1e-12:
        return float("nan"), float("nan")

    rho = float(np.corrcoef(ex, ey)[0, 1])
    rho = max(-1.0, min(1.0, rho))

    if abs(rho) >= 1.0:
        return rho, 0.0
    t = rho * np.sqrt((n - 3) / (1.0 - rho ** 2))
    p = float(2.0 * stats.t.sf(abs(t), df=n - 3))
    return rho, p


# ── Per-zone analysis ─────────────────────────────────────────────────────────

def analyse_grid(grid_row, bldg, grid_geom, annual_poa):
    """Return a result dict for one grid cell, or None if it was skipped."""
    gid = int(grid_row["grid_id"])
    cell = grid_geom[grid_geom["grid_id"] == gid]
    zone = gpd.sjoin(
        bldg, cell[["grid_id", "geometry"]], how="inner", predicate="intersects"
    ).drop(columns=["index_right"], errors="ignore")

    n = len(zone)
    if n < 3:
        logging.warning("  grid_id=%d: only %d buildings — skipping", gid, n)
        return None

    # Identical yield computation to the published robustness run
    zone = bench.compute_pvlib_yield(zone, annual_poa)

    score = zone["solar_potential_score"].astype(float)
    yld   = zone["pvlib_yield_kwh"].astype(float)
    area  = zone["footprint_area_m2"].astype(float)
    shade = zone["shading_factor"].astype(float)
    unit_yield = yld / area

    rho_headline, p_headline = spearman_safe(score, yld)          # published metric
    rho_a, p_a = spearman_safe(score, unit_yield)                 # (a)
    rho_b, p_b = partial_spearman(score, yld, area)               # (b)
    rho_c, p_c = spearman_safe(area, yld)                         # (c)
    rho_sa, p_sa = spearman_safe(score, area)   # directness of the proxy-area link

    heights = pd.to_numeric(zone["height_proxy_m"], errors="coerce").fillna(6.0)

    return {
        "grid_id": gid,
        "stratum": int(grid_row["stratum"]),
        "n": n,
        "mean_score": float(grid_row["mean_score"]),
        "rho_headline": rho_headline,
        "p_headline": p_headline,
        "rho_a_unit_area": rho_a,
        "p_a_unit_area": p_a,
        "rho_b_partial": rho_b,
        "p_b_partial": p_b,
        "rho_c_area_only": rho_c,
        "p_c_area_only": p_c,
        "rho_score_vs_area": rho_sa,
        "p_score_vs_area": p_sa,
        "unit_yield_constant": bool(is_constant(unit_yield)),
        "n_shaded": int((shade < 1.0).sum()),
        "frac_shaded": float((shade < 1.0).mean()),
        "min_shading_factor": float(shade.min()),
        "n_unique_height": int(heights.nunique()),
        "modal_height_share": float(heights.value_counts(normalize=True).iloc[0]),
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def fmt(v, width=9, prec=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return f"{'n/a':>{width}}"
    return f"{v:>+{width}.{prec}f}"


def format_main_table(df: pd.DataFrame) -> str:
    lines = [
        "",
        "=" * 104,
        "  Area-confound check — per-zone rank correlations (20 stratified 500 m grids, seed=42)",
        "=" * 104,
        f"  {'grid':>5} {'str':>3} {'n':>4}   "
        f"{'headline ρ':>11}   {'(a) unit-area':>13} {'p':>9}   "
        f"{'(b) partial':>11} {'p':>9}   {'(c) area-only':>13} {'score~area':>11}",
        "-" * 104,
    ]
    for _, r in df.iterrows():
        lines.append(
            f"  {int(r['grid_id']):>5} {int(r['stratum']):>3} {int(r['n']):>4}   "
            f"{fmt(r['rho_headline'], 11)}   "
            f"{fmt(r['rho_a_unit_area'], 13)} {fmt(r['p_a_unit_area'], 9, 4).replace('+', ' ')}   "
            f"{fmt(r['rho_b_partial'], 11)} {fmt(r['p_b_partial'], 9, 4).replace('+', ' ')}   "
            f"{fmt(r['rho_c_area_only'], 13)} {fmt(r['rho_score_vs_area'], 11)}"
        )
    lines.append("-" * 104)

    def agg(col, fn):
        s = df[col].dropna()
        return fn(s) if len(s) else float("nan")

    lines.append(
        f"  {'MEAN':>13}      "
        f"{fmt(agg('rho_headline', np.mean), 11)}   "
        f"{fmt(agg('rho_a_unit_area', np.mean), 13)} {'':>9}   "
        f"{fmt(agg('rho_b_partial', np.mean), 11)} {'':>9}   "
        f"{fmt(agg('rho_c_area_only', np.mean), 13)} {fmt(agg('rho_score_vs_area', np.mean), 11)}"
    )
    lines.append(
        f"  {'MEDIAN':>13}      "
        f"{fmt(agg('rho_headline', np.median), 11)}   "
        f"{fmt(agg('rho_a_unit_area', np.median), 13)} {'':>9}   "
        f"{fmt(agg('rho_b_partial', np.median), 11)} {'':>9}   "
        f"{fmt(agg('rho_c_area_only', np.median), 13)} {fmt(agg('rho_score_vs_area', np.median), 11)}"
    )
    lines.append("=" * 104)

    # Significance counts
    n_zones = len(df)
    for col_rho, col_p, label in [
        ("rho_a_unit_area", "p_a_unit_area", "(a) unit-area yield"),
        ("rho_b_partial",   "p_b_partial",   "(b) partial (area controlled)"),
        ("rho_c_area_only", "p_c_area_only", "(c) area only [control]"),
    ]:
        valid = df[df[col_rho].notna()]
        n_pos = int(((valid[col_rho] > 0) & (valid[col_p] < ALPHA)).sum())
        n_neg = int(((valid[col_rho] < 0) & (valid[col_p] < ALPHA)).sum())
        n_undef = n_zones - len(valid)
        lines.append(
            f"  {label:<32} significantly POSITIVE: {n_pos:>2}/{n_zones}   "
            f"significantly NEGATIVE: {n_neg:>2}/{n_zones}   "
            f"undefined (no variance): {n_undef:>2}/{n_zones}"
        )
    lines += ["=" * 104, ""]
    return "\n".join(lines)


def format_shading_table(df: pd.DataFrame, pooled: dict) -> str:
    lines = [
        "",
        "=" * 88,
        "  Shading & height diagnostics — what actually varies per building",
        "=" * 88,
        f"  {'grid':>5} {'n':>4}  {'n shaded':>9} {'% shaded':>9} {'min factor':>11}  "
        f"{'unique h':>9} {'modal h share':>14}",
        "-" * 88,
    ]
    for _, r in df.iterrows():
        lines.append(
            f"  {int(r['grid_id']):>5} {int(r['n']):>4}  "
            f"{int(r['n_shaded']):>9} {100 * r['frac_shaded']:>8.1f}% "
            f"{r['min_shading_factor']:>11.4f}  "
            f"{int(r['n_unique_height']):>9} {100 * r['modal_height_share']:>13.1f}%"
        )
    lines += [
        "-" * 88,
        f"  POOLED over all {int(pooled['n_zones'])} zones: {int(pooled['n_bldg'])} buildings",
        f"    shading_factor == 1.0 (completely unshaded): "
        f"{int(pooled['n_unshaded'])} ({100 * pooled['frac_unshaded']:.2f}%)",
        f"    shading_factor  < 1.0 (any reduction):       "
        f"{int(pooled['n_shaded'])} ({100 * pooled['frac_shaded']:.2f}%)",
        f"    min / mean shading_factor over shaded only:  "
        f"{pooled['min_shaded_factor']:.4f} / {pooled['mean_shaded_factor']:.4f}",
        "=" * 88,
        "",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Test whether proxy-vs-pvlib agreement survives controlling for footprint area"
    )
    p.add_argument("--input", required=True)
    p.add_argument("--grid", required=True)
    p.add_argument("--output_dir", default="outputs/validation/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Loading buildings…")
    bldg = gpd.read_file(args.input)
    logging.info("Loading grid…")
    grid = gpd.read_file(args.grid)
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)

    # Same POA scalar and same 20 grids (seed=42) as the published run
    annual_poa = bench.annual_clearsky_poa()
    selected = bench.select_stratified_grids(grid)

    results, shade_pool = [], []
    for _, row in selected.iterrows():
        logging.info(
            "  Processing grid_id=%d  stratum=Q%d  n_bldg=%d",
            row["grid_id"], row["stratum"], row["building_count"],
        )
        res = analyse_grid(row, bldg, grid, annual_poa)
        if res:
            results.append(res)
            shade_pool.append(res)

    df = pd.DataFrame(results).sort_values(["stratum", "grid_id"]).reset_index(drop=True)

    # Pooled shading statistics
    n_bldg = int(df["n"].sum())
    n_shaded = int(df["n_shaded"].sum())
    shaded_mins = df.loc[df["n_shaded"] > 0, "min_shading_factor"]
    pooled = {
        "n_zones": len(df),
        "n_bldg": n_bldg,
        "n_shaded": n_shaded,
        "n_unshaded": n_bldg - n_shaded,
        "frac_shaded": n_shaded / n_bldg if n_bldg else float("nan"),
        "frac_unshaded": (n_bldg - n_shaded) / n_bldg if n_bldg else float("nan"),
        "min_shaded_factor": float(shaded_mins.min()) if len(shaded_mins) else float("nan"),
        "mean_shaded_factor": float(shaded_mins.mean()) if len(shaded_mins) else float("nan"),
    }

    print(format_main_table(df))
    print(format_shading_table(df, pooled))

    csv_out = output_dir / "benchmark_area_confound_results.csv"
    df.to_csv(csv_out, index=False, float_format="%.6f")
    logging.info("Saved CSV: %s", csv_out)
    logging.info("Done.")


if __name__ == "__main__":
    main()
