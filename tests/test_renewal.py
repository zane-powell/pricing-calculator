"""
test_renewal.py — Verifies the Looker parsing and aggregation logic.

These tests use synthetic data (not real client data) so they're reproducible
and safe to share publicly.
"""

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

# Add parent folder to Python's import path so we can import renewal/data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import renewal


# ---------------------------------------------------------------------------
# Test fixtures: build small synthetic dataframes that mimic real Looker output
# ---------------------------------------------------------------------------
def make_checks_df():
    """Build a synthetic 6-month dataframe matching real Looker schema."""
    months = pd.to_datetime(
        ["2025-04-01", "2025-05-01", "2025-06-01",
         "2025-07-01", "2025-08-01", "2025-09-01"]
    )
    df = pd.DataFrame(
        {
            "Bank Info": [0, 0, 0, 0, 0, 1],
            "Enhanced NFC ID": [10, 100, 200, 200, 200, 300],   # ramping up
            "Enhanced NFC ID - SoF": [0, 20, 40, 40, 40, 60],
            "Identity Document Verification": [0, 0, 0, 0, 0, 0],
            "Lite Screening": [0, 5, 10, 10, 10, 15],
            "Original ID": [5, 50, 100, 100, 100, 150],
            "Original ID - SoF": [0, 0, 0, 10, 0, 0],
            "POA Upload": [0, 0, 0, 0, 0, 0],
        },
        index=months,
    )
    df.index.name = "month"
    return df


def make_om_series():
    """Build a synthetic OM series."""
    months = pd.to_datetime(["2025-07-01", "2025-08-01", "2025-09-01"])
    return pd.Series([0, 50, 100], index=months, name="om_total")


# ---------------------------------------------------------------------------
# Volume computation tests
# ---------------------------------------------------------------------------
def test_compute_volumes_median_all_months():
    """Median across all 6 months for each calculator product."""
    df = make_checks_df()
    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=df.index.tolist(),
        statistic="median",
    )

    # Enhanced NFC ID = standalone + SoF variant per month, then median.
    # Per month: 10, 120, 240, 240, 240, 360 → median = 240
    assert result["Enhanced NFC ID"] == 240

    # Original ID: 5, 50, 100, 110, 100, 150 → median = 100
    assert result["Original ID"] == 100

    # SoF: 0, 20, 40, 50, 40, 60 → median = 40
    assert result["SoF"] == 40

    # Lite Screening: 0, 5, 10, 10, 10, 15 → median = 10
    assert result["Lite Screening"] == 10


def test_compute_volumes_mean_all_months():
    """Mean across all 6 months."""
    df = make_checks_df()
    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=df.index.tolist(),
        statistic="mean",
    )

    # Enhanced NFC ID per month: 10, 120, 240, 240, 240, 360 → mean = 1210/6 ≈ 202
    assert result["Enhanced NFC ID"] == 202


def test_excluding_partial_months_changes_result():
    """If we exclude the first (partial) month, the median rises."""
    df = make_checks_df()

    # First month (April) has only 10 NFC checks — clearly partial. Exclude it.
    months_to_include = df.index.tolist()[1:]  # drop first month

    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=months_to_include,
        statistic="median",
    )

    # NFC totals without April: 120, 240, 240, 240, 360 → median = 240
    # (Coincidentally the same in this dataset, but the maths is exclusion-aware.)
    assert result["Enhanced NFC ID"] == 240

    # Mean shifts noticeably: (120+240+240+240+360)/5 = 240 (vs 202 with April)
    result_mean = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=months_to_include,
        statistic="mean",
    )
    assert result_mean["Enhanced NFC ID"] == 240


def test_om_volumes_included_when_om_data_provided():
    """OM data should produce a PEPs Ongoing Monitoring volume."""
    df = make_checks_df()
    om = make_om_series()

    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=om,
        included_months=df.index.tolist(),
        statistic="median",
    )

    # OM values (only 3 months of data): 0, 50, 100 → median = 50
    assert result["PEPs Ongoing Monitoring"] == 50


def test_no_om_data_results_in_zero():
    """If no OM file uploaded, the OM volume defaults to zero."""
    df = make_checks_df()
    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=df.index.tolist(),
        statistic="median",
    )
    assert result["PEPs Ongoing Monitoring"] == 0


def test_unmapped_products_default_to_zero():
    """Products not in the Looker data (e.g. KYB) should default to 0."""
    df = make_checks_df()
    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=df.index.tolist(),
        statistic="median",
    )
    # KYB and Title Check aren't in standard Looker checks export
    assert result["KYB - Summary Report"] == 0
    assert result["KYB - UBO"] == 0
    assert result["Title Check"] == 0
    assert result["IAV"] == 0


def test_no_months_included_returns_zeros():
    """Edge case: if user excludes ALL months, all volumes are 0."""
    df = make_checks_df()
    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=[],  # nothing included
        statistic="median",
    )
    for product, volume in result.items():
        assert volume == 0, f"{product} should be 0 but is {volume}"


# ---------------------------------------------------------------------------
# Partial-month detection tests
# ---------------------------------------------------------------------------
def test_detect_partial_months_flags_first_month():
    """The first month is partial (only 15 total checks vs ~ hundreds in others)."""
    df = make_checks_df()
    partial = renewal.detect_partial_months(df, threshold_ratio=0.3)

    # April 2025 (index 0) has total = 0+10+0+0+0+5+0+0 = 15 — well below threshold
    assert pd.Timestamp("2025-04-01") in partial


def test_detect_partial_months_doesnt_flag_normal_months():
    """Months close to the median should not be flagged."""
    df = make_checks_df()
    partial = renewal.detect_partial_months(df, threshold_ratio=0.3)

    # July, August, September should all be normal
    assert pd.Timestamp("2025-07-01") not in partial
    assert pd.Timestamp("2025-08-01") not in partial


def test_detect_partial_months_empty_df():
    """Edge case: empty dataframe shouldn't error."""
    empty = pd.DataFrame()
    assert renewal.detect_partial_months(empty) == []


# ---------------------------------------------------------------------------
# Statistic argument validation
# ---------------------------------------------------------------------------
def test_invalid_statistic_raises():
    """Passing an unknown statistic should raise."""
    df = make_checks_df()
    with pytest.raises(ValueError):
        renewal.compute_monthly_volumes(
            checks_df=df,
            om_series=None,
            included_months=df.index.tolist(),
            statistic="mode",  # not supported
        )


# ---------------------------------------------------------------------------
# Mapping tests
# ---------------------------------------------------------------------------
def test_bank_info_contributes_to_sof():
    """Bank Info column should be summed into the SoF total."""
    months = pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"])
    df = pd.DataFrame(
        {
            "Bank Info": [10, 10, 10],   # 10 every month — should map to SoF
            "Enhanced NFC ID": [0, 0, 0],
            "Enhanced NFC ID - SoF": [0, 0, 0],
            "Original ID": [0, 0, 0],
            "Original ID - SoF": [0, 0, 0],
            "Identity Document Verification": [0, 0, 0],
            "Lite Screening": [0, 0, 0],
            "POA Upload": [0, 0, 0],
        },
        index=months,
    )
    df.index.name = "month"

    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=df.index.tolist(),
        statistic="mean",
    )

    # Bank Info alone (10/month) should produce SoF = 10
    assert result["SoF"] == 10


def test_poa_upload_is_ignored():
    """POA Upload should never contribute to any calculator product."""
    months = pd.to_datetime(["2025-01-01", "2025-02-01"])
    df = pd.DataFrame(
        {
            "Bank Info": [0, 0],
            "Enhanced NFC ID": [0, 0],
            "Enhanced NFC ID - SoF": [0, 0],
            "Original ID": [0, 0],
            "Original ID - SoF": [0, 0],
            "Identity Document Verification": [0, 0],
            "Lite Screening": [0, 0],
            "POA Upload": [1000, 1000],   # huge volume, should be ignored
        },
        index=months,
    )
    df.index.name = "month"

    result = renewal.compute_monthly_volumes(
        checks_df=df,
        om_series=None,
        included_months=df.index.tolist(),
        statistic="mean",
    )

    # Despite 1000 POA uploads, every calculator product should be 0
    for product, volume in result.items():
        assert volume == 0, f"{product} should be 0 but is {volume}"
