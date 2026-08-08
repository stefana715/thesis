"""
Random Baseline Validation for Proxy-Based Solar Screening Framework
=====================================================================
This script tests whether the proxy-based screening scores provide
discriminatory value beyond random assignment, by comparing observed
rank correlations (proxy vs pvlib) against a null distribution generated
from 1,000 random permutations.

Usage:
    1. Replace the placeholder data in ZONE_DATA with your actual
       per-zone (proxy_score, pvlib_yield) arrays.
    2. Run: python random_baseline_validation.py
    3. Results are printed to console and saved to random_baseline_results.csv

Requirements: numpy, scipy, pandas
"""

import numpy as np
from scipy.stats import spearmanr
import pandas as pd

# ============================================================
# INPUT DATA — Replace with your actual building-level data
# ============================================================
# Each zone should contain paired arrays of:
#   - proxy_scores: your composite solar potential scores
#   - pvlib_yields: the pvlib-based annual yield estimates
#
# Format: { zone_id: (proxy_scores_array, pvlib_yields_array) }
#
# Example with placeholder data — REPLACE with real values:

ZONE_DATA = {
    # --- Original 3 benchmark zones ---
    # "zone_A": (np.array([proxy scores]), np.array([pvlib yields])),
    # "zone_B": (np.array([...]), np.array([...])),
    # "zone_C": (np.array([...]), np.array([...])),
    
    # --- 20 stratified zones (Q1-Q5, 4 each) ---
    # "Q1_grid_XXX": (np.array([...]), np.array([...])),
    # ... etc.
    
    # PLACEHOLDER — generates synthetic data for demonstration
    # DELETE this block and use your real data
    f"demo_zone_{i}": (
        np.random.RandomState(42 + i).uniform(30, 70, size=25),
        np.random.RandomState(142 + i).uniform(1000, 5000, size=25)
    )
    for i in range(20)
}

# Your observed mean rho from the 20-zone spatial robustness test
OBSERVED_MEAN_RHO = 0.950

# ============================================================
# CONFIGURATION
# ============================================================
N_PERMUTATIONS = 1000
RANDOM_SEED = 42

# ============================================================
# ANALYSIS
# ============================================================

def run_random_baseline_test():
    np.random.seed(RANDOM_SEED)
    
    zone_ids = list(ZONE_DATA.keys())
    n_zones = len(zone_ids)
    
    # --- Step 1: Compute observed per-zone Spearman rho ---
    observed_rhos = {}
    for zid in zone_ids:
        proxy, pvlib = ZONE_DATA[zid]
        rho, pval = spearmanr(proxy, pvlib)
        observed_rhos[zid] = rho
    
    observed_mean = np.mean(list(observed_rhos.values()))
    print(f"Observed mean Spearman ρ across {n_zones} zones: {observed_mean:.3f}")
    print(f"  (Per-zone range: {min(observed_rhos.values()):.3f} – {max(observed_rhos.values()):.3f})")
    print()
    
    # --- Step 2: Generate null distribution via permutation ---
    null_mean_rhos = []
    null_all_rhos = []  # all individual zone rhos across permutations
    
    for perm_i in range(N_PERMUTATIONS):
        perm_rhos = []
        for zid in zone_ids:
            proxy, pvlib = ZONE_DATA[zid]
            # Randomly shuffle proxy scores within each zone
            shuffled_proxy = np.random.permutation(proxy)
            rho, _ = spearmanr(shuffled_proxy, pvlib)
            perm_rhos.append(rho)
            null_all_rhos.append(rho)
        null_mean_rhos.append(np.mean(perm_rhos))
    
    null_mean_rhos = np.array(null_mean_rhos)
    null_all_rhos = np.array(null_all_rhos)
    
    # --- Step 3: Compute statistics ---
    null_mean = np.mean(null_mean_rhos)
    null_std = np.std(null_mean_rhos)
    null_ci_lower = np.percentile(null_mean_rhos, 2.5)
    null_ci_upper = np.percentile(null_mean_rhos, 97.5)
    
    # p-value: proportion of null distribution >= observed
    # Use OBSERVED_MEAN_RHO (your actual value) for the final test
    p_value = np.mean(null_mean_rhos >= OBSERVED_MEAN_RHO)
    
    # Percentile rank of observed value
    percentile = np.mean(null_mean_rhos < OBSERVED_MEAN_RHO) * 100
    
    # Individual zone null statistics
    null_zone_mean = np.mean(null_all_rhos)
    null_zone_ci_lower = np.percentile(null_all_rhos, 2.5)
    null_zone_ci_upper = np.percentile(null_all_rhos, 97.5)
    
    # --- Step 4: Print results ---
    print("=" * 60)
    print("RANDOM BASELINE TEST RESULTS")
    print("=" * 60)
    print(f"Number of zones:           {n_zones}")
    print(f"Permutations:              {N_PERMUTATIONS}")
    print()
    print("--- Null distribution (random assignment) ---")
    print(f"Mean of null mean ρ:       {null_mean:.4f}")
    print(f"Std of null mean ρ:        {null_std:.4f}")
    print(f"95% CI of null mean ρ:     [{null_ci_lower:.4f}, {null_ci_upper:.4f}]")
    print()
    print(f"Per-zone null mean ρ:      {null_zone_mean:.4f}")
    print(f"Per-zone null 95% CI:      [{null_zone_ci_lower:.4f}, {null_zone_ci_upper:.4f}]")
    print()
    print("--- Observed vs null ---")
    print(f"Observed mean ρ:           {OBSERVED_MEAN_RHO:.3f}")
    print(f"Percentile in null dist:   {percentile:.1f}th")
    print(f"p-value (one-tailed):      {p_value:.4f}")
    if p_value == 0:
        print(f"  → p < {1/N_PERMUTATIONS:.4f} (none of {N_PERMUTATIONS} permutations reached observed value)")
    print()
    print("--- Interpretation ---")
    if p_value < 0.001:
        print("The proxy-based framework provides HIGHLY SIGNIFICANT")
        print("discriminatory value beyond random assignment (p < 0.001).")
    elif p_value < 0.05:
        print("The proxy-based framework provides SIGNIFICANT")
        print(f"discriminatory value beyond random assignment (p = {p_value:.4f}).")
    else:
        print("WARNING: The proxy-based framework does NOT provide")
        print("significant discriminatory value beyond random assignment.")
    
    # --- Step 5: Save results ---
    results = {
        "metric": [
            "n_zones", "n_permutations",
            "null_mean_rho", "null_std_rho", "null_ci_lower", "null_ci_upper",
            "null_zone_mean_rho", "null_zone_ci_lower", "null_zone_ci_upper",
            "observed_mean_rho", "percentile_rank", "p_value"
        ],
        "value": [
            n_zones, N_PERMUTATIONS,
            round(null_mean, 4), round(null_std, 4),
            round(null_ci_lower, 4), round(null_ci_upper, 4),
            round(null_zone_mean, 4), round(null_zone_ci_lower, 4),
            round(null_zone_ci_upper, 4),
            OBSERVED_MEAN_RHO, round(percentile, 1), round(p_value, 4)
        ]
    }
    df = pd.DataFrame(results)
    df.to_csv("random_baseline_results.csv", index=False)
    print()
    print("Results saved to: random_baseline_results.csv")
    
    return null_mean_rhos

if __name__ == "__main__":
    null_dist = run_random_baseline_test()
