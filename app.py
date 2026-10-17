import io
import re
import os
from datetime import datetime
from typing import Optional

import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
from PIL import Image
import pytesseract
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

# -----------------------------
# Local-only configuration
# -----------------------------
st.set_page_config(page_title="Operations Assistant | Local", page_icon="⚡", layout="wide")
NAVY = colors.HexColor("#15283F")
BLUE = colors.HexColor("#4569E8")
MINT = colors.HexColor("#EAF7F2")
PALE_BLUE = colors.HexColor("#EEF2FF")
CREAM = colors.HexColor("#F8F7F3")
SLATE = colors.HexColor("#607086")
LINE = colors.HexColor("#DCE3EB")
DARK = colors.HexColor("#28394D")

st.markdown("""
<style>
    .stApp { background: #fbfcfe; }
    .block-container { max-width: 1180px; padding-top: 1.4rem; padding-bottom: 2rem; }
    .hero { padding: 1.3rem 1.5rem; border-radius: 18px; background: linear-gradient(115deg,#eef2ff 0%,#f8f7f3 58%,#eaf7f2 100%); border: 1px solid #dce3eb; margin-bottom: 1rem; }
    .eyebrow { text-transform: uppercase; letter-spacing: .12em; color: #4569e8; font-size: .75rem; font-weight: 750; }
    .hero h1 { color: #15283f; margin: .35rem 0 .25rem 0; font-size: 2.25rem; }
    .hero p { color: #607086; margin: 0; }
    div[data-testid="stMetric"] { background: white; border: 1px solid #dce3eb; padding: .8rem 1rem; border-radius: 13px; }
    div[data-testid="stMetricLabel"] { color: #607086; }
    .privacy { padding: .75rem 1rem; border-radius: 10px; border: 1px solid #c8e7dc; background: #f0faf6; color: #225b4c; font-size: .9rem; }
    .smallnote { color: #607086; font-size: .82rem; }
    h2, h3 { color: #15283f; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="eyebrow">Local workflow · No cloud AI</div>
  <h1>Operations Assistant</h1>
  <p>Commercial energy-bill review · extract, validate, calculate and export</p>
</div>
<div class="privacy"><b>Privacy by design:</b> files are processed in this local Python app. No bill content is sent to ChatGPT, an external AI API or a third-party server by this app. Keep the app running on your own computer and do not expose the Streamlit port to your network.</div>
""", unsafe_allow_html=True)

# -------- Local document processing --------
def extract_pdf_text(data: bytes) -> str:
    text_parts = []
    doc = fitz.open(stream=data, filetype="pdf")
    for page in doc:
        text_parts.append(page.get_text("text"))
    return "\n\n".join(text_parts).strip()

def extract_image_text(data: bytes) -> str:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    return pytesseract.image_to_string(image)

def text_from_upload(uploaded_file) -> tuple[str, str]:
    data = uploaded_file.getvalue()
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        txt = extract_pdf_text(data)
        if len(txt.strip()) < 40:
            try:
                doc = fitz.open(stream=data, filetype="pdf")
                pages = []
                for page in doc:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                    pages.append(pytesseract.image_to_string(img))
                txt = "\n\n".join(pages).strip()
                return txt, "PDF (local OCR)"
            except Exception as e:
                return txt, f"PDF text extraction; OCR unavailable: {e}"
        return txt, "PDF text extraction"
    return extract_image_text(data), "Image OCR (local Tesseract)"

def find_first(patterns, text, flags=re.I):
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip(" :\t\r\n")
    return ""

def guess_value(text, kind):
    patterns = {
        "account": [r"(?:account\s*(?:number|no\.?|#))\s*[:#]?\s*([A-Z0-9][A-Z0-9\- ]{3,24})"],
        "mprn": [r"\bMPRN\b\s*[:#]?\s*(\d{6,12})", r"Meter Point Reference Number\s*[:#]?\s*(\d{6,12})"],
        "mpan": [r"\bMPAN\b\s*[:#]?\s*(\d{12,21})", r"\bS\s*\d{2}\s*\d{3}\s*\d{3}\s*\d{3}\s*(?:\n|\s)+(\d{2}\s*\d{4}\s*\d{4}\s*\d{3})"],
        "meter": [r"(?:meter\s*(?:serial\s*)?(?:number|no\.?|serial))\s*[:#]?\s*([A-Z0-9]{5,20})"],
        "ced": [r"(?:contract\s*end\s*date|contract\s*end|plan\s*end\s*date|end\s*date)\s*[:#]?\s*(\d{1,2}[\/\- ](?:[A-Z]{3,9}|\d{1,2})[\/\- ,]*\d{2,4}|\d{1,2}\s+[A-Z]{3,9}\s+\d{4})"],
        "unit_rate": [r"(?:unit\s*rate|energy\s*charge|unit\s*price)\s*[: ]{0,4}£?\s*(\d+(?:\.\d+)?)\s*p?\s*(?:/|\s+per\s*)?kWh"],
        "standing": [r"(?:standing\s*charge|daily\s*standing\s*charge)\s*[: ]{0,5}£?\s*(\d+(?:\.\d+)?)\s*(?:p\/day|p per day|p\/d|per day|\/day|a day)"],
        "supplier": [r"(British Gas Lite|British Gas|ScottishPower|Scottish Power|TotalEnergies(?: Gas & Power)?|Gazprom|SEFE|Crown Gas & Power|Y[uü] Energy|Yu Energy|EDF Energy|E\.ON Next|E\.ON|Octopus Energy|Positive Energy)"],
    }
    return find_first(patterns.get(kind, []), text)

def guess_fuel(text):
    t = text.lower()
    if "mprn" in t or "gas charges" in t or "gas supply" in t or "gas bill" in t:
        if "mpan" not in t and "electricity" not in t:
            return "Gas"
    if "electricity" in t or "mpan" in t or "electricity charges" in t:
        return "Electricity"
    return "Not sure"

def parse_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return 0.0

def build_pdf(data, periods_df, totals, annual, days_total, avg_day, rate_registers):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=16*mm)
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name="EyebrowX", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLUE, spaceAfter=4))
    ss.add(ParagraphStyle(name="TitleX", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=23, leading=27, textColor=NAVY, alignment=0, spaceAfter=4))
    ss.add(ParagraphStyle(name="SubX", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=SLATE, spaceAfter=8))
    ss.add(ParagraphStyle(name="HeadX", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=5))
    ss.add(ParagraphStyle(name="BodyX", parent=ss["BodyText"], fontName="Helvetica", fontSize=8, leading=10.5, textColor=DARK, spaceAfter=1))
    ss.add(ParagraphStyle(name="TinyX", parent=ss["BodyText"], fontName="Helvetica", fontSize=7, leading=9, textColor=SLATE))
    ss.add(ParagraphStyle(name="MetricX", parent=ss["BodyText"], fontName="Helvetica-Bold", fontSize=18, leading=20, textColor=BLUE, alignment=1))
    ss.add(ParagraphStyle(name="MetricLabelX", parent=ss["BodyText"], fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=NAVY, alignment=1))
    P = lambda x, sty="BodyX": Paragraph(str(x), ss[sty])
    story = [P("OPERATIONS ASSISTANT  /  LOCAL ENERGY-BILL REVIEW", "EyebrowX"),
             P(data["customer"] or "Commercial Energy Supply", "TitleX"),
             P(f'{data["supplier"] or "Supplier not confirmed"}  ·  {data["fuel"]}  ·  {data["address"] or "Supply address not entered"}', "SubX")]
    facts = [
        [P("<b>ACCOUNT / METER POINT</b>"), P("<b>CONTRACT</b>"), P("<b>RATES</b>")],
        [P(f'Account: {data["account"] or "Not stated"}<br/>MPAN: {data["mpan"] or "Not stated"}<br/>MPRN: {data["mprn"] or "Not stated"}<br/>Meter serial: {data["meter"] or "Not stated"}'),
         P(f'Product: {data["product"] or "Not stated"}<br/>Start: {data["start"] or "Not stated"}<br/>CED: {data["ced"] or "Not stated"}'),
         P(f'Unit rate: {data["unit_rate"] or "Not entered"} p/kWh<br/>Standing charge: {data["standing"] or "Not entered"} p/day<br/>Day: {rate_registers["day"] or "—"} p/kWh<br/>Night: {rate_registers["night"] or "—"} p/kWh<br/>EW: {rate_registers["ew"] or "—"} p/kWh')]
    ]
    ft = Table(facts, colWidths=[58*mm,53*mm,57*mm])
    ft.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),("TEXTCOLOR",(0,0),(-1,0),colors.white),("BACKGROUND",(0,1),(-1,1),CREAM),("GRID",(0,0),(-1,-1),0.5,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story += [ft, P("Consumption periods", "HeadX")]
    headers = [P("<b>Period / bill</b>"), P("<b>Days</b>"), P("<b>Day kWh</b>"), P("<b>Night kWh</b>"), P("<b>EW kWh</b>"), P("<b>Total kWh</b>")]
    rows = [headers]
    for _, r in periods_df.iterrows():
        d, n, e = parse_num(r.get("Day kWh", 0)), parse_num(r.get("Night kWh", 0)), parse_num(r.get("EW kWh", 0))
        tot = parse_num(r.get("Total kWh", 0))
        if not tot:
            tot = d+n+e
        rows.append([P(r.get("Period", "")), P(r.get("Days", "")), P(f"{d:,.2f}" if d else "—"), P(f"{n:,.2f}" if n else "—"), P(f"{e:,.2f}" if e else "—"), P(f"{tot:,.2f}" if tot else "—")])
    tb = Table(rows, colWidths=[49*mm,16*mm,29*mm,29*mm,25*mm,30*mm], repeatRows=1)
    tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),BLUE),("GRID",(0,0),(-1,-1),0.4,LINE),("BACKGROUND",(0,1),(-1,-1),colors.white),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [tb, Spacer(1, 3*mm)]
    metrics = Table([[
        [P(f"{totals['total']:,.0f}", "MetricX"), P("TOTAL CONSUMPTION · kWh", "MetricLabelX")],
        [P(f"{totals['avg_month']:,.0f}", "MetricX"), P("AVERAGE PER BILL · kWh", "MetricLabelX")],
        [P(f"{annual:,.0f}", "MetricX"), P("ANNUALISED · kWh/year", "MetricLabelX")],
        [P(f"{days_total}", "MetricX"), P("TOTAL BILLED DAYS", "MetricLabelX")]
    ]], colWidths=[42*mm]*4)
    metrics.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),PALE_BLUE),("BACKGROUND",(1,0),(1,0),MINT),("BACKGROUND",(2,0),(2,0),CREAM),("BACKGROUND",(3,0),(3,0),PALE_BLUE),("BOX",(0,0),(-1,-1),0.5,LINE),("INNERGRID",(0,0),(-1,-1),0.5,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story += [metrics, Spacer(1, 3*mm), P(f'Daily average: {avg_day:,.2f} kWh/day  ·  Annualisation method: total consumption ÷ total billed days × 365.', "TinyX"),
              Spacer(1, 2*mm), P("Human verification required: confirm meter point, billing dates, rates and any OCR-extracted values against the original invoices.", "TinyX")]
    doc.build(story)
    return buf.getvalue()

# -------- Sidebar and uploads --------
with st.sidebar:
    st.markdown("### Workflow")
    st.markdown("1. Upload bills\n2. Review extracted text\n3. Confirm supply details\n4. Enter consumption registers\n5. Download PDF")
    st.markdown("---")
    st.markdown("**Privacy note**")
    st.caption("No external AI/API calls are made. Uploaded documents are held in this app's local session memory while it is running.")

uploads = st.file_uploader("Upload bill PDFs or screenshots", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff"], accept_multiple_files=True)
if "bill_texts" not in st.session_state:
    st.session_state.bill_texts = {}
if "field_defaults" not in st.session_state:
    st.session_state.field_defaults = {}

combined = ""
if uploads:
    st.subheader("1 · Local extraction")
    tabs = st.tabs([f"{u.name[:24]}" for u in uploads])
    for tab, u in zip(tabs, uploads):
        try:
            txt, method = text_from_upload(u)
        except Exception as e:
            txt, method = "", f"Extraction error: {e}"
        st.session_state.bill_texts[u.name] = txt
        with tab:
            st.caption(f"Method: {method}")
            if not txt:
                st.warning("No readable text was extracted. If this is a scanned PDF or image, install Tesseract OCR (instructions in README).")
            st.text_area("Extracted text (local; editable for corrections)", value=txt, height=180, key=f"text_{u.name}")
        combined += f"\n\n--- {u.name} ---\n{txt}\n"
    st.caption("Extraction is a first pass. OCR and supplier layouts can misread digits; verify every important value against the original bill.")

# Editable fields; auto-suggest from combined text
defaults = {
    "customer": find_first([r"(?:customer\s*name|account\s*name|bill(?:ing)?\s*name)\s*[:\-]?\s*([A-Z][A-Z0-9 &.,'()\-]{3,70})"], combined),
    "supplier": guess_value(combined, "supplier"),
    "fuel": guess_fuel(combined),
    "address": find_first([r"(?:supply\s*address|site\s*address)\s*[:\-]\s*([^\n]{5,100})"], combined),
    "account": guess_value(combined, "account"),
    "mpan": guess_value(combined, "mpan"),
    "mprn": guess_value(combined, "mprn"),
    "meter": guess_value(combined, "meter"),
    "product": find_first([r"(?:product|tariff|plan)\s*[:\-]?\s*([A-Z][A-Za-z0-9 &\-]{2,40})"], combined),
    "start": find_first([r"(?:contract\s*start\s*date|start\s*date)\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+[A-Z]{3,9}\s+\d{4})"], combined),
    "ced": guess_value(combined, "ced"),
    "unit_rate": guess_value(combined, "unit_rate"),
    "standing": guess_value(combined, "standing"),
}
st.subheader("2 · Confirm supply details")
st.caption("Fields are editable. Auto-extraction is best-effort; use the bill as the source of truth.")
c1, c2, c3 = st.columns(3)
with c1:
    customer = st.text_input("Customer", value=defaults["customer"], key="customer")
    supplier = st.text_input("Supplier", value=defaults["supplier"], key="supplier")
    fuel = st.selectbox("Fuel", ["Gas", "Electricity", "Dual fuel", "Not sure"], index=["Gas", "Electricity", "Dual fuel", "Not sure"].index(defaults["fuel"]) if defaults["fuel"] in ["Gas","Electricity","Dual fuel","Not sure"] else 3)
    address = st.text_input("Supply address", value=defaults["address"], key="address")
with c2:
    account = st.text_input("Account number", value=defaults["account"], key="account")
    mpan = st.text_input("MPAN (electricity)", value=defaults["mpan"], key="mpan")
    mprn = st.text_input("MPRN (gas)", value=defaults["mprn"], key="mprn")
    meter = st.text_input("Meter serial number", value=defaults["meter"], key="meter")
with c3:
    product = st.text_input("Product / tariff", value=defaults["product"], key="product")
    start = st.text_input("Contract start date (if known)", value=defaults["start"], key="start")
    ced = st.text_input("Contract end date (CED)", value=defaults["ced"], key="ced")
    unit_rate = st.text_input("Unit rate (p/kWh)", value=defaults["unit_rate"], key="unit_rate")
    standing = st.text_input("Standing charge (p/day)", value=defaults["standing"], key="standing")

st.subheader("3 · Rates by register")
r1, r2, r3 = st.columns(3)
with r1:
    day_rate = st.text_input("Day rate (p/kWh)", value="", key="day_rate")
with r2:
    night_rate = st.text_input("Night rate (p/kWh)", value="", key="night_rate")
with r3:
    ew_rate = st.text_input("Evening & Weekend rate (p/kWh)", value="", key="ew_rate")

st.subheader("4 · Consumption by bill")
st.caption("Enter the billing period and days shown on each invoice. Keep Day, Night and Evening & Weekend registers separate wherever applicable. For single-rate supplies, enter usage in Total kWh.")
default_rows = [{"Period": "Bill 1", "Days": 0, "Day kWh": 0.0, "Night kWh": 0.0, "EW kWh": 0.0, "Total kWh": 0.0}]
if uploads:
    default_rows = [{"Period": u.name[:28], "Days": 0, "Day kWh": 0.0, "Night kWh": 0.0, "EW kWh": 0.0, "Total kWh": 0.0} for u in uploads]
df = pd.DataFrame(default_rows)
edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True,
    column_config={
        "Period": st.column_config.TextColumn("Bill / billing period"),
        "Days": st.column_config.NumberColumn("Days", min_value=0, step=1),
        "Day kWh": st.column_config.NumberColumn("Day kWh", min_value=0.0, format="%.2f"),
        "Night kWh": st.column_config.NumberColumn("Night kWh", min_value=0.0, format="%.2f"),
        "EW kWh": st.column_config.NumberColumn("EW kWh", min_value=0.0, format="%.2f"),
        "Total kWh": st.column_config.NumberColumn("Total kWh (single-rate)", min_value=0.0, format="%.2f"),
    })

# Compute total: register values sum if provided, otherwise single-rate total
if not edited_df.empty:
    register_total = edited_df["Day kWh"].fillna(0).sum() + edited_df["Night kWh"].fillna(0).sum() + edited_df["EW kWh"].fillna(0).sum()
    single_total = edited_df["Total kWh"].fillna(0).sum()
    total = float(register_total + single_total)
    days_total = int(edited_df["Days"].fillna(0).sum())
    avg_month = total / len(edited_df) if len(edited_df) else 0
    avg_day = total / days_total if days_total else 0
    annual = avg_day * 365
else:
    total, days_total, avg_month, avg_day, annual = 0.0, 0, 0.0, 0.0, 0.0

st.subheader("5 · Calculated summary")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total consumption", f"{total:,.2f} kWh")
m2.metric("Average per bill", f"{avg_month:,.2f} kWh")
m3.metric("Annualised estimate", f"{annual:,.0f} kWh/year")
m4.metric("Billed days", f"{days_total}")
st.caption("Formula: total consumption ÷ total billed days × 365. This estimate is only as reliable as the periods and consumption entered.")

# Preview text extraction in expandable area
with st.expander("View combined extracted text"):
    st.text_area("Combined text", value=combined, height=220)

st.subheader("6 · Download report")
data = {
    "customer": customer, "supplier": supplier, "fuel": fuel, "address": address,
    "account": account, "mpan": mpan, "mprn": mprn, "meter": meter, "product": product,
    "start": start, "ced": ced, "unit_rate": unit_rate, "standing": standing
}
rate_registers = {"day": day_rate, "night": night_rate, "ew": ew_rate}
pdf_bytes = build_pdf(data, edited_df, {"total": total, "avg_month": avg_month}, annual, days_total, avg_day, rate_registers)
st.download_button("Download client-ready PDF", data=pdf_bytes,
                   file_name=f"Energy_Bill_Analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                   mime="application/pdf", type="primary")
st.markdown('<p class="smallnote">Before sharing: verify identifiers, dates, rates, standing charge and register totals against the original invoices. This app does not guarantee that extracted values are correct.</p>', unsafe_allow_html=True)
