from __future__ import annotations
import io, hashlib, html, re
from datetime import datetime
from collections import defaultdict

import pandas as pd
import streamlit as st
from bill_parser import extract_document, parse_bill, calculate_usage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

# ---------------- Page + visual system ----------------
st.set_page_config(page_title="Operations Assistant | Bill Review", page_icon="OA", layout="wide", initial_sidebar_state="expanded")
NAVY="#14243A"; BLUE="#4263EB"; CYAN="#11A9A0"; TEXT="#1E293B"; MUTED="#66758A"; LINE="#E2E8F0"; BG="#F5F7FB"; WHITE="#FFFFFF"; AMBER="#B7791F"; RED="#B42318"; GREEN="#147D64"
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root {{ --oa-navy:{NAVY}; --oa-blue:{BLUE}; --oa-text:{TEXT}; --oa-muted:{MUTED}; }}
html, body, [class*="css"] {{ font-family:'DM Sans',sans-serif; color:var(--oa-text); }}
.stApp {{ background:{BG}; }}
.block-container {{ max-width:1440px; padding-top:1.25rem; padding-bottom:3rem; }}
[data-testid="stSidebar"] {{ background:#101D30; border-right:1px solid #263750; }}
[data-testid="stSidebar"] * {{ color:#E7EDF7 !important; }}
[data-testid="stSidebar"] .stCaption {{ color:#A8B7CC !important; }}
.oa-brand {{ display:flex; align-items:center; gap:12px; margin:.2rem 0 1.4rem; }}
.oa-mark {{ width:42px;height:42px;border-radius:13px;display:flex;align-items:center;justify-content:center;background:linear-gradient(145deg,{BLUE},{CYAN});color:white;font-family:Manrope,sans-serif;font-size:17px;font-weight:800;box-shadow:0 8px 20px #0002; }}
.oa-brand-title {{ font-family:Manrope,sans-serif;font-size:16px;font-weight:800;color:white;line-height:1.2; }}
.oa-brand-sub {{ color:#9DAEC4;font-size:11px;margin-top:3px;letter-spacing:.08em;text-transform:uppercase; }}
.oa-hero {{ background:linear-gradient(120deg,#152942 0%,#1C3554 55%,#203E5D 100%); padding:28px 32px; border-radius:20px; color:white; margin-bottom:18px; position:relative; overflow:hidden; }}
.oa-hero:after {{ content:'';position:absolute;width:280px;height:280px;border-radius:50%;border:1px solid #ffffff1a;right:-65px;top:-140px;box-shadow:0 0 0 32px #ffffff08,0 0 0 65px #ffffff05; }}
.oa-kicker {{ text-transform:uppercase;letter-spacing:.16em;font-size:10px;font-weight:800;color:#8FB1FF;margin-bottom:8px; }}
.oa-hero h1 {{ font-family:Manrope,sans-serif;font-size:32px;line-height:1.15;font-weight:800;color:white;margin:0 0 8px; }}
.oa-hero p {{ color:#D4DEEC;font-size:14px;margin:0;max-width:720px; }}
.oa-pill {{ display:inline-block;border:1px solid #ffffff25;background:#ffffff0d;color:#DDE8F7;border-radius:99px;padding:5px 10px;font-size:11px;font-weight:600;margin-top:16px; }}
.oa-section {{ font-family:Manrope,sans-serif;font-weight:800;font-size:18px;color:{NAVY};margin:12px 0 4px; }}
.oa-sub {{ color:{MUTED};font-size:12px;margin-bottom:12px; }}
.oa-card {{ background:white;border:1px solid {LINE};border-radius:16px;padding:16px 18px;box-shadow:0 3px 12px #15243a06; }}
.oa-card-label {{ font-size:11px;color:{MUTED};font-weight:700;letter-spacing:.05em;text-transform:uppercase;margin-bottom:7px; }}
.oa-card-value {{ font-family:Manrope,sans-serif;font-size:25px;font-weight:800;color:{NAVY};line-height:1.2; }}
.oa-card-foot {{ color:{MUTED};font-size:11px;margin-top:6px; }}
.oa-note {{ padding:12px 14px;border:1px solid #D9E4FF;border-left:4px solid {BLUE};background:#F3F6FF;border-radius:10px;color:#344565;font-size:12px; }}
.oa-warning {{ padding:12px 14px;border:1px solid #F1D7A5;border-left:4px solid #D99A24;background:#FFF9EB;border-radius:10px;color:#76541B;font-size:12px; }}
.oa-success {{ padding:12px 14px;border:1px solid #BCE5D9;border-left:4px solid {CYAN};background:#EFFAF6;border-radius:10px;color:#22594D;font-size:12px; }}
.oa-divider {{ height:1px;background:{LINE};margin:18px 0; }}
.stButton>button, .stDownloadButton>button {{ border-radius:10px;font-weight:700;min-height:42px; }}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"] {{ background:{BLUE};border-color:{BLUE}; }}
[data-testid="stMetric"] {{ background:white;border:1px solid {LINE};border-radius:14px;padding:14px 16px;box-shadow:0 3px 12px #15243a06; }}
[data-testid="stMetricLabel"] {{ color:{MUTED};font-size:12px; }}
[data-testid="stMetricValue"] {{ font-family:Manrope,sans-serif;color:{NAVY};font-weight:800; }}
[data-testid="stFileUploader"] {{ background:white;border:1.5px dashed #B9C7DA;border-radius:16px;padding:8px; }}
[data-testid="stTabs"] button {{ font-weight:700; }}
/* Strong, consistent contrast: the previous global/sidebar styles made form labels nearly invisible. */
.stApp, .stApp p, .stApp span, .stApp label, .stApp [data-testid="stWidgetLabel"], .stApp [data-testid="stMarkdownContainer"] {{ color:{TEXT}; }}
.stApp [data-testid="stWidgetLabel"] p, .stApp [data-testid="stWidgetLabel"] label {{ color:{NAVY} !important; font-weight:700 !important; }}
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div {{ background:#FFFFFF !important; color:{TEXT} !important; border-color:#CBD5E1 !important; }}
.stApp input::placeholder, .stApp textarea::placeholder {{ color:#94A3B8 !important; }}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ color:{MUTED} !important; }}
.stApp [data-testid="stTabs"] button {{ color:{NAVY} !important; }}
.stApp [data-testid="stTabs"] button[aria-selected="true"] {{ color:{BLUE} !important; border-bottom-color:{BLUE} !important; }}
.stApp [data-testid="stDataFrame"], .stApp [data-testid="stDataEditor"] {{ background:white; border-radius:12px; }}
.oa-hero {{ box-shadow:0 12px 28px #14243A12; }}
.oa-hero h1, .oa-hero p, .oa-hero .oa-kicker, .oa-hero .oa-pill {{ color:#FFFFFF !important; }}
.oa-hero .oa-kicker {{ color:#AFC6FF !important; }}
.oa-section {{ margin-top:20px; }}

[data-testid="stExpander"] {{ border:1px solid {LINE};border-radius:12px;background:white; }}
small, .stCaption {{ color:{MUTED}; }}
footer {{ visibility:hidden; }}
</style>
""", unsafe_allow_html=True)

# ---------------- PDF report ----------------
def esc(v): return html.escape(str(v if v not in (None, "") else "Not stated"))
def fmt_num(v, dec=2):
    try: return f"{float(v):,.{dec}f}"
    except (TypeError,ValueError): return "—"
def moneyish(v): return str(v) if v not in (None, "") else "Not stated"

def current_review_flags(record, details, usage=None, days=None):
    flags=list(record.get("status",[]))
    checks=[
        ("Customer name needs review", bool(details.get("Customer", "").strip())),
        ("Supplier not identified", bool(details.get("Supplier", "").strip())),
        ("Supply address needs review", bool(details.get("Supply address", "").strip())),
        ("MPAN/MPRN not found", bool(details.get("MPAN", "").strip() or details.get("MPRN", "").strip())),
        ("Unit rate needs review", bool(details.get("Unit rates (p/kWh)", "").strip())),
        ("Standing charge needs review", bool(details.get("Standing charge (p/day)", "").strip())),
        ("Consumption not reliably extracted", bool((usage if usage is not None else record.get("usage", 0)) > 0)),
        ("Billing days not reliably extracted", bool((days if days is not None else record.get("days", 0)) > 0)),
    ]
    for flag,has_value in checks:
        if has_value and flag in flags: flags.remove(flag)
    return flags

def make_report(records, consumption_df, detail_values, generated_at):
    """Clean, readable portrait report with explicit calculation steps and highlighted results."""
    buff=io.BytesIO()
    doc=SimpleDocTemplate(buff,pagesize=A4,rightMargin=11*mm,leftMargin=11*mm,topMargin=8*mm,bottomMargin=12*mm)
    ss=getSampleStyleSheet()
    ss.add(ParagraphStyle(name="OAeyebrow2",parent=ss["Normal"],fontName="Helvetica-Bold",fontSize=8,leading=10,textColor=colors.HexColor(BLUE),spaceAfter=7))
    ss.add(ParagraphStyle(name="OATitle2",parent=ss["Title"],fontName="Helvetica-Bold",fontSize=21,leading=23,textColor=colors.HexColor(NAVY),alignment=TA_LEFT,spaceAfter=3))
    ss.add(ParagraphStyle(name="OASub2",parent=ss["Normal"],fontName="Helvetica",fontSize=6,leading=7,textColor=colors.HexColor(MUTED),spaceAfter=5))
    ss.add(ParagraphStyle(name="OAHead2",parent=ss["Heading2"],fontName="Helvetica-Bold",fontSize=10,leading=12,textColor=colors.HexColor(NAVY),spaceBefore=6,spaceAfter=3))
    ss.add(ParagraphStyle(name="OABody2",parent=ss["BodyText"],fontName="Helvetica",fontSize=7,leading=8.5,textColor=colors.HexColor(TEXT)))
    ss.add(ParagraphStyle(name="OATiny2",parent=ss["BodyText"],fontName="Helvetica",fontSize=6,leading=7,textColor=colors.HexColor(MUTED)))
    ss.add(ParagraphStyle(name="OAHeadCell2",parent=ss["BodyText"],fontName="Helvetica-Bold",fontSize=8,leading=10,textColor=colors.white))
    ss.add(ParagraphStyle(name="OAMetric2",parent=ss["BodyText"],fontName="Helvetica-Bold",fontSize=12,leading=14,textColor=colors.HexColor(NAVY),alignment=TA_LEFT))
    ss.add(ParagraphStyle(name="OAMetricLabel2",parent=ss["BodyText"],fontName="Helvetica-Bold",fontSize=6,leading=7,textColor=colors.HexColor(MUTED),alignment=TA_LEFT))
    ss.add(ParagraphStyle(name="OAStep2",parent=ss["BodyText"],fontName="Helvetica",fontSize=7,leading=8.5,textColor=colors.HexColor(TEXT)))
    P=lambda v,sty="OABody2":Paragraph(str(v),ss[sty])
    story=[P("OPERATIONS ASSISTANT  /  COMMERCIAL ENERGY BILL REVIEW","OAeyebrow2"),
           P("Energy Bill Analysis","OATitle2"),
           P(f"Generated {esc(generated_at)} · Source-backed extraction · Review flagged fields against the original invoice.","OASub2")]
    # High-level summary cards
    totals=defaultdict(lambda:{"usage":0.0,"days":0,"bills":0,"rows":[],"unknown":False})
    for _,row in consumption_df.iterrows():
        rec=next((x for x in records if x["id"]==row.get("_id")),None)
        if not rec: continue
        d=detail_values[rec["id"]]
        key=(d.get("MPAN","").strip() or d.get("MPRN","").strip() or d.get("Account number","").strip() or rec["filename"])
        vals=[row.get(c) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"]]
        nums=[float(v) for v in vals if v is not None and not pd.isna(v)]
        total=sum(max(0,v) for v in nums)
        totals[key]["usage"]+=total; totals[key]["days"]+=int(row.get("Days",0) or 0); totals[key]["bills"]+=1
        totals[key]["rows"].append((rec,row,total))
        if not nums: totals[key]["unknown"]=True
    total_usage=sum(v["usage"] for v in totals.values())
    total_days=sum(v["days"] for v in totals.values())
    annual,monthly=calculate_usage(total_usage,total_days)
    metrics=[
        [P("TOTAL CONSUMPTION","OAMetricLabel2"),P(f"{total_usage:,.2f} kWh","OAMetric2")],
        [P("BILLED DAYS","OAMetricLabel2"),P(f"{total_days:,}","OAMetric2")],
        [P("AVERAGE MONTHLY","OAMetricLabel2"),P(f"{monthly:,.2f} kWh" if monthly is not None else "—","OAMetric2")],
        [P("ANNUALISED ESTIMATE","OAMetricLabel2"),P(f"{annual:,.2f} kWh/year" if annual is not None else "—","OAMetric2")],
    ]
    mt=Table([metrics],colWidths=[44*mm]*4)
    mt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F2F5FB")),("BOX",(0,0),(-1,-1),.6,colors.HexColor(LINE)),("INNERGRID",(0,0),(-1,-1),.5,colors.HexColor(LINE)),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.append(mt)
    story.append(P("Supply details","OAHead2"))
    detail_rows=[[P("FIELD","OAHeadCell2"),P("EXTRACTED VALUE","OAHeadCell2")]]
    for r in records:
        d=detail_values[r["id"]]
        detail_rows += [
            [P("Source bill"),P(esc(r["filename"]))],
            [P("Customer / supplier"),P(f"<b>{esc(d.get('Customer',''))}</b><br/>{esc(d.get('Supplier',''))}")],
            [P("Fuel / supply address"),P(f"{esc(d.get('Fuel',''))}<br/>{esc(d.get('Supply address',''))}")],
            [P("Account / MPAN / MPRN / meter"),P(f"Account: {esc(d.get('Account number',''))}<br/>MPAN: {esc(d.get('MPAN',''))}<br/>MPRN: {esc(d.get('MPRN',''))}<br/>Meter: {esc(d.get('Meter serial number',''))}")],
            [P("Product / contract end"),P(f"{esc(d.get('Product / tariff',''))}<br/>CED: {esc(d.get('Contract end date (CED)',''))}")],
            [P("Rates and charges"),P(f"Unit rate: {esc(d.get('Unit rates (p/kWh)',''))} p/kWh<br/>Standing charge: {esc(d.get('Standing charge (p/day)',''))} p/day<br/>CCL: {esc(d.get('CCL rate (p/kWh)',''))} p/kWh")],
        ]
    dt=Table(detail_rows,colWidths=[54*mm,122*mm],repeatRows=1,hAlign="LEFT")
    dt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(NAVY)),("BACKGROUND",(0,1),(0,-1),colors.HexColor("#F2F5FB")),("GRID",(0,0),(-1,-1),.45,colors.HexColor(LINE)),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
    story.append(dt)
    story.append(P("Consumption by bill","OAHead2"))
    cr=[[P("BILL / PERIOD","OAHeadCell2"),P("DAYS","OAHeadCell2"),P("DAY","OAHeadCell2"),P("NIGHT","OAHeadCell2"),P("E&W","OAHeadCell2"),P("OTHER","OAHeadCell2"),P("SINGLE RATE","OAHeadCell2"),P("TOTAL","OAHeadCell2")]]
    for _,row in consumption_df.iterrows():
        def valfmt(v):
            try: return "—" if v is None or pd.isna(v) or abs(float(v))<1e-8 else f"{float(v):,.2f}"
            except (ValueError,TypeError): return "—"
        total=sum(float(row.get(c) or 0) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"] if row.get(c) is not None and not pd.isna(row.get(c)))
        cr.append([P(f"{esc(row.get('Bill',''))}<br/><font color='#66758A'>{esc(row.get('Billing period',''))}</font>"),P(str(int(row.get("Days",0) or 0))),P(valfmt(row.get("Day kWh"))),P(valfmt(row.get("Night kWh"))),P(valfmt(row.get("EW kWh"))),P(valfmt(row.get("Other register kWh"))),P(valfmt(row.get("Single-rate kWh"))),P(f"<b>{total:,.2f}</b>")])
    ct=Table(cr,colWidths=[47*mm,13*mm,17*mm,17*mm,15*mm,17*mm,22*mm,19*mm],repeatRows=1,hAlign="LEFT")
    ct.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(BLUE)),("GRID",(0,0),(-1,-1),.45,colors.HexColor(LINE)),("BACKGROUND",(0,1),(-1,-1),colors.white),("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,1),(-1,-1),"RIGHT"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
    story.append(ct)
    story.append(P("Calculation — step by step","OAHead2"))
    story.append(P("Formula: Annualised consumption = Total consumption ÷ Total billed days × 365","OAStep2"))
    for key,v in totals.items():
        usage=v["usage"]; days=v["days"]
        ann,mon=calculate_usage(usage,days)
        # Each supply gets its own transparent arithmetic and highlighted final values.
        step_rows=[
            [P("1  Total consumption"),P(f"{usage:,.2f} kWh")],
            [P("2  Total billed days"),P(f"{days:,} days")],
            [P("3  Daily average"),P(f"{usage:,.2f} ÷ {days:,} = {usage/days:,.4f} kWh/day" if days else "Cannot calculate — billed days missing")],
            [P("4  Annualise"),P(f"{usage:,.2f} ÷ {days:,} × 365 = {ann:,.2f} kWh/year" if ann is not None else "Cannot calculate — usage or billed days missing")],
            [P("5  Average monthly"),P(f"{ann:,.2f} ÷ 12 = {mon:,.2f} kWh/month" if ann is not None else "Not calculated")],
        ]
        st=Table(step_rows,colWidths=[54*mm,122*mm],hAlign="LEFT")
        st.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F2F5FB")),("BACKGROUND",(1,3),(1,4),colors.HexColor("#EAF7F2")),("TEXTCOLOR",(1,3),(1,4),colors.HexColor("#126B55")),("BOX",(0,0),(-1,-1),.6,colors.HexColor(LINE)),("INNERGRID",(0,0),(-1,-1),.4,colors.HexColor(LINE)),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
        story.append(P(f"Supply: {esc(key)}","OABody2")); story.append(st)
        story.append(Spacer(1,1*mm))
    def footer(canvas,doc_):
        canvas.saveState(); w,h=A4
        canvas.setStrokeColor(colors.HexColor(LINE)); canvas.line(11*mm,8*mm,w-11*mm,8*mm)
        canvas.setFont("Helvetica",7); canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(11*mm,4*mm,"OPERATIONS ASSISTANT  ·  ENERGY BILL REVIEW")
        canvas.drawRightString(w-11*mm,4*mm,f"PAGE {doc_.page}")
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buff.getvalue()

# ---------------- Header ----------------
st.markdown(f"""
<div class="oa-hero"><div class="oa-kicker">Commercial energy operations · Document intelligence</div><h1>Operations Assistant</h1><p>Turn supplier bills into a consistent, reviewable supply report — with consumption calculations, source evidence and missing-data flags.</p><span class="oa-pill">UPLOAD → EXTRACT → REVIEW → CALCULATE → EXPORT</span></div>
""",unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f'<div class="oa-brand"><div class="oa-mark">OA</div><div><div class="oa-brand-title">Operations Assistant</div><div class="oa-brand-sub">Energy bill review</div></div></div>',unsafe_allow_html=True)
    st.markdown("### Workflow")
    st.markdown("**01**  Upload documents\n\n**02**  Review extracted details\n\n**03**  Confirm consumption\n\n**04**  Export the report")
    st.markdown("---")
    st.caption("No external AI API is called. Extraction uses PDF text/OCR plus supplier-aware parsing; always verify the source bill.")

st.markdown('<div class="oa-section">01 · Upload bills</div><div class="oa-sub">Upload one or more PDFs or screenshots. Each file is parsed independently so values from different bills are not mixed together.</div>',unsafe_allow_html=True)
uploads=st.file_uploader("Drop commercial energy bills here",type=["pdf","png","jpg","jpeg","tif","tiff"],accept_multiple_files=True,label_visibility="collapsed",help="Text PDFs are fastest. Scanned PDFs use OCR when Tesseract is available.")

if "oa_parsed" not in st.session_state: st.session_state.oa_parsed={}
if not uploads:
    st.markdown('<div class="oa-note"><b>Designed for a review-first workflow.</b> Upload bill PDFs to automatically extract supplier, customer, supply address, MPAN/MPRN, meter serial, tariff, CED, rates, standing charge, CCL, consumption and billing days. Uncertain or missing values are flagged rather than invented.</div>',unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    with c1: st.markdown('<div class="oa-card"><div class="oa-card-label">Extraction</div><div style="font-weight:800;color:#14243A;font-size:16px">Supplier-aware</div><div class="oa-card-foot">Works with common UK bill layouts; unsupported layouts stay flagged.</div></div>',unsafe_allow_html=True)
    with c2: st.markdown('<div class="oa-card"><div class="oa-card-label">Calculations</div><div style="font-weight:800;color:#14243A;font-size:16px">Auditable</div><div class="oa-card-foot">Usage ÷ billed days × 365, with register totals kept separate.</div></div>',unsafe_allow_html=True)
    with c3: st.markdown('<div class="oa-card"><div class="oa-card-label">Output</div><div style="font-weight:800;color:#14243A;font-size:16px">Report-ready</div><div class="oa-card-foot">Editable fields, review flags and a formatted PDF export.</div></div>',unsafe_allow_html=True)
    st.stop()

records=[]
for uploaded in uploads:
    raw=uploaded.getvalue(); file_hash=hashlib.sha256(raw).hexdigest()[:12]
    if file_hash not in st.session_state.oa_parsed:
        with st.spinner(f"Reading {uploaded.name}…"):
            try:
                text,method,pages=extract_document(raw,uploaded.name)
                rec=parse_bill(text,uploaded.name,method,pages)
                rec["id"]=file_hash
                st.session_state.oa_parsed[file_hash]=rec
            except Exception as exc:
                st.session_state.oa_parsed[file_hash]={"id":file_hash,"filename":uploaded.name,"text":"","method":"Extraction failed","pages":0,"status":[f"Could not read file: {type(exc).__name__}: {exc}"],"supplier":"","fuel":"Not confirmed","customer":"","address":"","account":"","mpan":"","mprn":"","meter":"","product":"","start":"","ced":"","bill_date":"","invoice":"","period":"","days":0,"usage":0,"usage_source":"","usage_evidence":[],"registers":[],"rates":[],"standing":"","ccl":"","supplier_annual":"","fields":{},"confidence":"Needs review","period_dates":[],"day_counts":[]}
    records.append(st.session_state.oa_parsed[file_hash])

# Create stable editable field state per document.
FIELD_MAP=[("Customer","customer"),("Supplier","supplier"),("Fuel","fuel"),("Supply address","address"),("Account number","account"),("MPAN","mpan"),("MPRN","mprn"),("Meter serial number","meter"),("Product / tariff","product"),("Contract start date","start"),("Contract end date (CED)","ced"),("Price guaranteed until","price_guarantee"),("Unit rates (p/kWh)","rates_text"),("Standing charge (p/day)","standing"),("CCL rate (p/kWh)","ccl"),("Supplier stated annual usage (kWh)","supplier_annual")]
def initial_field(r,field):
    if field=="rates_text": return "; ".join(f"{x['label']}: {x['rate']:g}" for x in r.get("rates",[]))
    return str(r.get(field,""))

detail_values={}
for r in records:
    d={}
    for label,field in FIELD_MAP:
        key=f"oa_{r['id']}_{field}"
        if key not in st.session_state: st.session_state[key]=initial_field(r,field)
        d[label]=st.session_state[key]
    detail_values[r['id']]=d

st.markdown('<div class="oa-divider"></div><div class="oa-section">02 · Extraction overview</div><div class="oa-sub">Check each document’s extraction status before using the data downstream.</div>',unsafe_allow_html=True)
parsed_count=sum(1 for r in records if r.get("usage",0)>0 and r.get("days",0)>0)
flag_count=sum(len(current_review_flags(r,detail_values[r['id']])) for r in records)
k1,k2,k3,k4=st.columns(4)
k1.metric("Documents",len(records))
k2.metric("Usage extracted",f"{sum(1 for r in records if r.get('usage',0)>0)} / {len(records)}")
k3.metric("Billing days found",f"{sum(1 for r in records if r.get('days',0)>0)} / {len(records)}")
k4.metric("Review flags",flag_count,delta="Check before export" if flag_count else "No missing-field flags",delta_color="inverse" if flag_count else "normal")

for r in records:
    flags=current_review_flags(r,detail_values[r['id']])
    if flags:
        st.markdown(f'<div class="oa-warning"><b>{html.escape(r["filename"])}</b> · Needs review: {html.escape("; ".join(flags))}</div>',unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="oa-success"><b>{html.escape(r["filename"])}</b> · Core fields extracted. Please still verify against the source bill.</div>',unsafe_allow_html=True)

st.markdown('<div class="oa-divider"></div><div class="oa-section">03 · Review extracted supply details</div><div class="oa-sub">The first pass is editable. Every field can be corrected before generating the final report.</div>',unsafe_allow_html=True)
tabs=st.tabs([f"{r['filename'][:26]}" for r in records])
for tab,r in zip(tabs,records):
    with tab:
        d=detail_values[r['id']]
        st.caption(f"{r.get('supplier') or 'Supplier not identified'} · {r.get('fuel','Not confirmed')} · {r.get('method','')} · {r.get('pages',0)} page(s)")
        col1,col2,col3=st.columns(3)
        field_order=[
            [("Customer","Customer"),("Supplier","Supplier"),("Fuel","Fuel"),("Supply address","Supply address"),("Account number","Account number")],
            [("MPAN","MPAN"),("MPRN","MPRN"),("Meter serial number","Meter serial number"),("Product / tariff","Product / tariff"),("Contract start date","Contract start date")],
            [("Contract end date (CED)","Contract end date (CED)"),("Price guaranteed until","Price guaranteed until"),("Unit rates (p/kWh)","Unit rates (p/kWh)"),("Standing charge (p/day)","Standing charge (p/day)"),("CCL rate (p/kWh)","CCL rate (p/kWh)"),("Supplier stated annual usage (kWh)","Supplier stated annual usage (kWh)")]
        ]
        for col,fields in zip([col1,col2,col3],field_order):
            with col:
                for label,_ in fields:
                    field=dict((x[0],x[1]) for x in FIELD_MAP)[label]
                    key=f"oa_{r['id']}_{field}"
                    st.text_input(label,key=key,help="Edit if the source bill shows a different value. Leave blank if not stated.")
        with st.expander("View source text and extraction evidence"):
            st.caption("Evidence excerpts are generated from the PDF text layer/OCR. They are useful pointers, not proof that a value was read correctly.")
            for label,(value,evidence) in r.get("fields",{}).items():
                if value or evidence:
                    st.markdown(f"**{html.escape(label)}:** {html.escape(str(value) or 'Not found')}")
                    if evidence: st.caption(html.escape(str(evidence)[:500]))
            st.text_area("Full extracted text",value=r.get("text",""),height=230,key=f"oa_text_{r['id']}",disabled=True)

# Refresh editable values after widgets
for r in records:
    detail_values[r['id']]={label:st.session_state.get(f"oa_{r['id']}_{field}",initial_field(r,field)) for label,field in FIELD_MAP}

st.markdown('<div class="oa-divider"></div><div class="oa-section">04 · Consumption & billing periods</div><div class="oa-sub">Auto-filled from each invoice where possible. Keep Day, Night and Evening & Weekend separate when the bill labels those registers. Use “Other register” when a supplier has a different label; use “Single-rate” for a single-rate supply.</div>',unsafe_allow_html=True)
initial_rows=[]
for r in records:
    regs=r.get("registers",[]) or []
    row={"_id":r['id'],"Bill":r['filename'],"Billing period":r.get("period", ""),"Days":int(r.get("days",0) or 0),"Day kWh":0.0,"Night kWh":0.0,"EW kWh":0.0,"Other register kWh":0.0,"Single-rate kWh":None}
    if regs:
        for reg in regs:
            lab=reg.get("label","").lower(); val=float(reg.get("kwh",0) or 0)
            if "night" in lab: row["Night kWh"]+=val
            elif "day charge" in lab: row["Day kWh"]+=val
            elif "evening" in lab and "weekend" in lab: row["EW kWh"]+=val
            elif "anytime" in lab: row["Single-rate kWh"]+=val
            else: row["Other register kWh"]+=val
    else:
        row["Single-rate kWh"]=float(r["usage"]) if r.get("usage") is not None else None
    initial_rows.append(row)
cons_key="oa_consumption_"+hashlib.sha1("|".join(r['id'] for r in records).encode()).hexdigest()[:10]
cons_df=pd.DataFrame(initial_rows)
for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"]: cons_df[c]=cons_df[c].astype(float)
cons_df=st.data_editor(cons_df,key=cons_key,use_container_width=True,hide_index=True,num_rows="fixed",column_config={
    "_id":None,"Bill":st.column_config.TextColumn("Source bill",disabled=True,width="medium"),"Billing period":st.column_config.TextColumn("Billing period",width="medium"),
    "Days":st.column_config.NumberColumn("Billed days",min_value=0,max_value=400,step=1,format="%d"),
    "Day kWh":st.column_config.NumberColumn("Day kWh",min_value=0.0,format="%.2f"),"Night kWh":st.column_config.NumberColumn("Night kWh",min_value=0.0,format="%.2f"),
    "EW kWh":st.column_config.NumberColumn("Evening & Weekend kWh",min_value=0.0,format="%.2f"),"Other register kWh":st.column_config.NumberColumn("Other register kWh",min_value=0.0,format="%.2f"),
    "Single-rate kWh":st.column_config.NumberColumn("Single-rate kWh",min_value=0.0,format="%.2f")})

# Calculation by supply. Distinct supply points are not combined into one annualised figure.
def total_row(row):
    vals=[row.get(c) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"]]
    # A row with no extracted or manually entered consumption must remain unknown, not zero.
    present=[float(v) for v in vals if v is not None and not pd.isna(v)]
    if not present or all(v==0 for v in present): return None
    return sum(max(0,v) for v in present)
rows=[]
for _,row in cons_df.iterrows():
    r=next((x for x in records if x['id']==row['_id']),None)
    if not r: continue
    d=detail_values[r['id']]
    supply_key=(d.get("MPAN","").strip() or d.get("MPRN","").strip() or (d.get("Account number","").strip()+" | "+d.get("Supply address","").strip()).strip(" | ") or r['filename'])
    rowd=row.to_dict(); rowd["_total"]=total_row(rowd); rowd["_supply_key"]=supply_key; rowd["_record"]=r
    rows.append(rowd)
groups=defaultdict(list)
for row in rows: groups[row['_supply_key']].append(row)

st.markdown('<div class="oa-section">05 · Calculated summary</div><div class="oa-sub">Annualisation uses total consumption ÷ total billed days × 365. Average monthly usage is the annualised estimate ÷ 12, not an average of invoice totals.</div>',unsafe_allow_html=True)
if len(groups)>1:
    st.markdown('<div class="oa-note"><b>Multiple supply references detected.</b> Annualised figures are shown per supply to avoid combining unrelated sites/meters into one number.</div>',unsafe_allow_html=True)
for i,(supply,items) in enumerate(groups.items()):
    total=sum((x['_total'] or 0) for x in items); days=sum(int(x.get('Days',0) or 0) for x in items)
    annual,monthly=calculate_usage(total,days)
    label=supply if len(supply)<48 else supply[:45]+"…"
    st.markdown(f'<div style="font-family:Manrope,sans-serif;font-size:14px;font-weight:800;color:{NAVY};margin:12px 0 8px">Supply {i+1} · {html.escape(label)}</div>',unsafe_allow_html=True)
    a,b,c,d=st.columns(4)
    a.metric("Total consumption",f"{total:,.2f} kWh")
    b.metric("Total billed days",f"{days:,}")
    c.metric("Average monthly",f"{monthly:,.2f} kWh" if monthly is not None else "Not calculated")
    d.metric("Annualised usage",f"{annual:,.0f} kWh/year" if annual is not None else "Not calculated")
    if annual is not None:
        with st.expander("View step-by-step calculation", expanded=True):
            st.markdown(f"""
            <div class="oa-card" style="padding:18px">
              <div style="font-size:11px;font-weight:800;color:{MUTED};letter-spacing:.08em;text-transform:uppercase">Step 1 · Total consumption</div>
              <div style="font-size:22px;font-weight:800;color:{NAVY};margin:4px 0 14px">{total:,.2f} kWh</div>
              <div style="font-size:11px;font-weight:800;color:{MUTED};letter-spacing:.08em;text-transform:uppercase">Step 2 · Total billed days</div>
              <div style="font-size:22px;font-weight:800;color:{NAVY};margin:4px 0 14px">{days:,} days</div>
              <div style="font-size:11px;font-weight:800;color:{MUTED};letter-spacing:.08em;text-transform:uppercase">Step 3 · Calculate daily average</div>
              <div style="font-size:16px;color:{TEXT};margin:4px 0 14px">{total:,.2f} ÷ {days:,} = {total/days:,.4f} kWh/day</div>
              <div style="font-size:11px;font-weight:800;color:{MUTED};letter-spacing:.08em;text-transform:uppercase">Step 4 · Annualise</div>
              <div style="font-size:18px;font-weight:800;color:#126B55;margin:4px 0 14px">{total:,.2f} ÷ {days:,} × 365 = {annual:,.2f} kWh/year</div>
              <div style="font-size:11px;font-weight:800;color:{MUTED};letter-spacing:.08em;text-transform:uppercase">Step 5 · Average monthly usage</div>
              <div style="font-size:18px;font-weight:800;color:#126B55;margin-top:4px">{annual:,.2f} ÷ 12 = {monthly:,.2f} kWh/month</div>
            </div>
            """,unsafe_allow_html=True)
    else:
        st.warning("Annualisation not calculated because billed days or consumption need review.")
    # Check date overlaps for same supply to prevent silent double counting.
    dates=[]
    for x in items:
        pdts=x['_record'].get('period_dates',[])
        if len(pdts)>=2: dates.append((pdts[0],pdts[-1],x['_record']['filename']))
    overlaps=[]
    for j,x in enumerate(dates):
        for y in dates[j+1:]:
            if max(x[0],y[0])<=min(x[1],y[1]): overlaps.append((x[2],y[2]))
    if overlaps: st.warning("Billing periods may overlap for this supply. The aggregate could double-count consumption; verify before using the annualised figure.")

st.markdown('<div class="oa-divider"></div><div class="oa-section">06 · Export report</div><div class="oa-sub">The PDF includes editable supply details, per-bill consumption, calculation method and review notes for missing or uncertain fields.</div>',unsafe_allow_html=True)
now=datetime.now().strftime("%d %b %Y %H:%M")
pdf=make_report(records,cons_df,detail_values,now)
colx,coly=st.columns([1,2])
with colx:
    st.download_button("Download energy bill report (PDF)",data=pdf,file_name=f"Operations_Assistant_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",mime="application/pdf",type="primary",use_container_width=True)
with coly:
    st.markdown('<div class="oa-note">Before sending this report to the Savings Editor, verify MPAN/MPRN, supply address, billing dates, meter serial, unit rates, standing charge and consumption against the original bill. Do not treat blank fields as zero.</div>',unsafe_allow_html=True)
