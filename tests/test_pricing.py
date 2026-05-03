"""
test_pricing.py — Verifies our Python pricing matches the Excel calculator.

Run with:   python -m pytest tests/

Why tests matter (especially as a beginner):
  - You can change pricing.py confidently — if you break something,
    pytest tells you immediately.
  - It documents what "correct" looks like.
  - When a colleague queries a quote, you can point at the tests.
"""

import sys
from pathlib import Path

# Add parent folder to Python's import path so we can import pricing/data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pricing


# The exact scenario from the Excel "Agent Interface" tab (Debenhams Ottaway).
DEBENHAMS_INPUTS = {
    "Enhanced NFC ID": 290,
    "Original ID": 0,
    "SoF": 0,
    "PEPs Ongoing Monitoring": 0,
    "Stand Alone Screening": 0,
    "Lite Screening": 0,
    "Identity Document Verification": 0,
    "IAV": 0,
    "KYB - Summary Report": 50,
    "KYB - UBO": 50,
}


def test_annual_credits_legal():
    """Excel '2. Pricing Calc'!E6 = 52,800 for Legal."""
    credits = pricing.calculate_annual_credits(DEBENHAMS_INPUTS, "Legal")
    assert credits == 52800


def test_band_allocation():
    """Excel allocates 52,600 credits-to-purchase as [12k, 12k, 24k, 6k, 0]."""
    purchases = pricing.allocate_credits_to_bands(52600)
    assert purchases == [12000, 12000, 24000, 6000, 0]


def test_full_quote_legal():
    """Verify all three tier annual totals match the Excel output."""
    quote = pricing.build_quote(
        client_name="Debenhams Ottaway",
        vertical="Legal",
        monthly_volumes=DEBENHAMS_INPUTS,
    )

    # Excel says: Essentials 54,500, Compliance 68,400, Enterprise 103,800
    essentials, compliance, enterprise = quote.tiers

    assert essentials.tier_label == "Essentials"
    assert essentials.annual_total == 54500

    assert compliance.tier_label == "Compliance"
    assert compliance.annual_total == 68400

    assert enterprise.tier_label == "Enterprise"
    assert enterprise.annual_total == 103800


def test_tier_labels_per_vertical():
    """Middle tier is named differently per vertical."""
    legal_quote = pricing.build_quote("X", "Legal", DEBENHAMS_INPUTS)
    property_quote = pricing.build_quote("X", "Property", DEBENHAMS_INPUTS)
    accounting_quote = pricing.build_quote("X", "Accounting & FS", DEBENHAMS_INPUTS)

    assert legal_quote.tiers[1].tier_label == "Compliance"
    assert property_quote.tiers[1].tier_label == "Flow"
    assert accounting_quote.tiers[1].tier_label == "Risk"


def test_zero_volume_doesnt_break():
    """Edge case: client with zero volume should still produce a valid quote."""
    zero_inputs = {product: 0 for product in DEBENHAMS_INPUTS}
    quote = pricing.build_quote("Empty Co.", "Legal", zero_inputs)

    assert quote.annual_credits_required == 0
    # Should just be the base fees
    assert quote.tiers[0].annual_total == 2000   # Essentials Legal base
    assert quote.tiers[1].annual_total == 18000  # Compliance Legal base
    assert quote.tiers[2].annual_total == 60000  # Enterprise Legal base


# ---------------------------------------------------------------------------
# Free credits tests
# ---------------------------------------------------------------------------
def test_split_free_credits_examples():
    """Verify the upfront/monthly split matches the Excel FLOOR formula."""
    # 0 free → nothing to split
    assert pricing.split_free_credits(0) == (0, 0)

    # 100 free: 100/12 ≈ 8.3/mo, rounds down to 0/mo, so all 100 goes upfront
    assert pricing.split_free_credits(100) == (100, 0)

    # 240 free: exactly 20/mo, so all 240 goes monthly, none upfront
    assert pricing.split_free_credits(240) == (0, 240)

    # 250 free: 250/12 ≈ 20.8/mo, rounds down to 20/mo (=240 monthly), 10 upfront
    assert pricing.split_free_credits(250) == (10, 240)

    # 360 free: exactly 30/mo (=360 monthly), nothing upfront
    assert pricing.split_free_credits(360) == (0, 360)


def test_free_credits_reduce_purchase_amount():
    """Free credits should reduce the credits-to-purchase by their full amount."""
    free_by_tier = {"essentials": 0, "mid": 0, "enterprise": 1000}
    quote = pricing.build_quote(
        client_name="Discount Co.",
        vertical="Legal",
        monthly_volumes=DEBENHAMS_INPUTS,
        free_credits_by_tier=free_by_tier,
    )

    # Essentials/Compliance unchanged from original test
    assert quote.tiers[0].annual_total == 54500  # Essentials, no free
    assert quote.tiers[1].annual_total == 68400  # Compliance, no free

    # Enterprise: original credits_to_purchase was 50,800.
    # Now subtract 1,000 free → 49,800 to purchase.
    enterprise = quote.tiers[2]
    assert enterprise.free_credits == 1000
    assert enterprise.credits_to_purchase == 49800
    # Verify the upfront/monthly split for 1000 free
    assert enterprise.free_credits_monthly == 960   # 80/mo × 12
    assert enterprise.free_credits_upfront == 40


def test_free_credits_capped_when_exceeding_demand():
    """If included + free covers all demand, credits_to_purchase should be 0."""
    small_inputs = {product: 0 for product in DEBENHAMS_INPUTS}
    small_inputs["KYB - Summary Report"] = 1   # 1 × 5 × 12 = 60 credits/year

    quote = pricing.build_quote(
        "Tiny Co.",
        "Legal",
        small_inputs,
        free_credits_by_tier={"essentials": 5000, "mid": 0, "enterprise": 0},
    )
    essentials = quote.tiers[0]
    assert essentials.annual_credits_required == 60
    assert essentials.credits_to_purchase == 0   # included (200) + free (5000) > 60
    assert essentials.credit_cost == 0
    assert essentials.annual_total == 2000   # just the base fee
