import json
import pandas as pd
import geopandas as gpd

b_path = 'data/processed/buildings_changsha_urban_core_solar_baseline.geojson'
g_path = 'data/processed/grid_changsha_urban_core_solar_baseline.geojson'

b = gpd.read_file(b_path)
res = {}
res['building_rows'] = int(len(b))
res['has_is_high_potential'] = bool('is_high_potential' in b.columns)

if 'solar_potential_score' in b.columns:
    s_num = pd.to_numeric(b['solar_potential_score'], errors='coerce')
    res['solar_potential_score_non_numeric_or_nan'] = int(s_num.isna().sum())
    res['q66'] = None if s_num.dropna().empty else float(s_num.quantile(0.66))
else:
    res['solar_potential_score_non_numeric_or_nan'] = None
    res['q66'] = None

if res['has_is_high_potential']:
    col = b['is_high_potential']
    res['is_high_potential_dtype'] = str(col.dtype)
    uniques = pd.Series(col).dropna().unique().tolist()
    try:
        uniques = sorted(uniques)
    except Exception:
        pass
    res['is_high_potential_unique_non_null'] = uniques
    is_hp_num = pd.to_numeric(col, errors='coerce')
    hp_count = int((is_hp_num == 1).sum())
    res['is_high_potential_eq_1_count'] = hp_count
    res['is_high_potential_eq_1_share'] = float(hp_count / len(b)) if len(b) else None
else:
    res['is_high_potential_dtype'] = None
    res['is_high_potential_unique_non_null'] = None
    res['is_high_potential_eq_1_count'] = None
    res['is_high_potential_eq_1_share'] = None

g = gpd.read_file(g_path)
occupied = g[g['building_count'] > 0].copy() if 'building_count' in g.columns else g.iloc[0:0].copy()
res['occupied_grid_count'] = int(len(occupied))

if 'high_potential_building_count' in occupied.columns:
    hp_cells = int((pd.to_numeric(occupied['high_potential_building_count'], errors='coerce').fillna(0) > 0).sum())
    res['occupied_grid_with_high_potential_building_count_gt_0'] = hp_cells
else:
    res['occupied_grid_with_high_potential_building_count_gt_0'] = None

if 'high_potential_ratio' in occupied.columns:
    hr = pd.to_numeric(occupied['high_potential_ratio'], errors='coerce').dropna()
    res['high_potential_ratio_min'] = float(hr.min()) if len(hr) else None
    res['high_potential_ratio_max'] = float(hr.max()) if len(hr) else None
    res['high_potential_ratio_mean'] = float(hr.mean()) if len(hr) else None
else:
    res['high_potential_ratio_min'] = None
    res['high_potential_ratio_max'] = None
    res['high_potential_ratio_mean'] = None

print(json.dumps(res, ensure_ascii=True, indent=2))
