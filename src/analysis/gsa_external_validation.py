"""
External validation: compare grid-level mean_solar_score against
Global Solar Atlas v2 GHI (kWh/m²/day) using Spearman rank correlation.

Pipeline:
  1. Load existing 500 m grid GeoJSON (mean_score per cell).
  2. Open GHI GeoTIFF (EPSG:4326, ~0.0025° ≈ 278 m resolution).
  3. For every occupied grid cell, window-read all GHI pixels that fall
     inside the cell bounding box and compute their mean.
  4. Drop cells where no valid GHI pixels exist.
  5. Compute Spearman ρ between mean_solar_score and mean GHI.
  6. Export scatter plot → figure/fig10_validation_scatter.png
  7. Export comparison table → outputs/validation/gsa_comparison.csv
"""

from pathlib import Path
import logging

import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
from scipy.stats import spearmanr
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ── Paths ──────────────────────────────────────────────────────────────────────
GRID_PATH = Path("data/processed/grid_changsha_urban_core_solar_baseline.geojson")
GHI_PATH = Path(
    "data/external/"
    "China_GISdata_LTAy_AvgDailyTotals_GlobalSolarAtlas-v2_GEOTIFF/GHI.tif"
)
OUT_CSV = Path("outputs/validation/gsa_comparison.csv")
OUT_FIG = Path("figure/fig10_validation_scatter.png")

# ── Logging ────────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ── Zonal statistics ───────────────────────────────────────────────────────────

def extract_mean_ghi(grid: gpd.GeoDataFrame, ghi_path: Path) -> pd.Series:
    """
    For each grid cell return the mean GHI value (kWh/m²/day).

    Uses rasterio window reads so only a small tile is read per cell —
    memory-efficient even for a full-China raster.

    Returns
    -------
    pd.Series indexed like `grid`, NaN where no valid pixels found.
    """
    means = np.full(len(grid), np.nan)

    with rasterio.open(ghi_path) as src:
        nodata = src.nodata  # NaN for this file

        for i, row in enumerate(grid.itertuples(index=False)):
            geom = row.geometry
            minx, miny, maxx, maxy = geom.bounds

            # Build a window aligned to raster pixels
            win = from_bounds(minx, miny, maxx, maxy, src.transform)

            # Clamp to valid raster extent
            win = win.intersection(
                rasterio.windows.Window(0, 0, src.width, src.height)
            )
            if win.width <= 0 or win.height <= 0:
                continue

            data = src.read(1, window=win).astype(np.float32)

            # Mask nodata (NaN in this dataset)
            valid = data[np.isfinite(data)]
            if valid.size > 0:
                means[i] = float(valid.mean())

    return pd.Series(means, index=grid.index, name="mean_ghi")


# ── Scatter plot ───────────────────────────────────────────────────────────────

def make_scatter(df: pd.DataFrame, rho: float, pval: float, out_path: Path) -> None:
    """
    Publication-quality scatter: mean_solar_score (x) vs mean GHI (y).
    Colour-codes by high_potential_ratio; shows Spearman ρ annotation.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 5.5))

    sc = ax.scatter(
        df["mean_score"],
        df["mean_ghi"],
        c=df["high_potential_ratio"],
        cmap="RdYlGn",
        alpha=0.65,
        s=28,
        edgecolors="none",
        vmin=0,
        vmax=1,
    )

    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("High-potential ratio", fontsize=9)

    # Trend line (ordinary least squares)
    coef = np.polyfit(df["mean_score"], df["mean_ghi"], 1)
    xline = np.linspace(df["mean_score"].min(), df["mean_score"].max(), 200)
    ax.plot(xline, np.polyval(coef, xline), color="#333333", linewidth=1.2,
            linestyle="--", label="OLS trend")

    # Annotation
    pval_str = f"{pval:.3e}" if pval < 0.001 else f"{pval:.3f}"
    ax.text(
        0.04, 0.96,
        f"Spearman ρ = {rho:.3f}\np = {pval_str}\nn = {len(df)}",
        transform=ax.transAxes,
        va="top", ha="left",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.7", alpha=0.85),
    )

    ax.set_xlabel("Model mean solar potential score (dimensionless)", fontsize=10)
    ax.set_ylabel("GSA GHI — mean daily total (kWh m⁻² day⁻¹)", fontsize=10)
    ax.set_title(
        "Model score vs. Global Solar Atlas GHI\n"
        "Changsha urban core — 500 m grid cells (occupied only)",
        fontsize=10,
    )
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.grid(which="major", linestyle=":", linewidth=0.5, alpha=0.7)
    ax.legend(fontsize=8, loc="lower right")

    plt.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved figure: %s", out_path)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    # 1. Load grid
    logging.info("Loading grid: %s", GRID_PATH)
    grid = gpd.read_file(GRID_PATH)

    # Keep only occupied cells
    occupied = grid[grid["building_count"] > 0].copy().reset_index(drop=True)
    logging.info("Occupied grid cells: %d / %d", len(occupied), len(grid))

    # 2–3. Extract GHI per cell
    logging.info("Extracting mean GHI per grid cell from: %s", GHI_PATH)
    occupied["mean_ghi"] = extract_mean_ghi(occupied, GHI_PATH)

    # 4. Drop cells with no GHI coverage
    n_before = len(occupied)
    occupied = occupied.dropna(subset=["mean_ghi"])
    n_dropped = n_before - len(occupied)
    if n_dropped:
        logging.warning("Dropped %d cells with no valid GHI pixels.", n_dropped)
    logging.info("Cells retained for correlation: %d", len(occupied))

    # 5. Spearman correlation
    rho, pval = spearmanr(occupied["mean_score"], occupied["mean_ghi"])
    logging.info("Spearman ρ = %.4f  (p = %.4e)", rho, pval)

    # 6. Scatter plot
    make_scatter(occupied, rho, pval, OUT_FIG)

    # 7. Export CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    export_cols = [
        "grid_id",
        "mean_score",
        "mean_ghi",
        "high_potential_ratio",
        "building_count",
        "mean_height_proxy_m",
    ]
    occupied[export_cols].to_csv(OUT_CSV, index=False)
    logging.info("Saved CSV: %s", OUT_CSV)

    # Print summary
    print("\n=== External Validation Summary ===")
    print(f"  Grid cells compared : {len(occupied)}")
    print(f"  Spearman ρ          : {rho:.4f}")
    print(f"  p-value             : {pval:.4e}")
    print(f"  GHI range (kWh/m²/d): {occupied['mean_ghi'].min():.3f} – {occupied['mean_ghi'].max():.3f}")
    print(f"  Score range         : {occupied['mean_score'].min():.2f} – {occupied['mean_score'].max():.2f}")
    print(f"\n  Figure → {OUT_FIG}")
    print(f"  CSV    → {OUT_CSV}")


if __name__ == "__main__":
    main()
