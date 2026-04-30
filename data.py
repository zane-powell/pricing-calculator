"""
data.py — All pricing tables and configuration.

This file holds the "source of truth" pricing data, mirroring the
Excel workbook. Keeping it in its own file means:
  - When prices change, you only edit this file (not the logic).
  - The pricing logic in pricing.py stays clean and readable.
  - You could later move this into a database or YAML file.

NOTE on naming: Thirdfort's middle tier has different names per vertical
(Property = "Flow", Legal = "Compliance", Accounting & FS = "Risk").
We expose this via TIER_DISPLAY_NAMES so the UI can show the right label.
"""

# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
# The order here drives the order of inputs in the UI.
PRODUCTS = [
    "Enhanced NFC ID",
    "Original ID",
    "SoF",
    "PEPs Ongoing Monitoring",
    "Stand Alone Screening",
    "Lite Screening",
    "Identity Document Verification",
    "IAV",
    "KYB - Summary Report",
    "KYB - UBO",
    "Title Check",
]

# ---------------------------------------------------------------------------
# Verticals & tier display names
# ---------------------------------------------------------------------------
VERTICALS = ["Property", "Legal", "Accounting & FS"]

# (essentials_label, mid_label, enterprise_label) per vertical
TIER_DISPLAY_NAMES = {
    "Property":         ("Essentials", "Flow",       "Enterprise"),
    "Legal":            ("Essentials", "Compliance", "Enterprise"),
    "Accounting & FS":  ("Essentials", "Risk",       "Enterprise"),
}

# Internal tier keys we use everywhere in code (vertical-agnostic).
TIER_KEYS = ("essentials", "mid", "enterprise")


# ---------------------------------------------------------------------------
# Credits per check, by product and vertical
# ---------------------------------------------------------------------------
# How many "credits" a single check consumes.
# Example: an Enhanced NFC ID check on the Legal tier costs 10 credits.
CREDITS_PER_CHECK = {
    #                                    Property  Legal   Accounting & FS
    "Enhanced NFC ID":                  {"Property": 5,  "Legal": 10, "Accounting & FS": 5},
    "Original ID":                      {"Property": 5,  "Legal": 10, "Accounting & FS": 5},
    "SoF":                              {"Property": 5,  "Legal": 10, "Accounting & FS": 5},
    "PEPs Ongoing Monitoring":          {"Property": 1,  "Legal": 1,  "Accounting & FS": 1},
    "Stand Alone Screening":            {"Property": 2,  "Legal": 2,  "Accounting & FS": 2},
    "Lite Screening":                   {"Property": 3,  "Legal": 3,  "Accounting & FS": 3},
    "Identity Document Verification":   {"Property": 3,  "Legal": 3,  "Accounting & FS": 3},
    "IAV":                              {"Property": 5,  "Legal": 10, "Accounting & FS": 5},
    "KYB - Summary Report":             {"Property": 5,  "Legal": 5,  "Accounting & FS": 5},
    "KYB - UBO":                        {"Property": 25, "Legal": 25, "Accounting & FS": 25},
    "Title Check":                      {"Property": 8,  "Legal": 8,  "Accounting & FS": 8},
}


# ---------------------------------------------------------------------------
# Annual base platform fee, by vertical and tier
# ---------------------------------------------------------------------------
BASE_FEES = {
    "Property":         {"essentials": 1000,  "mid": 10000, "enterprise": 60000},
    "Legal":            {"essentials": 2000,  "mid": 18000, "enterprise": 60000},
    "Accounting & FS":  {"essentials": 1000,  "mid": 10000, "enterprise": 60000},
}


# ---------------------------------------------------------------------------
# Free credits included in the platform fee, by tier
# ---------------------------------------------------------------------------
INCLUDED_CREDITS = {
    "essentials": 200,
    "mid":        500,
    "enterprise": 2000,
}


# ---------------------------------------------------------------------------
# Volume bands & pricing
# ---------------------------------------------------------------------------
# Each band has:
#   - "max_in_band":  the maximum credits you can buy in this band
#                     (i.e. the size of the band, not the cumulative cap).
#                     Band 1 caps at 12,000.
#                     Band 2 caps at 24,000 cumulative, so 12,000 in band.
#                     Band 3 caps at 48,000 cumulative, so 24,000 in band.
#                     Band 4 caps at 300,000 cumulative, so 252,000 in band.
#                     Band 5 is effectively unlimited.
#   - "package":      credits are sold in chunks of this size in this band.
#                     If you need 28,600 credits in band 3 (pkg 2400) you
#                     must round up to 28,800 (12 × 2400).
#   - prices keyed by tier: cost per credit in that band, for that tier.
#
# These prices are vertical-agnostic — the same price grid applies whether
# you're Property/Legal/Accounting & FS. Only the base fee and the credit
# cost per check differ by vertical.
BANDS = [
    {
        "max_in_band": 12000,   # band 1: 1 to 12,000
        "package": 120,
        "prices": {"essentials": 1.00, "mid": 1.00, "enterprise": 1.00},
    },
    {
        "max_in_band": 12000,   # band 2: 12,001 to 24,000
        "package": 1200,
        "prices": {"essentials": 1.00, "mid": 0.95, "enterprise": 0.90},
    },
    {
        "max_in_band": 24000,   # band 3: 24,001 to 48,000
        "package": 2400,
        "prices": {"essentials": 0.95, "mid": 0.90, "enterprise": 0.75},
    },
    {
        "max_in_band": 252000,  # band 4: 48,001 to 300,000
        "package": 6000,
        "prices": {"essentials": 0.95, "mid": 0.90, "enterprise": 0.50},
    },
    {
        "max_in_band": 10**9,   # band 5: 300,001 and above (effectively unlimited)
        "package": 12000,
        "prices": {"essentials": 0.90, "mid": 0.75, "enterprise": 0.45},
    },
]
