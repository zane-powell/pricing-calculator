"""
pdf_export.py — Generate a Thirdfort-branded pricing proposal PDF.

Pure module like pricing.py and renewal.py — takes a Quote and returns PDF bytes.
No Streamlit, no I/O. The Streamlit layer wraps this with a download button.

Document structure (4 pages):
  1. Cover — dark teal, client name, big white title, decorative arcs motif
  2. How our pricing works — two cards explaining platform fee + credits
  3. Our Platform Tiers — three teal cards comparing tiers
  4. Recommended tier detail — products table + pricing summary

Brand assets are loaded from the assets/ folder relative to this file.
Fonts gracefully fall back to Helvetica if not present.

To swap in the brand-correct Red Hat Text font, see assets/fonts/README.md.
"""

import io
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import pricing


# ---------------------------------------------------------------------------
# Brand constants — extracted from the Thirdfort proposal deck
# ---------------------------------------------------------------------------
PRIMARY_DARK = HexColor("#163D44")     # cover, tier cards
ACCENT_TERRACOTTA = HexColor("#D47059") # decorative + accent
ACCENT_CORAL = HexColor("#F09E8A")     # softer accent
TEXT_DARK = HexColor("#313131")        # body text on light bg
TEXT_MUTED = HexColor("#6E6E6E")       # captions, footers
BG_NEUTRAL = HexColor("#ECEDE9")       # warm off-white background
CARD_BG_LIGHT = HexColor("#F7F5F0")    # explainer card background
RULE_LIGHT = HexColor("#E5E2DC")       # subtle dividers


# ---------------------------------------------------------------------------
# Font registration — loads the bundled fonts, falls back to Helvetica
# ---------------------------------------------------------------------------
ASSETS_DIR = Path(__file__).parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

# Will be populated by _register_fonts() — names used throughout this file.
HEADER_FONT = "Helvetica-Bold"          # default fallback
HEADER_FONT_LIGHT = "Helvetica"
BODY_FONT = "Helvetica"
BODY_FONT_BOLD = "Helvetica-Bold"
BODY_FONT_MEDIUM = "Helvetica-Bold"


def _register_fonts() -> None:
    """Try to load custom fonts; gracefully fall back to Helvetica.

    Called once on module import. Modifies the global font name constants
    so the rest of this module can just reference them by name.
    """
    global HEADER_FONT, HEADER_FONT_LIGHT
    global BODY_FONT, BODY_FONT_BOLD, BODY_FONT_MEDIUM

    # Map of (font_name_we'll_use, candidate_files_to_try)
    # We try multiple filenames so this works whether someone has the
    # static TTFs (Lora-Bold.ttf, RedHatText-Regular.ttf etc.) or the
    # variable fonts (Lora-Variable.ttf).
    candidates = {
        "Lora": ["Lora-Bold.ttf", "Lora-Variable.ttf", "Lora-Regular.ttf"],
        "LoraLight": ["Lora-Regular.ttf", "Lora-Variable.ttf"],
        "Body": ["RedHatText-Regular.ttf", "Poppins-Regular.ttf"],
        "BodyBold": ["RedHatText-Bold.ttf", "Poppins-Bold.ttf"],
        "BodyMedium": ["RedHatText-Medium.ttf", "Poppins-Medium.ttf"],
    }

    registered = {}
    for font_name, files in candidates.items():
        for filename in files:
            path = FONTS_DIR / filename
            if path.exists():
                try:
                    pdfmetrics.registerFont(TTFont(font_name, str(path)))
                    registered[font_name] = True
                    break
                except Exception:
                    continue

    # Promote to globals only if registration succeeded — otherwise
    # the Helvetica defaults stay in place.
    if "Lora" in registered:
        HEADER_FONT = "Lora"
    if "LoraLight" in registered:
        HEADER_FONT_LIGHT = "LoraLight"
    if "Body" in registered:
        BODY_FONT = "Body"
    if "BodyBold" in registered:
        BODY_FONT_BOLD = "BodyBold"
    if "BodyMedium" in registered:
        BODY_FONT_MEDIUM = "BodyMedium"


_register_fonts()


# ---------------------------------------------------------------------------
# Layout constants — A4 page is 210mm × 297mm
# ---------------------------------------------------------------------------
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _draw_logo(c: canvas.Canvas, x: float, y: float, height: float, white_version: bool) -> None:
    """Place the Thirdfort logo at (x, y) with the given height."""
    filename = "thirdfort_logo_white.png" if white_version else "thirdfort_logo.png"
    logo_path = ASSETS_DIR / filename
    if not logo_path.exists():
        return
    # The logo is wider than tall (roughly 4.5:1 for the dark version, including text).
    # Preserve aspect ratio.
    c.drawImage(
        str(logo_path),
        x, y,
        height=height,
        preserveAspectRatio=True,
        anchor="sw",      # x,y is the south-west corner of the bounding box
        mask="auto",      # respect PNG alpha
    )


def _draw_page_footer(c: canvas.Canvas, page_number: int, total_pages: int) -> None:
    """Small Thirdfort logo bottom-left + page number bottom-right."""
    _draw_logo(c, MARGIN, 10 * mm, height=5 * mm, white_version=False)
    c.setFont(BODY_FONT, 9)
    c.setFillColor(TEXT_MUTED)
    c.drawRightString(
        PAGE_WIDTH - MARGIN, 12 * mm,
        f"{page_number} / {total_pages}",
    )


def _wrap_text(text: str, width: float, font: str, font_size: float) -> list:
    """Naive word-wrap: returns a list of lines that each fit within `width`."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if pdfmetrics.stringWidth(candidate, font, font_size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# PAGE 1: Cover
# ---------------------------------------------------------------------------
def _draw_cover(c: canvas.Canvas, client_name: str, generation_date: date) -> None:
    """Dark teal cover with creative arc motif in the bottom-right corner."""
    # Full-bleed dark teal background
    c.setFillColor(PRIMARY_DARK)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

    # --- Decorative arc motif (bottom-right corner) -----------------------
    # Concentric quarter-circles in brand accent colours — a subtle nod
    # to the original deck's circular motif but more abstract.
    cx = PAGE_WIDTH + 20 * mm    # centre is off the page bottom-right
    cy = -20 * mm
    arc_colours = [
        (ACCENT_TERRACOTTA, 200 * mm),
        (ACCENT_CORAL, 160 * mm),
        (HexColor("#E89478"), 120 * mm),
        (PRIMARY_DARK, 80 * mm),       # inner one same as bg
    ]
    for colour, radius in arc_colours:
        c.setFillColor(colour)
        c.circle(cx, cy, radius, fill=1, stroke=0)

    # --- Logo (white version) ---------------------------------------------
    _draw_logo(c, MARGIN, PAGE_HEIGHT - MARGIN - 12 * mm, height=12 * mm, white_version=True)

    # --- Title block ------------------------------------------------------
    c.setFillColor(white)

    # Small "PRICING PROPOSAL" eyebrow
    c.setFont(BODY_FONT_MEDIUM, 11)
    c.drawString(MARGIN, PAGE_HEIGHT / 2 + 18 * mm, "PRICING PROPOSAL")

    # Big client name title — uses serif header font for elegance
    c.setFont(HEADER_FONT, 38)
    title_y = PAGE_HEIGHT / 2
    # Word-wrap the client name in case it's long
    title_lines = _wrap_text(client_name, CONTENT_WIDTH * 0.7, HEADER_FONT, 38)
    for line in title_lines:
        c.drawString(MARGIN, title_y, line)
        title_y -= 14 * mm

    # --- Date in bottom-left ----------------------------------------------
    c.setFont(BODY_FONT, 11)
    c.setFillColor(white)
    c.drawString(MARGIN, MARGIN + 5 * mm, generation_date.strftime("%d %B %Y"))


# ---------------------------------------------------------------------------
# PAGE 2: How our pricing works
# ---------------------------------------------------------------------------
def _draw_how_pricing_works(c: canvas.Canvas, page_number: int, total_pages: int) -> None:
    """Two large cards: Platform fee + Credits."""
    # White background (default — no need to fill)

    # --- Title (large serif, two-line) ------------------------------------
    c.setFillColor(PRIMARY_DARK)
    c.setFont(HEADER_FONT, 40)
    c.drawString(MARGIN, PAGE_HEIGHT - 50 * mm, "How our")
    c.drawString(MARGIN, PAGE_HEIGHT - 65 * mm, "pricing works")

    # --- Two cards side-by-side -------------------------------------------
    card_top = PAGE_HEIGHT - 90 * mm
    card_height = 130 * mm
    card_gap = 8 * mm
    card_width = (CONTENT_WIDTH - card_gap) / 2

    # Card 1 — Platform fee (dark teal)
    c.setFillColor(PRIMARY_DARK)
    c.roundRect(
        MARGIN, card_top - card_height,
        card_width, card_height,
        radius=6 * mm, fill=1, stroke=0,
    )

    # Big "1." numeral
    c.setFillColor(white)
    c.setFont(HEADER_FONT, 64)
    c.drawString(MARGIN + 10 * mm, card_top - 30 * mm, "1.")

    # Card title
    c.setFont(BODY_FONT_BOLD, 18)
    c.drawString(MARGIN + 10 * mm, card_top - 55 * mm, "Platform fee")

    # Card body text — wrapped
    body = (
        "A monthly fee that covers access to the platform for your users, "
        "ongoing software updates, onboarding, access to our client and "
        "consumer support teams, as well as retention of your client data."
    )
    c.setFont(BODY_FONT, 11)
    c.setFillColor(white)
    body_y = card_top - 70 * mm
    for line in _wrap_text(body, card_width - 20 * mm, BODY_FONT, 11):
        c.drawString(MARGIN + 10 * mm, body_y, line)
        body_y -= 5.5 * mm

    # Card 2 — Credits (warm cream/beige)
    card2_x = MARGIN + card_width + card_gap
    c.setFillColor(BG_NEUTRAL)
    c.roundRect(
        card2_x, card_top - card_height,
        card_width, card_height,
        radius=6 * mm, fill=1, stroke=0,
    )

    c.setFillColor(PRIMARY_DARK)
    c.setFont(HEADER_FONT, 64)
    c.drawString(card2_x + 10 * mm, card_top - 30 * mm, "2.")

    c.setFont(BODY_FONT_BOLD, 18)
    c.setFillColor(PRIMARY_DARK)
    c.drawString(card2_x + 10 * mm, card_top - 55 * mm, "Credits")

    body2 = (
        "Credits are what you'll use to pay for individual checks. "
        "Different check types consume different numbers of credits — "
        "for example, an Enhanced NFC ID check costs 10 credits, while "
        "an ongoing monitoring check costs 1 credit. Buying credits in "
        "bulk reduces the cost per credit."
    )
    c.setFont(BODY_FONT, 11)
    c.setFillColor(TEXT_DARK)
    body_y = card_top - 70 * mm
    for line in _wrap_text(body2, card_width - 20 * mm, BODY_FONT, 11):
        c.drawString(card2_x + 10 * mm, body_y, line)
        body_y -= 5.5 * mm

    _draw_page_footer(c, page_number, total_pages)


# ---------------------------------------------------------------------------
# PAGE 3: Platform Tiers comparison
# ---------------------------------------------------------------------------
# Tier feature lists — these mirror the Thirdfort proposal deck's content
TIER_FEATURES = {
    "essentials": [
        "ID checks",
        "Source of Funds",
        "AML checks",
        "KYB checks",
        "Title documents",
    ],
    "mid": [
        "Everything in Essentials, plus…",
        "API access",
        "AML screening configs",
        "Approval flows",
        "Bulk uploads",
        "Bespoke training",
        "Reporting (usage, billing, risk)",
    ],
    "enterprise": [
        "Everything in Compliance/Flow, plus…",
        "Roles & permissions settings",
        "SSO",
        "Customisable reporting",
        "Customisable KYB / KYC",
    ],
}


def _draw_platform_tiers(
    c: canvas.Canvas,
    quote: pricing.Quote,
    recommended_tier_key: str,
    page_number: int,
    total_pages: int,
) -> None:
    """Three tier cards side-by-side. The recommended one is highlighted."""

    # Title
    c.setFillColor(PRIMARY_DARK)
    c.setFont(HEADER_FONT, 32)
    c.drawString(MARGIN, PAGE_HEIGHT - 35 * mm, "Our Platform Tiers")

    # Subtitle
    c.setFillColor(TEXT_MUTED)
    c.setFont(BODY_FONT, 11)
    c.drawString(
        MARGIN, PAGE_HEIGHT - 43 * mm,
        f"Three tiers tailored for {quote.vertical}.",
    )

    # --- Three cards ------------------------------------------------------
    card_top = PAGE_HEIGHT - 55 * mm
    card_height = 195 * mm
    card_gap = 5 * mm
    card_width = (CONTENT_WIDTH - 2 * card_gap) / 3

    for index, tier in enumerate(quote.tiers):
        x = MARGIN + index * (card_width + card_gap)
        is_recommended = (tier.tier_key == recommended_tier_key)

        # Card background — recommended one gets a coral accent border
        if is_recommended:
            # Outer accent border (4px)
            c.setFillColor(ACCENT_TERRACOTTA)
            c.roundRect(
                x - 1 * mm, card_top - card_height - 1 * mm,
                card_width + 2 * mm, card_height + 2 * mm,
                radius=6 * mm, fill=1, stroke=0,
            )

        c.setFillColor(PRIMARY_DARK)
        c.roundRect(
            x, card_top - card_height,
            card_width, card_height,
            radius=5 * mm, fill=1, stroke=0,
        )

        # Big numeral
        c.setFillColor(white)
        c.setFont(HEADER_FONT, 48)
        c.drawString(x + 10 * mm, card_top - 22 * mm, f"{index + 1}.")

        # "RECOMMENDED" badge
        if is_recommended:
            c.setFillColor(ACCENT_TERRACOTTA)
            c.roundRect(
                x + 10 * mm, card_top - 32 * mm,
                40 * mm, 6 * mm,
                radius=2 * mm, fill=1, stroke=0,
            )
            c.setFillColor(white)
            c.setFont(BODY_FONT_BOLD, 8)
            c.drawString(x + 13 * mm, card_top - 30.5 * mm, "RECOMMENDED")

        # Tier name + annual total (using actual quote, not just base fee)
        c.setFillColor(white)
        c.setFont(BODY_FONT_BOLD, 16)
        y_offset = 45 if is_recommended else 38
        c.drawString(x + 10 * mm, card_top - y_offset * mm, tier.tier_label)

        # Annual total — what this client would actually pay
        c.setFont(BODY_FONT_BOLD, 13)
        y_offset += 7
        c.drawString(
            x + 10 * mm, card_top - y_offset * mm,
            f"£{tier.annual_total:,.0f}/year",
        )

        # Monthly equivalent — softer colour
        c.setFillColor(HexColor("#9DBEC4"))
        c.setFont(BODY_FONT, 9)
        y_offset += 5
        c.drawString(
            x + 10 * mm, card_top - y_offset * mm,
            f"£{tier.monthly_total:,.0f}/month",
        )

        # Divider line
        y_offset += 6
        c.setStrokeColor(HexColor("#2A5560"))
        c.setLineWidth(0.5)
        c.line(
            x + 10 * mm, card_top - y_offset * mm,
            x + card_width - 10 * mm, card_top - y_offset * mm,
        )

        # Feature list
        y_offset += 6
        features = TIER_FEATURES[tier.tier_key]
        c.setFont(BODY_FONT, 10)
        c.setFillColor(white)
        for feature in features:
            # First feature is sometimes the inheritance line — render lighter
            is_inheritance = feature.startswith("Everything")
            if is_inheritance:
                c.setFillColor(HexColor("#B4D4DA"))
                c.setFont(BODY_FONT, 9)
            else:
                c.setFillColor(white)
                c.setFont(BODY_FONT, 10)

            wrapped = _wrap_text(feature, card_width - 20 * mm, BODY_FONT, 10)
            for line in wrapped:
                if y_offset > card_height - 10:
                    break  # don't overflow card
                c.drawString(x + 10 * mm, card_top - y_offset * mm, line)
                y_offset += 5

            y_offset += 1  # small gap between features

    _draw_page_footer(c, page_number, total_pages)


# ---------------------------------------------------------------------------
# PAGE 4: Recommended tier pricing detail
# ---------------------------------------------------------------------------
def _draw_pricing_detail(
    c: canvas.Canvas,
    quote: pricing.Quote,
    recommended_tier: pricing.TierQuote,
    page_number: int,
    total_pages: int,
) -> None:
    """Detail page for the recommended tier — two tables side by side."""

    # Title
    c.setFillColor(PRIMARY_DARK)
    c.setFont(HEADER_FONT, 28)
    c.drawString(
        MARGIN, PAGE_HEIGHT - 35 * mm,
        f"{quote.client_name} — {recommended_tier.tier_label}",
    )

    c.setFillColor(TEXT_MUTED)
    c.setFont(BODY_FONT, 11)
    c.drawString(
        MARGIN, PAGE_HEIGHT - 43 * mm,
        "Annual pricing breakdown",
    )

    # --- Two tables side-by-side ------------------------------------------
    table_top = PAGE_HEIGHT - 60 * mm
    table_gap = 8 * mm
    left_width = CONTENT_WIDTH * 0.55
    right_width = CONTENT_WIDTH - left_width - table_gap

    # === LEFT TABLE: products and volumes ================================
    left_x = MARGIN

    # Header row
    c.setFillColor(PRIMARY_DARK)
    c.rect(left_x, table_top - 10 * mm, left_width, 10 * mm, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont(BODY_FONT_BOLD, 10)
    c.drawString(left_x + 4 * mm, table_top - 6.5 * mm, "Check type")
    c.drawRightString(
        left_x + left_width - 4 * mm, table_top - 6.5 * mm,
        "Annual checks",
    )

    # Body rows — only show products with non-zero volume
    nonzero_products = {
        product: volume for product, volume in quote.monthly_volumes.items()
        if volume > 0
    }

    row_height = 8 * mm
    y = table_top - 10 * mm
    c.setFillColor(TEXT_DARK)
    c.setFont(BODY_FONT, 10)
    row_index = 0

    for product, monthly_volume in nonzero_products.items():
        annual_volume = monthly_volume * 12
        # Zebra striping for readability
        if row_index % 2 == 1:
            c.setFillColor(BG_NEUTRAL)
            c.rect(left_x, y - row_height, left_width, row_height, fill=1, stroke=0)
            c.setFillColor(TEXT_DARK)

        c.setFont(BODY_FONT, 10)
        # Wrap long product names
        max_text_w = left_width - 30 * mm
        wrapped = _wrap_text(product, max_text_w, BODY_FONT, 10)
        # For simplicity put on one line, truncate if needed
        line = wrapped[0] if wrapped else product
        if len(wrapped) > 1:
            line = wrapped[0] + "…"
        c.drawString(left_x + 4 * mm, y - 5.5 * mm, line)

        c.setFont(BODY_FONT_MEDIUM, 10)
        c.drawRightString(
            left_x + left_width - 4 * mm, y - 5.5 * mm,
            f"{annual_volume:,}",
        )

        y -= row_height
        row_index += 1

    # Border around the whole left table
    c.setStrokeColor(RULE_LIGHT)
    c.setLineWidth(0.5)
    c.rect(left_x, y, left_width, table_top - y, fill=0, stroke=1)

    # === RIGHT TABLE: pricing summary ====================================
    right_x = MARGIN + left_width + table_gap

    # Header row (matches left table)
    c.setFillColor(PRIMARY_DARK)
    c.rect(right_x, table_top - 10 * mm, right_width, 10 * mm, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont(BODY_FONT_BOLD, 11)
    c.drawCentredString(
        right_x + right_width / 2, table_top - 6.5 * mm,
        recommended_tier.tier_label,
    )

    # Pricing rows
    pricing_rows = [
        ("Annual credits required", f"{recommended_tier.annual_credits_required:,}"),
        ("Credits to purchase", f"{recommended_tier.package_adjusted_credits:,}"),
        ("Free credits", f"{recommended_tier.included_credits + recommended_tier.free_credits:,}"),
        ("Cost per credit", f"£{recommended_tier.cost_per_credit:.3f}"),
        ("Annual platform fee", f"£{recommended_tier.base_fee:,.0f}"),
    ]

    y = table_top - 10 * mm
    row_index = 0
    for label, value in pricing_rows:
        if row_index % 2 == 1:
            c.setFillColor(BG_NEUTRAL)
            c.rect(right_x, y - row_height, right_width, row_height, fill=1, stroke=0)

        c.setFillColor(TEXT_DARK)
        c.setFont(BODY_FONT, 10)
        c.drawString(right_x + 4 * mm, y - 5.5 * mm, label)
        c.setFont(BODY_FONT_BOLD, 10)
        c.drawRightString(right_x + right_width - 4 * mm, y - 5.5 * mm, value)

        y -= row_height
        row_index += 1

    # --- Highlighted total row ---
    total_box_height = 18 * mm
    c.setFillColor(PRIMARY_DARK)
    c.rect(right_x, y - total_box_height, right_width, total_box_height, fill=1, stroke=0)

    # Label on top line
    c.setFillColor(HexColor("#9DBEC4"))   # lighter so it doesn't compete
    c.setFont(BODY_FONT_BOLD, 9)
    c.drawString(right_x + 4 * mm, y - 6 * mm, "ANNUAL / MONTHLY SPEND (EX VAT)")

    # Big number on its own line below the label
    c.setFillColor(white)
    c.setFont(BODY_FONT_BOLD, 16)
    c.drawRightString(
        right_x + right_width - 4 * mm, y - 13.5 * mm,
        f"£{recommended_tier.annual_total:,.0f} / £{recommended_tier.monthly_total:,.0f}",
    )

    y -= total_box_height

    # Border around the whole right table
    c.setStrokeColor(RULE_LIGHT)
    c.setLineWidth(0.5)
    c.rect(right_x, y, right_width, table_top - y, fill=0, stroke=1)

    # --- Footnote ---------------------------------------------------------
    c.setFillColor(TEXT_MUTED)
    c.setFont(BODY_FONT, 9)
    c.drawString(
        MARGIN, MARGIN + 22 * mm,
        "*Includes access to our API. Does not include retrospective checks.",
    )
    c.drawString(
        MARGIN, MARGIN + 18 * mm,
        "Pricing valid for 30 days from the date on the cover page.",
    )

    _draw_page_footer(c, page_number, total_pages)


# ---------------------------------------------------------------------------
# Top-level: build the full PDF
# ---------------------------------------------------------------------------
def build_pdf(
    quote: pricing.Quote,
    recommended_tier_key: str,
    generation_date: Optional[date] = None,
) -> bytes:
    """
    Build the complete pricing proposal PDF and return its bytes.

    quote:                   the pricing.Quote produced by pricing.build_quote()
    recommended_tier_key:    "essentials" / "mid" / "enterprise" — which tier
                             to highlight and detail
    generation_date:         date to print on the cover; defaults to today

    Returns the PDF as raw bytes — caller can write to disk, send over network,
    or hand to Streamlit's st.download_button().
    """
    # Find the recommended tier in the quote
    recommended_tier = next(
        (t for t in quote.tiers if t.tier_key == recommended_tier_key),
        None,
    )
    if recommended_tier is None:
        raise ValueError(
            f"recommended_tier_key={recommended_tier_key!r} not found in quote"
        )

    if generation_date is None:
        generation_date = date.today()

    # In-memory buffer — avoids writing to disk
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    # Set PDF metadata
    c.setTitle(f"{quote.client_name} - Pricing Proposal")
    c.setAuthor("Thirdfort")
    c.setSubject(f"Pricing proposal for {quote.client_name}")

    total_pages = 4

    # PAGE 1 — Cover
    _draw_cover(c, quote.client_name, generation_date)
    c.showPage()

    # PAGE 2 — How our pricing works
    _draw_how_pricing_works(c, page_number=2, total_pages=total_pages)
    c.showPage()

    # PAGE 3 — Platform Tiers
    _draw_platform_tiers(
        c, quote, recommended_tier_key,
        page_number=3, total_pages=total_pages,
    )
    c.showPage()

    # PAGE 4 — Recommended tier detail
    _draw_pricing_detail(
        c, quote, recommended_tier,
        page_number=4, total_pages=total_pages,
    )
    c.showPage()

    c.save()
    return buffer.getvalue()
