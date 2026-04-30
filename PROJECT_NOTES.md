# Project Notes — Thirdfort Pricing Calculator (Python rebuild)

> **Purpose of this file:** captures the state of the project, key decisions, and what's next, so we can pick up cleanly across sessions. Update this file at the end of each working session.
>
> **For future Claude sessions:** paste the contents of this file into the chat (or upload it) at the start of a new conversation to restore project context.

---

## What this project is

A Python/Streamlit rebuild of Zane's Thirdfort pricing calculator, originally built as an n8n agent. It generates a 3-tier annual pricing quote based on a client's monthly check volumes and their vertical (Property / Legal / Accounting & FS).

Built primarily as a **learning project** — Zane is at a beginner level with Python and is using this to deepen his Python, n8n, and AI agent skills. The project doubles as a real tool for his AM work at Thirdfort.

---

## Current state (as of this session)

✅ **Phase 1 complete** — working Streamlit app with full pricing logic.

- Sidebar inputs: client name, vertical dropdown, 11 monthly check volumes, optional free credits per tier
- Main area: 3-tier comparison with annual total, monthly total, cost per credit, and an expandable breakdown
- All maths verified against the Excel source-of-truth (Debenhams Ottaway example reproduces exactly: Essentials £54,500 / Compliance £68,400 / Enterprise £103,800)

✅ **Phase 4 complete** — Looker CSV/XLSX upload for renewals.

- Renewal mode expander at the top of the main area
- Two file uploaders: completed checks (required) + ongoing monitoring (optional)
- Auto-detects partial months and defaults to excluding them
- Per-month checkboxes to override
- Mean/median toggle (defaults to mean)
- "Apply to inputs" button writes computed volumes via `st.session_state`
- New module `renewal.py` with pure parsing/computation functions

✅ **Phase 3 complete** — PDF proposal generation.

- New `pdf_export.py` module — pure function `build_pdf(quote, recommended_tier_key)`
- 4-page A4 PDF: Cover → How our pricing works → Platform Tiers → Recommended tier detail
- Thirdfort-branded: extracted exact colours (`#163D44` primary, `#D47059` accent) and logo from the proposal deck
- Lora (serif headers) + Poppins as a Red Hat Text substitute (bundled in `assets/fonts/`)
- Recommended tier selector in sidebar; that tier gets a coral border on the comparison page and a dedicated detail page
- Tested with the Birketts renewal data — produces a credible client-facing PDF
- 6 new tests covering generation, edge cases, and tier validation
- **27 tests passing total** (8 pricing + 11 renewal + 6 PDF + 2 mapping)

✅ **Running locally** — Zane has VS Code set up, venv created, Streamlit running on `http://localhost:8501`.

---

## Project structure

```
pricing-calculator/
├── app.py              ← Streamlit UI (the web interface)
├── pricing.py          ← Pure pricing functions (the brains)
├── renewal.py          ← Looker parsing + volume computation (Phase 4)
├── pdf_export.py       ← PDF proposal generation (Phase 3)
├── data.py             ← All pricing tables, base fees, credit costs
├── requirements.txt    ← Python libraries this project depends on
├── README.md           ← Setup and run instructions
├── PROJECT_NOTES.md    ← This file
├── .gitignore          ← Files git should ignore (e.g. venv/)
├── venv/               ← Virtual environment (do not commit, do not edit)
├── assets/
│   ├── thirdfort_logo.png        ← Dark logo for light backgrounds
│   ├── thirdfort_logo_white.png  ← White logo for dark backgrounds
│   └── fonts/
│       ├── Lora-*.ttf            ← Serif font for headers
│       ├── Poppins-*.ttf         ← Sans-serif body (Red Hat Text substitute)
│       └── README.md             ← How to swap to Red Hat Text
└── tests/
    ├── test_pricing.py    ← 8 tests verifying logic against Excel
    ├── test_renewal.py    ← 13 tests for Looker parsing and aggregation
    └── test_pdf_export.py ← 6 tests for PDF generation
```

**Key architectural principle:** clean separation between data (`data.py`), logic (`pricing.py`), and UI (`app.py`). When prices change, only `data.py` is touched. The pure-function design in `pricing.py` means the same logic could power a CLI, FastAPI backend, or batch script with no rewrites.

---

## Key design decisions made so far

1. **Pure functions in `pricing.py`** — no I/O, no side effects. Easy to test, easy to reuse.

2. **Internal tier keys vs display names** — code uses `essentials`/`mid`/`enterprise` everywhere; UI translates to vertical-specific labels (Property=Flow, Legal=Compliance, Accounting & FS=Risk) at the last possible moment via `data.TIER_DISPLAY_NAMES`.

3. **Bands as direct Python logic** — replaced Excel's clever 5,998-row pre-computed `Map` sheet with ~10 lines of band-filling logic. Same result, far simpler to reason about.

4. **Free credits as optional sweetener** — defaults to 0 across all tiers. When set, reduces credits-to-purchase and is split into upfront/monthly portions per the Excel formula. Note: free credits only reduce the *bill* when they push the calculation across a package boundary; otherwise they just give the client extra value at no cost change.

5. **Dataclasses for structured data** — `TierQuote` and `Quote` dataclasses give labelled fields rather than raw dicts. More readable, more debuggable, type-hinted.

6. **Skipped for now (flagged for later):**
   - Add-ons (Technical Onboarding, Technical Maintenance, Commercial SLA — each £20k/year per tier in the Excel)
   - Secure Share Rebate logic
   - "KYB - Other" (variable by jurisdiction in Excel)

---

## Roadmap (current order)

### Phase 3 — PDF generation ✅ DONE
A 4-page Thirdfort-branded PDF: Cover, How our pricing works, Platform Tiers comparison, and a detail page for the recommended tier. Generated by `pdf_export.build_pdf(quote, recommended_tier_key)`. Available via "Download PDF proposal" button after generating any quote.

**Things still possible to add later:**
- Add an AE contact details footer (currently no name on PDF — by user choice)
- A more elaborate cover image (currently uses abstract concentric arcs)
- Multi-tier detail pages (currently just the recommended one)
- Swap Poppins for the brand-correct Red Hat Text font (instructions in `assets/fonts/README.md`)

### Phase 4 — Looker CSV upload for renewals ✅ DONE
Drag-and-drop a Looker usage export onto the Streamlit app, automatically calculate avg monthly check volumes per product, pre-fill the calculator inputs, generate the renewal quote.

**Bonus features still possible to add:**
- Year-over-year trend visualisation
- Renewal vs current pricing comparison
- Anomaly flagging (e.g. "KYB UBO usage spiked 300% in October")
- Suggested vertical inference from product mix
- "Use most recent month" or "Use last 3 months" presets for OM
- Custom Looker → calculator product mapping in the UI (for clients with non-standard exports)
- Confirmation of the "Bank Info" mapping (currently ignored — likely IAV)

### Phase 2 (deferred) — AI extraction layer
LLM reads a free-text prospect description ("50-person legal firm doing 200 ID checks a month, KYB on every new corporate client") and populates the calculator inputs automatically. Likely Claude or Gemini via API.

### Phase 5 — Email delivery
SMTP via Python's built-in `smtplib`, or Resend/Postmark for a nicer API. Send the PDF quote to the prospect/client directly from the app.

### Phase 6 — Deployment
Dockerise and deploy to Zane's friend's server (n8n.shinyseekers.com), running alongside n8n. Likely behind a reverse proxy on a subdomain like `pricing.shinyseekers.com`.

---

## Pricing model — quick reference

**Inputs:**
- Client name (text)
- Vertical: Property / Legal / Accounting & FS
- Monthly volumes for 11 products: Enhanced NFC ID, Original ID, SoF, PEPs Ongoing Monitoring, Stand Alone Screening, Lite Screening, Identity Document Verification, IAV, KYB - Summary Report, KYB - UBO, Title Check
- Optional: free credits per tier (sales sweetener)

**Logic:**
1. Annual credits required = sum across products of (monthly_volume × credits_per_check × 12)
2. Credits to purchase = annual_credits - included_credits - free_credits
3. Allocate to 5 bands in order, rounding up to package boundaries within the band that runs out
4. Cost = sum of (credits in band × per-credit price for that tier)
5. Annual total = credit cost + base platform fee

**Tier base fees (annual, GBP):**
| Vertical          | Essentials | Mid (Flow/Compliance/Risk) | Enterprise |
|-------------------|------------|----------------------------|------------|
| Property          | 1,000      | 10,000                     | 60,000     |
| Legal             | 2,000      | 18,000                     | 60,000     |
| Accounting & FS   | 1,000      | 10,000                     | 60,000     |

**Included credits per tier:** Essentials 200, Mid 500, Enterprise 2,000.

**Bands:**
| Band | Range            | Package size | Essentials £/credit | Mid £/credit | Enterprise £/credit |
|------|------------------|--------------|---------------------|--------------|---------------------|
| 1    | 1–12,000         | 120          | 1.00                | 1.00         | 1.00                |
| 2    | 12,001–24,000    | 1,200        | 1.00                | 0.95         | 0.90                |
| 3    | 24,001–48,000    | 2,400        | 0.95                | 0.90         | 0.75                |
| 4    | 48,001–300,000   | 6,000        | 0.95                | 0.90         | 0.50                |
| 5    | 300,001+         | 12,000       | 0.90                | 0.75         | 0.45                |

**Source of truth:** original Excel file `Source_of_truth_pricing_calculator___for_agent_.xlsx`. Copy this into the project folder so it travels with the code.

---

## Daily workflow

Coming back to work on the project:

```bash
cd ~/Desktop/pricing_calculator_files/pricing-calculator   # adjust path
source venv/bin/activate
streamlit run app.py
```

Running tests:

```bash
python -m pytest tests/ -v
```

Stopping the app: `Ctrl+C` in the terminal.

---

## Personal/context notes

- **Zane's level:** beginner Python — comfortable with basic syntax, learning by doing. Strong at n8n, prompt engineering, and the underlying business model.
- **Learning style:** prefers conceptual explanations alongside concrete steps. Learns well during commute (mobile-friendly).
- **Role:** Account Manager at Thirdfort, London. Pipeline generation is the primary work challenge.
- **Existing infrastructure:** friend hosts n8n on n8n.shinyseekers.com — same server is the eventual deployment target for this app.
- **Already shipped at Thirdfort:** 2 production AI agents (Pricing Calculator Agent in n8n, Client Query Agent).

---

## Open questions / decisions pending

- [ ] Slides template — share with Claude to scope PDF design (Phase 3 blocker)
- [ ] Looker export — share an anonymised sample to scope the renewal upload (Phase 4 blocker)
- [ ] Add-ons (Technical Onboarding £20k, Maintenance £20k, SLA £20k per tier per year) — add when needed
- [ ] Cloud backup of project folder — drag into Google Drive/iCloud (recommended)
- [ ] Git + GitHub setup — proper version control, a future session task
- [ ] Decision on Slides match level: 3a only, or 3a → 3b polish phase

---

## Things to remember when picking up

1. The Streamlit auto-reload makes the dev loop incredibly fast — change a file, save, refresh browser. Use this aggressively when learning.
2. Always run `pytest` after changing `pricing.py` or `data.py` to catch regressions.
3. The free credits feature has a subtle behaviour worth re-explaining to anyone new: bonus credits don't always reduce the £ total — they only do when they push past a package boundary. The breakdown shows `credits_to_purchase` going down even when the total stays flat.
4. Excel formulas use `,` as 1000-separators in some places — be careful when porting new logic from the spreadsheet.
5. The Excel `Map` sheet's pre-computed cumulative rows are NOT replicated in Python — we use direct band-filling logic instead (cleaner, equivalent result).
