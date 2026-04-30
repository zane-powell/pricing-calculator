# Thirdfort Pricing Calculator (Python / Streamlit)

A Python rebuild of the n8n pricing agent. Generates a 3-tier annual quote
based on a client's monthly check volumes and chosen vertical.

## What's in here

```
pricing-calculator/
├── app.py              ← Streamlit UI (the web interface)
├── pricing.py          ← Pure pricing functions (the brains)
├── data.py             ← All pricing tables, base fees, credit costs
├── requirements.txt    ← Python libraries this project depends on
├── README.md           ← This file
├── .gitignore          ← Files git should ignore
└── tests/
    └── test_pricing.py ← Verifies the logic against the Excel "source of truth"
```

The split matters: `data.py` is config, `pricing.py` is logic, `app.py` is UI.
When prices change you only touch `data.py`. When you want to add a CLI
or an API, you only touch the UI layer — the logic stays unchanged.

## Setup (one time)

You'll need Python 3.10 or newer installed.

```bash
# 1. Create a virtual environment (an isolated Python install for this project)
python3 -m venv venv

# 2. Activate it
#    macOS/Linux:
source venv/bin/activate
#    Windows (PowerShell):
venv\Scripts\Activate.ps1

# 3. Install the dependencies
pip install -r requirements.txt
```

A virtual environment keeps this project's libraries separate from your
system Python — so installing/upgrading things here can never break
something else on your machine.

## Running the app

```bash
streamlit run app.py
```

Streamlit will print a local URL (usually `http://localhost:8501`) and
auto-open your browser. The page hot-reloads when you save changes to
any `.py` file — great for tinkering.

## Running the tests

```bash
python -m pytest tests/ -v
```

You should see all 5 tests pass. If you ever change the pricing logic
and a test goes red, you've broken something — fix it before continuing.

## What this project is teaching you

- **Project structure** — splitting code into modules by responsibility
- **Pure functions** — `pricing.py` is testable because it has no side effects
- **Type hints & dataclasses** — modern Python conventions worth adopting early
- **Testing** — pytest, asserting expected outputs, edge cases
- **Streamlit** — building interactive UIs in pure Python

## Roadmap (where to go next)

- **Phase 2** — Add the AI reasoning layer (Gemini or Claude). Let the
  user describe their needs in plain English and have the LLM populate
  the inputs.
- **Phase 3** — Persist quotes to SQLite, generate a PDF output with
  `reportlab` or `weasyprint`.
- **Phase 4** — Email delivery via SMTP or Resend, error handling, logging.
- **Phase 5** — Dockerise and deploy to your friend's server alongside n8n.
