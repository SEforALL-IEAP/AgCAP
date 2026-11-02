"""
Sidebar filter logic shared by all server-side callbacks (CSV export, analysis charts,
bubble chart, legend / filter histograms).

The same rules are implemented client-side in assets/agcap_filters.js (map and table);
keep the two in sync:

- Numeric filter: a row passes if its value is within [min, max]. Rows with a missing
  value pass only if the filter card's "Include N empty values" box is ticked
  (na_store[column] is True).
- Categorical filter: a row passes if its value is among the selected options. Rows
  with a missing value pass only if the "(empty)" option (MISSING) is selected.
- An empty categorical selection means no filter on that column.
"""
import pandas as pd

# Option value used for "(empty)" in categorical filter dropdowns
MISSING = '__missing__'


def missing_mask(series):
    """True where a value counts as missing (NaN/None, or an empty string)."""
    missing = series.isna()
    if not pd.api.types.is_numeric_dtype(series):
        missing |= series.astype(str).eq('')
    return missing


def filter_mask(df, slider_vals, slider_ids, cat_vals, cat_ids, na_store=None, exclude_col=None):
    """Boolean mask of rows passing all sidebar filters (optionally ignoring one column)."""
    na_store = na_store or {}
    mask = pd.Series(True, index=df.index)
    for value, sid in zip(slider_vals or [], slider_ids or []):
        col = sid['column']
        if col == exclude_col or col not in df.columns or not value:
            continue
        s = df[col]
        in_range = (s >= value[0]) & (s <= value[1])
        if na_store.get(col):
            in_range |= s.isna()
        mask &= in_range
    for values, cid in zip(cat_vals or [], cat_ids or []):
        col = cid['column']
        if col == exclude_col or col not in df.columns or not values:
            continue
        s = df[col]
        missing = missing_mask(s)
        accepted = [v for v in values if v != MISSING]
        passes = ~missing & s.astype(str).isin(accepted)
        if MISSING in values:
            passes |= missing
        mask &= passes
    return mask


def apply_filters(df, slider_vals, slider_ids, cat_vals, cat_ids, na_store=None):
    """Rows of df passing all sidebar filters."""
    return df[filter_mask(df, slider_vals, slider_ids, cat_vals, cat_ids, na_store)]
