#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=========================================="
echo " Operations Assistant - Local Setup"
echo "=========================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found."
  echo "Install Python 3.11 or 3.12 from https://www.python.org/downloads/macos/"
  echo "Then run this file again."
  read -r -p "Press Return to close..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating a local Python environment..."
  python3 -m venv .venv
fi

echo "Installing/updating Python packages..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "Starting Streamlit on this Mac only..."
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
export STREAMLIT_SERVER_ADDRESS=127.0.0.1
export STREAMLIT_SERVER_HEADLESS=true
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
