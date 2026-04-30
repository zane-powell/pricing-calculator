"""
renewal.py — Parse Looker exports and compute monthly volumes for renewal quotes.

This module reads two types of Looker exports:
  1. "Completed Checks" — pivot table with months as rows, products as columns.
  2. "Ongoing Monitoring" — flat table with month + total transactions
     (a separate export because OM is recurring, not per-check).

It then maps Looker's product names to the calculator's product names
(handling composites like Enhanced NFC ID = "Enhanced NFC ID" + "Enhanced NFC ID - SoF")
and computes the mean or median monthly volume to feed into the calculator.

This file is "pure" like pricing.py — functions take inputs and return outputs.
No Streamlit, no UI. Reusable from any caller.
"""

from typing import Dict, List, Optional

import pandas as pd

import data


# ---------------------------------------------------------------------------
# Looker → Calculator product mapping
# ---------------------------------------------------------------------------
# Each calculator product is computed by SUMMING one or more Looker columns.
# This handles composites:
#   - "Enhanced NFC ID" (calculator) = "Enhanced NFC ID" + "Enhanced NFC ID - SoF" (Looker)
#     because every NFC ID check is billable, with or without SoF added.
#   - "SoF" (calculator) = "Enhanced NFC ID - SoF" + "Original ID - SoF" + "Bank Info" (Looker)
#     because all three represent a SoF check (Bank Info is the open-banking
#     SoF flow, the other two are SoF on top of an ID check).
LOOKER_TO_CALCULATOR = {
    "Enhanced NFC ID": ["Enhanced NFC ID", "Enhanced NFC ID - SoF"],
    "Original ID": ["Original ID", "Original ID - SoF"],
    "SoF": ["Enhanced NFC ID - SoF", "Original ID - SoF", "Bank Info"],
    "Identity Document Verification": ["Identity Document Verification"],
    "Lite Screening": ["Lite Screening"],
}

# Looker columns we deliberately ignore.
# - "POA Upload" — not a billable product, just a flag on other checks
IGNORED_LOOKER_COLUMNS = ["POA Upload"]


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------
def parse_completed_checks(file) -> pd.DataFrame:
    """
    Parse a Looker "completed checks" export.

    Looker pivots have a quirky two-row header:
      Row 1: dimension label + product names
      Row 2: "Total Transactions" repeated under each metric column
    We read row 1 as the header and drop row 2 from the data.

    Returns a DataFrame:
      - Index: month (datetime, sorted oldest to newest)
      - Columns: Looker product names (e.g. "Enhanced NFC ID", "Bank Info")
      - Values: numeric check counts (NaN/empty cells become 0)

    `file` can be a file path or a file-like object (e.g. from Streamlit's
    file_uploader). pandas handles both transparently.
    """
    df = pd.read_excel(file, header=0)

    # Drop the "Total Transactions" sub-header row if present.
    # We detect it by checking column 1 (any column past the date column will do).
    if len(df) > 0 and str(df.iloc[0, 1]) == "Total Transactions":
        df = df.iloc[1:].reset_index(drop=True)

    # First column holds the dates — rename for clarity, parse as datetime.
    first_col = df.columns[0]
    df = df.rename(columns={first_col: "month"})
    df["month"] = pd.to_datetime(df["month"])
    df = df.set_index("month")

    # Cast all data columns to numeric (after dropping the string sub-header,
    # they're still object-dtype). errors='coerce' turns un-parseable values
    # into NaN, which we then fill with 0.
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    # Sort chronologically — Looker often exports newest-first.
    df = df.sort_index()

    return df


def parse_ongoing_monitoring(file) -> pd.Series:
    """
    Parse a Looker "Ongoing Monitoring" export.

    Format: two columns — month + total transactions.

    Returns a pandas Series indexed by month (datetime, sorted oldest to newest).
    """
    df = pd.read_excel(file, header=0)

    first_col = df.columns[0]
    second_col = df.columns[1]
    df = df.rename(columns={first_col: "month", second_col: "om_total"})
    df["month"] = pd.to_datetime(df["month"])
    df = df.set_index("month")

    series = df["om_total"].fillna(0).sort_index()
    return series


# ---------------------------------------------------------------------------
# Volume computation
# ---------------------------------------------------------------------------
def compute_monthly_volumes(
    checks_df: pd.DataFrame,
    om_series: Optional[pd.Series],
    included_months: List,
    statistic: str = "median",
) -> Dict[str, int]:
    """
    Compute monthly volume per calculator product from filtered Looker data.

    checks_df:        the parsed completed-checks dataframe
    om_series:        the parsed OM series (or None if no OM data)
    included_months:  list of months (datetime) to include in the calculation
    statistic:        "mean" or "median"

    Returns a dict mapping every calculator product name to its computed
    monthly volume (int). Products not present in the Looker data default to 0.
    """
    if statistic not in ("mean", "median"):
        raise ValueError(f"statistic must be 'mean' or 'median', got {statistic!r}")

    # Filter the dataframe to only the months the user wants to include.
    checks_filtered = checks_df.loc[checks_df.index.isin(included_months)]

    result: Dict[str, int] = {}

    # For each calculator product, sum the relevant Looker columns
    # (across columns within each month), then take the stat across months.
    for calc_product, looker_cols in LOOKER_TO_CALCULATOR.items():
        # Some Looker exports won't contain every column — skip missing ones.
        existing_cols = [c for c in looker_cols if c in checks_filtered.columns]

        if not existing_cols or len(checks_filtered) == 0:
            result[calc_product] = 0
            continue

        # Sum the relevant Looker columns to get the per-month volume,
        # then aggregate across months with the chosen statistic.
        monthly_totals = checks_filtered[existing_cols].sum(axis=1)
        value = monthly_totals.mean() if statistic == "mean" else monthly_totals.median()
        result[calc_product] = int(round(value)) if not pd.isna(value) else 0

    # OM is a separate file, handled separately.
    if om_series is not None and len(om_series) > 0:
        om_filtered = om_series.loc[om_series.index.isin(included_months)]
        if len(om_filtered) > 0:
            value = om_filtered.mean() if statistic == "mean" else om_filtered.median()
            result["PEPs Ongoing Monitoring"] = int(round(value)) if not pd.isna(value) else 0
        else:
            result["PEPs Ongoing Monitoring"] = 0
    else:
        result["PEPs Ongoing Monitoring"] = 0

    # Fill in 0 for any calculator products not covered by the Looker data
    # (e.g. KYB, Title Check — these aren't in standard Looker exports).
    for product in data.PRODUCTS:
        if product not in result:
            result[product] = 0

    return result


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------
def detect_partial_months(
    checks_df: pd.DataFrame,
    threshold_ratio: float = 0.3,
) -> List:
    """
    Heuristic to flag months that look partial (typically the first/last
    month of a contract, or the current month if exported mid-month).

    A month is flagged as partial if its total check count is less than
    `threshold_ratio` × the median total of all months.

    Default threshold (30%) catches obvious partial months but won't flag
    months that are merely below average. The user can manually exclude
    others via the UI checkboxes.

    Returns: list of months (datetime) considered partial.
    """
    if len(checks_df) == 0:
        return []

    monthly_totals = checks_df.sum(axis=1)
    median_total = monthly_totals.median()

    if median_total == 0:
        return []

    threshold = median_total * threshold_ratio
    partial = monthly_totals[monthly_totals < threshold].index.tolist()
    return partial
