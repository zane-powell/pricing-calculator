"""
test_pdf_export.py — Verifies the PDF generator produces valid output.

We don't try to validate visual layout in tests (that's what eyeballs are for),
but we DO verify:
  - The function runs without error
  - The output is non-empty bytes
  - The output starts with the PDF magic header (b'%PDF-')
  - All three tier_key values work as the recommended tier
  - It handles edge cases (zero volumes, very long client names)
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdf_export
import pricing


def make_test_quote() -> pricing.Quote:
    """A small valid quote for testing."""
    return pricing.build_quote(
        client_name="Test Co",
        vertical="Legal",
        monthly_volumes={
            "Enhanced NFC ID": 100,
            "Original ID": 50,
            "SoF": 20,
            "PEPs Ongoing Monitoring": 0,
            "Stand Alone Screening": 0,
            "Lite Screening": 0,
            "Identity Document Verification": 0,
            "IAV": 0,
            "KYB - Summary Report": 10,
            "KYB - UBO": 5,
            "Title Check": 0,
        },
    )


def test_pdf_is_generated():
    """The function should return non-empty bytes."""
    quote = make_test_quote()
    pdf_bytes = pdf_export.build_pdf(quote, recommended_tier_key="mid")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000  # a real PDF is at least a few KB


def test_pdf_has_correct_magic_header():
    """Verify the output is actually a valid PDF file (starts with %PDF-)."""
    quote = make_test_quote()
    pdf_bytes = pdf_export.build_pdf(quote, recommended_tier_key="essentials")
    assert pdf_bytes.startswith(b"%PDF-")


def test_all_three_tiers_can_be_recommended():
    """Every valid tier_key should produce a valid PDF when set as recommended."""
    quote = make_test_quote()
    for tier_key in ("essentials", "mid", "enterprise"):
        pdf_bytes = pdf_export.build_pdf(quote, recommended_tier_key=tier_key)
        assert pdf_bytes.startswith(b"%PDF-"), f"failed for {tier_key}"


def test_invalid_recommended_tier_raises():
    """An unknown tier key should raise ValueError."""
    quote = make_test_quote()
    with pytest.raises(ValueError):
        pdf_export.build_pdf(quote, recommended_tier_key="platinum")


def test_zero_volume_quote_still_generates():
    """Edge case: a quote with all-zero volumes should still produce a PDF."""
    quote = pricing.build_quote(
        client_name="Empty Co",
        vertical="Property",
        monthly_volumes={p: 0 for p in [
            "Enhanced NFC ID", "Original ID", "SoF",
            "PEPs Ongoing Monitoring", "Stand Alone Screening", "Lite Screening",
            "Identity Document Verification", "IAV",
            "KYB - Summary Report", "KYB - UBO", "Title Check",
        ]},
    )
    pdf_bytes = pdf_export.build_pdf(quote, recommended_tier_key="essentials")
    assert pdf_bytes.startswith(b"%PDF-")


def test_long_client_name_doesnt_crash():
    """Edge case: very long client names shouldn't break the layout code."""
    quote = pricing.build_quote(
        client_name="A Very Long Solicitors LLP & Associates Worldwide Ltd",
        vertical="Legal",
        monthly_volumes={p: 10 for p in [
            "Enhanced NFC ID", "Original ID", "SoF",
            "PEPs Ongoing Monitoring", "Stand Alone Screening", "Lite Screening",
            "Identity Document Verification", "IAV",
            "KYB - Summary Report", "KYB - UBO", "Title Check",
        ]},
    )
    pdf_bytes = pdf_export.build_pdf(quote, recommended_tier_key="enterprise")
    assert pdf_bytes.startswith(b"%PDF-")
