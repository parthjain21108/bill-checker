# Operations Assistant — Local Streamlit App

## What it does
- Runs on your Mac in a browser at `http://127.0.0.1:8501`.
- Reads text from PDFs locally; attempts local OCR for scanned PDFs and image bills.
- Helps organise supply identifiers, CED, unit/standing rates and consumption.
- Lets you review/correct extracted fields and enter billing days and separate Day, Night and Evening & Weekend registers.
- Calculates total, average per bill and annualised consumption using: `total kWh ÷ total billed days × 365`.
- Creates a downloadable PDF summary.

## Privacy model
This app does not call ChatGPT, OpenAI, or any external AI API. Bill processing, text extraction, calculations and PDF creation happen locally on your Mac. Streamlit is configured to disable usage-stat collection and bind to `127.0.0.1` only. Do not change the server address to `0.0.0.0` or expose the port if client confidentiality matters.

**Important:** Local processing reduces the risk of sending client bills to a cloud service, but it does not by itself guarantee that your organisation's policy or legal obligations are satisfied. Check Reducer/client data-handling rules and your Mac's disk encryption, user account, backups and malware protection. Files are processed in memory by the app; avoid saving bills into shared folders. The app is not an audited or certified compliance product.

## Install (macOS)
1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/macos/ if `python3 --version` does not show a supported version.
2. (Recommended for scanned/image bills) Install Homebrew from https://brew.sh if not already installed.
3. Open Terminal and run:
   ```bash
   brew install tesseract
   ```
   If you only work with text-based PDFs, OCR is not always needed. The app will still work for text extraction without Tesseract; scanned documents need OCR.
4. Download and unzip the project folder.
5. In Finder, open the folder. Right-click `Run_Operations_Assistant.command` → Open. If macOS blocks it, open Terminal, `cd` into the folder, then run:
   ```bash
   chmod +x Run_Operations_Assistant.command
   ./Run_Operations_Assistant.command
   ```
6. The first run creates `.venv` and installs packages. This requires internet access to download Python packages; client bill contents are not uploaded during installation.
7. A local URL appears in Terminal. Open `http://127.0.0.1:8501` in your browser.
8. Keep the Terminal window open while using the app. Press `Control + C` in Terminal to stop it.

## How to use
1. Upload the bills for one supply (preferably the latest 3 consecutive periods).
2. Review extracted text in each bill tab. OCR may misread digits.
3. Confirm the customer, supplier, fuel, address, MPAN/MPRN, meter serial, product and CED.
4. Enter unit rate and standing charge. Standing charge should be entered in **p/day**; unit rates in **p/kWh**.
5. Enter the number of billed days for each invoice. Add consumption to Day, Night and EW separately where present. For a single-rate meter, enter usage in `Total kWh (single-rate)`.
6. Check the displayed totals and annualised estimate.
7. Download the PDF and verify every figure before sharing.

## Accuracy notes
- This version uses local PDF text extraction and local OCR plus simple pattern-based suggestions, not a cloud AI model. It cannot reliably understand every supplier's invoice format.
- Treat prefilled values as suggestions. Confirm all fields against the bill.
- The consumption table intentionally requires review/input so it does not silently add incorrect values from unfamiliar invoice layouts.
- For bills spanning irregular periods, use the exact billed days shown/calculated from dates. Do not assume every invoice is one month.
- For multi-register electricity, enter register consumption separately and leave single-rate total as zero. For single-rate bills, enter the amount in `Total kWh (single-rate)`.

## Files
- `app.py` — Streamlit application
- `requirements.txt` — Python dependencies
- `Run_Operations_Assistant.command` — macOS launch/setup script
- `.streamlit/config.toml` — local privacy-oriented Streamlit settings
