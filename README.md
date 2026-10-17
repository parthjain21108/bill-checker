# Operations Assistant — British Gas template edition

This version is deliberately tuned for the four-page British Gas Business electricity bill format supplied for development. It is not marketed as a universal energy-bill parser.

## Features
- Multiple PDF uploads in one run; each file is parsed independently.
- Per-page text-layer detection and OCR for scanned pages.
- Multi-pass Tesseract OCR plus a focused right-column OCR pass for the tariff panel.
- Template-specific extraction of customer, site address, account number, meter ID, billing period, meter-reading usage, unit rate, standing charge and contract end date where legible.
- Cross-check of usage × unit rate against the billed energy charge.
- Missing consumption stays unknown rather than silently becoming zero.
- Editable fields, consumption review and PDF report export.

## Deploy to Streamlit Community Cloud
1. Upload the contents of this folder to your GitHub repository.
2. Ensure `packages.txt` and `.streamlit/config.toml` are included.
3. In Streamlit Community Cloud, select `app.py` as the entry point and deploy.
4. Test using copies of the supplied bill format and compare every extracted value with the source invoice.

## Important
This app uses OCR and deterministic parsing, not a trained machine-learning model. It is tuned to the supplied British Gas layout, but changes to the invoice template, poor scans, or OCR errors may still require review. Verify output before using it operationally.

The app runs on Streamlit Cloud when deployed there. Uploaded documents and extracted text are processed by the hosting environment; only upload client bills if your organisation has approved that processing.

## Requirements
Python dependencies are listed in `requirements.txt`. `packages.txt` installs the Tesseract OCR system package on Streamlit Community Cloud.
