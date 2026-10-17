# Operations Assistant — Streamlit Cloud

A review-first UK commercial energy-bill extraction and reporting app. Upload bills, inspect extracted fields, edit corrections, review consumption by register, calculate annualised usage, and export a PDF report.

## Deploy to Streamlit Community Cloud
1. Create a GitHub repository and upload the contents of this folder (including `.streamlit/config.toml` and `packages.txt`).
2. Open https://share.streamlit.io/ and connect the repository.
3. Set the main file path to `app.py` and deploy.
4. Wait for the first build to install Python packages and Tesseract OCR from `packages.txt`.

## What it does
- Extracts PDF text with PyMuPDF and falls back to Tesseract OCR for scanned/image PDFs.
- Uses deterministic, supplier-aware parsing and shows source text/evidence for review.
- Keeps Day, Night, Evening & Weekend, other registers, and single-rate usage separate.
- Calculates annualised usage as `total consumption ÷ total billed days × 365` and average monthly usage as annualised usage ÷ 12.
- Produces a formatted PDF report with supply details, consumption, calculations and review flags.
- Missing values are flagged rather than silently replaced with guessed values.

## Important limitations
- This is not a certified billing system and cannot guarantee 100% extraction accuracy. Supplier layouts differ and PDFs may have OCR/layout issues. Always verify critical values against the source invoice.
- It does not call ChatGPT or an external AI API. Parsing is rules-based; unsupported layouts may require manual correction.
- Streamlit Community Cloud processes uploaded files in the hosted app environment. A private GitHub repository does **not** make the deployed app private. Do not upload confidential client bills unless your organisation has explicitly approved cloud processing.
- Uploaded files are handled in the running app session. Do not treat this as a compliant records-management system.

## Local run
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```
For OCR locally, install Tesseract OCR using your operating system's package manager.

## Parser regression tests
Run the included sanitised tests with:
```bash
python -m unittest discover -s tests -v
```
