"""
pricing.py — The pure pricing logic.

"Pure" means: these functions take inputs and return outputs.
They don't read files, write to a database, call APIs, or print to screen.
That makes them:
  - Easy to test (just call the function and check the result).
  - Easy to reuse (the Streamlit UI uses them, but so could a CLI script
    or a FastAPI backend later).
  - Easy to reason about — you can understand each function in isolation.

This is the n8n equivalent of your "Code" nodes — but cleaner, because
you can split into multiple small functions and call them together.
"""

from dataclasses import dataclass
from typing import Dict, List

import data


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------
# A "dataclass" is just a class for holding data. Think of it as a labelled
# tuple — easier to read than a plain dict because the fields are named.
@dataclass
class TierQuote:
    """The complete quote for one tier (e.g. Essentials)."""
    tier_key: str               # "essentials" / "mid" / "enterprise"
    tier_label: str             # what to display: "Essentials" / "Compliance" / etc.
    annual_credits_required: int
    included_credits: int
    free_credits: int               # bonus credits given by sales (sweetener)
    free_credits_upfront: int       # of the free credits, this many given on day 1
    free_credits_monthly: int       # of the free credits, this many split monthly
    credits_to_purchase: int    # after subtracting included AND free credits
    package_adjusted_credits: int   # rounded up to package boundaries
    credit_cost: float          # cost of just the credits
    base_fee: float
    annual_total: float
    monthly_total: float
    cost_per_credit: float      # blended; useful sales metric
    purchases_by_band: List[int]   # how many credits bought in each band


@dataclass
class Quote:
    """The full quote: client info + all three tier options."""
    client_name: str
    vertical: str
    monthly_volumes: Dict[str, int]
    annual_credits_required: int
    tiers: List[TierQuote]      # always [essentials, mid, enterprise]


# ---------------------------------------------------------------------------
# Step 1: How many credits do they need each year?
# ---------------------------------------------------------------------------
def calculate_annual_credits(monthly_volumes: Dict[str, int], vertical: str) -> int:
    """
    Calculate total annual credits required across all products.

    monthly_volumes: dict like {"Enhanced NFC ID": 290, "KYB - UBO": 50, ...}
                     — how many of each check the client runs per month.
    vertical:        "Property", "Legal", or "Accounting & FS"
                     — affects credits-per-check for some products.
    """
    total = 0
    for product, monthly_count in monthly_volumes.items():
        credits_per_check = data.CREDITS_PER_CHECK[product][vertical]
        annual_credits_for_product = monthly_count * credits_per_check * 12
        total += annual_credits_for_product
    return total


# ---------------------------------------------------------------------------
# Step 2: How many credits do we need to buy from each band?
# ---------------------------------------------------------------------------
def allocate_credits_to_bands(credits_needed: int) -> List[int]:
    """
    Fill the bands in order and round up to the nearest package size
    in the band where demand runs out.

    Returns a list of 5 integers — credits purchased in each band.

    Example: needing 52,600 credits returns [12000, 12000, 24000, 6000, 0].
      - Band 1 fills (12,000), 40,600 still needed
      - Band 2 fills (12,000), 28,600 still needed
      - Band 3 fills (24,000), 4,600 still needed
      - Band 4 partially: 4,600 rounds up to 6,000 (the package size). Done.
      - Band 5: nothing needed.
    """
    purchases = []
    remaining = credits_needed

    for band in data.BANDS:
        if remaining <= 0:
            purchases.append(0)
            continue

        if remaining >= band["max_in_band"]:
            # Buy the whole band's capacity and move on.
            purchases.append(band["max_in_band"])
            remaining -= band["max_in_band"]
        else:
            # We finish in this band — round up to the next package.
            package = band["package"]
            # Ceiling division in Python: (a + b - 1) // b
            num_packages = (remaining + package - 1) // package
            purchases.append(num_packages * package)
            remaining = 0

    return purchases


# ---------------------------------------------------------------------------
# Step 3: What does it cost?
# ---------------------------------------------------------------------------
def calculate_credit_cost(purchases_by_band: List[int], tier_key: str) -> float:
    """Multiply credits in each band by the per-credit price for that tier."""
    total = 0.0
    for band, credits_bought in zip(data.BANDS, purchases_by_band):
        price_per_credit = band["prices"][tier_key]
        total += credits_bought * price_per_credit
    return total


# ---------------------------------------------------------------------------
# Step 3b: How are free credits split between upfront and monthly?
# ---------------------------------------------------------------------------
def split_free_credits(free_credits: int) -> tuple:
    """
    Free credits are split into two portions for the customer:
      - A monthly portion: the largest clean increment of 10/month.
      - An upfront portion: whatever's left over.

    This mirrors the Excel formula:  FLOOR(free / 12, 10) * 12
    Examples:
      100 free → 0 monthly, 100 upfront  (100/12 ≈ 8/mo, rounds down to 0)
      240 free → 240 monthly, 0 upfront  (240/12 = 20/mo, exact)
      250 free → 240 monthly, 10 upfront (250/12 ≈ 20.8/mo, rounds down to 20)

    Returns: (upfront, monthly_total)
    """
    if free_credits <= 0:
        return (0, 0)
    # Largest multiple of 10 that fits in (free_credits / 12).
    # // is integer division — drops the remainder.
    per_month = (free_credits // 12 // 10) * 10
    monthly_total = per_month * 12
    upfront = free_credits - monthly_total
    return (upfront, monthly_total)


# ---------------------------------------------------------------------------
# Putting it all together: build the quote for one tier
# ---------------------------------------------------------------------------
def build_tier_quote(
    annual_credits_required: int,
    vertical: str,
    tier_key: str,
    tier_label: str,
    free_credits: int = 0,
) -> TierQuote:
    """Run the full calculation for one tier and return a TierQuote.

    free_credits: bonus credits given by the salesperson (sweetener).
                  Reduces credits_to_purchase but costs nothing.
                  Defaults to 0 so existing callers don't break.
    """
    included = data.INCLUDED_CREDITS[tier_key]
    base_fee = data.BASE_FEES[vertical][tier_key]

    # Subtract included AND free credits from what the client needs.
    # max(..., 0) handles the edge case where included + free covers all demand.
    credits_to_purchase = max(annual_credits_required - included - free_credits, 0)

    purchases_by_band = allocate_credits_to_bands(credits_to_purchase)
    package_adjusted = sum(purchases_by_band)

    credit_cost = calculate_credit_cost(purchases_by_band, tier_key)
    annual_total = credit_cost + base_fee
    monthly_total = annual_total / 12

    # Blended cost per credit — handy sales metric. Guard against div by zero.
    # Note: includes free credits in the denominator since the client receives them.
    total_credits_in_quote = package_adjusted + included + free_credits
    if total_credits_in_quote > 0:
        cost_per_credit = credit_cost / total_credits_in_quote
    else:
        cost_per_credit = 0.0

    free_upfront, free_monthly = split_free_credits(free_credits)

    return TierQuote(
        tier_key=tier_key,
        tier_label=tier_label,
        annual_credits_required=annual_credits_required,
        included_credits=included,
        free_credits=free_credits,
        free_credits_upfront=free_upfront,
        free_credits_monthly=free_monthly,
        credits_to_purchase=credits_to_purchase,
        package_adjusted_credits=package_adjusted,
        credit_cost=credit_cost,
        base_fee=base_fee,
        annual_total=annual_total,
        monthly_total=monthly_total,
        cost_per_credit=cost_per_credit,
        purchases_by_band=purchases_by_band,
    )


# ---------------------------------------------------------------------------
# Top-level: build the full quote (all 3 tiers)
# ---------------------------------------------------------------------------
def build_quote(
    client_name: str,
    vertical: str,
    monthly_volumes: Dict[str, int],
    free_credits_by_tier: Dict[str, int] = None,
) -> Quote:
    """Build the complete quote a salesperson would present to a client.

    free_credits_by_tier: optional dict like {"essentials": 0, "mid": 250, "enterprise": 500}.
                          Lets the salesperson set different sweeteners per tier.
                          If None or missing keys, defaults to 0 for that tier.
    """
    annual_credits = calculate_annual_credits(monthly_volumes, vertical)
    tier_labels = data.TIER_DISPLAY_NAMES[vertical]

    # Default to no free credits if the caller didn't pass any.
    if free_credits_by_tier is None:
        free_credits_by_tier = {}

    tier_quotes = []
    for tier_key, tier_label in zip(data.TIER_KEYS, tier_labels):
        tier_quote = build_tier_quote(
            annual_credits_required=annual_credits,
            vertical=vertical,
            tier_key=tier_key,
            tier_label=tier_label,
            free_credits=free_credits_by_tier.get(tier_key, 0),
        )
        tier_quotes.append(tier_quote)

    return Quote(
        client_name=client_name,
        vertical=vertical,
        monthly_volumes=monthly_volumes,
        annual_credits_required=annual_credits,
        tiers=tier_quotes,
    )
