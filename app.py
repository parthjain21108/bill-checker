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
    buff=io.BytesIO(); doc=SimpleDocTemplate(buff,pagesize=landscape(A4),rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=13*mm)
    ss=getSampleStyleSheet()
    ss.add(ParagraphStyle(name="OAeyebrow",parent=ss["Normal"],fontName="Helvetica-Bold",fontSize=7.5,leading=9,textColor=colors.HexColor(BLUE),spaceAfter=5))
    ss.add(ParagraphStyle(name="OATitle",parent=ss["Title"],fontName="Helvetica-Bold",fontSize=22,leading=25,textColor=colors.HexColor(NAVY),alignment=TA_LEFT,spaceAfter=4))
    ss.add(ParagraphStyle(name="OASub",parent=ss["Normal"],fontName="Helvetica",fontSize=8.5,leading=11,textColor=colors.HexColor(MUTED),spaceAfter=8))
    ss.add(ParagraphStyle(name="OAHead",parent=ss["Heading2"],fontName="Helvetica-Bold",fontSize=11,leading=14,textColor=colors.HexColor(NAVY),spaceBefore=10,spaceAfter=5))
    ss.add(ParagraphStyle(name="OABody",parent=ss["BodyText"],fontName="Helvetica",fontSize=7.5,leading=9.5,textColor=colors.HexColor(TEXT)))
    ss.add(ParagraphStyle(name="OATiny",parent=ss["BodyText"],fontName="Helvetica",fontSize=6.5,leading=8,textColor=colors.HexColor(MUTED)))
    ss.add(ParagraphStyle(name="OAHeaderCell",parent=ss["BodyText"],fontName="Helvetica-Bold",fontSize=7,leading=8.5,textColor=colors.white))
    ss.add(ParagraphStyle(name="OAMetric",parent=ss["BodyText"],fontName="Helvetica-Bold",fontSize=14,leading=16,textColor=colors.HexColor(BLUE),alignment=TA_CENTER))
    ss.add(ParagraphStyle(name="OAMetricLabel",parent=ss["BodyText"],fontName="Helvetica-Bold",fontSize=6.5,leading=8,textColor=colors.HexColor(NAVY),alignment=TA_CENTER))
    P=lambda v,st="OABody":Paragraph(str(v),ss[st])
    story=[P("OPERATIONS ASSISTANT  /  COMMERCIAL ENERGY-BILL REVIEW","OAeyebrow"),P("Energy Bill Analysis","OATitle"),P(f"Extracted from uploaded documents · Generated {generated_at} · Verify flagged fields against the source bills before use.","OASub")]
    story += [P("Supply details","OAHead")]
    detail_rows=[[P("<b>Bill / source</b>","OAHeaderCell"),P("<b>Customer / supplier</b>","OAHeaderCell"),P("<b>Fuel / supply address</b>","OAHeaderCell"),P("<b>Identifiers</b>","OAHeaderCell"),P("<b>Product / contract end</b>","OAHeaderCell"),P("<b>Rates & charges</b>","OAHeaderCell")]]
    for r in records:
        d=detail_values[r['id']]
        ident=f"Account: {esc(d.get('Account number',''))}<br/>MPAN: {esc(d.get('MPAN',''))}<br/>MPRN: {esc(d.get('MPRN',''))}<br/>Meter: {esc(d.get('Meter serial number',''))}"
        rates=esc(d.get('Unit rates (p/kWh)',''))+f"<br/>Standing: {esc(d.get('Standing charge (p/day)',''))} p/day<br/>CCL: {esc(d.get('CCL rate (p/kWh)',''))} p/kWh"
        detail_rows.append([P(esc(r['filename'])),P(f"{esc(d.get('Customer',''))}<br/>{esc(d.get('Supplier',''))}"),P(f"{esc(d.get('Fuel',''))}<br/>{esc(d.get('Supply address',''))}"),P(ident),P(f"{esc(d.get('Product / tariff',''))}<br/>CED: {esc(d.get('Contract end date (CED)',''))}<br/>Price guaranteed until: {esc(d.get('Price guaranteed until',''))}"),P(rates)])
    t=Table(detail_rows,colWidths=[37*mm,43*mm,48*mm,45*mm,39*mm,47*mm],repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(NAVY)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor(LINE)),("BACKGROUND",(0,1),(-1,-1),colors.white),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.append(t); story.append(P("Consumption by bill","OAHead"))
    rows=[[P("<b>Bill / period</b>","OAHeaderCell"),P("<b>Days</b>","OAHeaderCell"),P("<b>Day kWh</b>","OAHeaderCell"),P("<b>Night kWh</b>","OAHeaderCell"),P("<b>EW kWh</b>","OAHeaderCell"),P("<b>Other register</b>","OAHeaderCell"),P("<b>Single-rate kWh</b>","OAHeaderCell"),P("<b>Total kWh</b>","OAHeaderCell")]]
    for _,r in consumption_df.iterrows():
        total=sum(float(r.get(c,0) or 0) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"])
        def regfmt(v):
            try: return "—" if abs(float(v or 0)) < 0.000001 else fmt_num(v)
            except (TypeError,ValueError): return "—"
        rows.append([P(f"{esc(r.get('Bill',''))}<br/>{esc(r.get('Billing period',''))}"),P(str(int(r.get("Days",0) or 0))),P(regfmt(r.get("Day kWh",0))),P(regfmt(r.get("Night kWh",0))),P(regfmt(r.get("EW kWh",0))),P(regfmt(r.get("Other register kWh",0))),P(regfmt(r.get("Single-rate kWh",0))),P(fmt_num(total))])
    ct=Table(rows,colWidths=[51*mm,14*mm,23*mm,24*mm,22*mm,28*mm,30*mm,25*mm],repeatRows=1)
    ct.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(BLUE)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor(LINE)),("BACKGROUND",(0,1),(-1,-1),colors.white),("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,1),(-1,-1),"RIGHT"),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.append(ct)
    # Group-level calculations are based on the editable consumption table.
    totals=defaultdict(lambda:{"usage":0.0,"days":0,"bills":0})
    for _,r in consumption_df.iterrows():
        bid=r.get("_id"); rec=next((x for x in records if x['id']==bid),None)
        if not rec: continue
        d=detail_values[rec['id']]
        key=d.get("MPAN") or d.get("MPRN") or d.get("Account number") or rec['filename']
        total=sum(float(r.get(c,0) or 0) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"])
        totals[key]["usage"]+=total; totals[key]["days"]+=int(r.get("Days",0) or 0); totals[key]["bills"]+=1
    story.append(P("Calculated summary","OAHead"))
    sr=[[P("<b>Supply reference</b>","OAHeaderCell"),P("<b>Bills</b>","OAHeaderCell"),P("<b>Total usage</b>","OAHeaderCell"),P("<b>Total billed days</b>","OAHeaderCell"),P("<b>Average monthly</b>","OAHeaderCell"),P("<b>Annualised estimate</b>","OAHeaderCell"),P("<b>Method</b>","OAHeaderCell")]]
    for key,v in totals.items():
        annual,monthly=calculate_usage(v['usage'],v['days'])
        sr.append([P(esc(key)),P(str(v['bills'])),P(f"{v['usage']:,.2f} kWh"),P(str(v['days'])),P(f"{monthly:,.2f} kWh" if monthly is not None else "Not calculated"),P(f"{annual:,.2f} kWh/year" if annual is not None else "Not calculated"),P("Total consumption ÷ total billed days × 365")])
    stbl=Table(sr,colWidths=[48*mm,15*mm,30*mm,28*mm,32*mm,34*mm,40*mm],repeatRows=1)
    stbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(NAVY)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor(LINE)),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.append(stbl)
    story += [Spacer(1,5*mm),P("Review notes","OAHead")]
    for r in records:
        row=consumption_df[consumption_df["_id"]==r["id"]]
        row_usage=sum(float(row.iloc[0].get(c,0) or 0) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"]) if not row.empty else r.get("usage",0)
        row_days=int(row.iloc[0].get("Days",0) or 0) if not row.empty else r.get("days",0)
        flags=current_review_flags(r,detail_values[r['id']],row_usage,row_days)
        if flags: story.append(P(f"<b>{esc(r['filename'])}:</b> {esc('; '.join(flags))}","OABody"))
        else: story.append(P(f"<b>{esc(r['filename'])}:</b> The parser found the core fields; source verification is still required.","OABody"))
    story += [Spacer(1,4*mm),P("Extraction is deterministic and evidence-first, not a guarantee of correctness. Empty fields mean the value was not reliably identified; they must not be treated as zero or inferred from another bill. Rates, billing days and register totals should be checked against the original invoice.","OATiny")]
    def footer(canvas,doc_):
        canvas.saveState(); w,h=landscape(A4); canvas.setStrokeColor(colors.HexColor(LINE)); canvas.line(12*mm,9*mm,w-12*mm,9*mm); canvas.setFont("Helvetica",6.5); canvas.setFillColor(colors.HexColor(MUTED)); canvas.drawString(12*mm,5*mm,"OPERATIONS ASSISTANT · ENERGY BILL REVIEW"); canvas.drawRightString(w-12*mm,5*mm,f"Page {doc_.page}"); canvas.restoreState()
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
    st.markdown("### Important")
    st.caption("This deployment runs on Streamlit Community Cloud. Uploaded bills and extracted text are processed by the hosted app. Use anonymised/test files unless cloud processing has been approved by your organisation.")
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
    row={"_id":r['id'],"Bill":r['filename'],"Billing period":r.get("period", ""),"Days":int(r.get("days",0) or 0),"Day kWh":0.0,"Night kWh":0.0,"EW kWh":0.0,"Other register kWh":0.0,"Single-rate kWh":0.0}
    if regs:
        for reg in regs:
            lab=reg.get("label","").lower(); val=float(reg.get("kwh",0) or 0)
            if "night" in lab: row["Night kWh"]+=val
            elif "day charge" in lab: row["Day kWh"]+=val
            elif "evening" in lab and "weekend" in lab: row["EW kWh"]+=val
            elif "anytime" in lab: row["Single-rate kWh"]+=val
            else: row["Other register kWh"]+=val
    else:
        row["Single-rate kWh"]=float(r.get("usage",0) or 0)
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
def total_row(row): return sum(max(0,float(row.get(c,0) or 0)) for c in ["Day kWh","Night kWh","EW kWh","Other register kWh","Single-rate kWh"])
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
    total=sum(x['_total'] for x in items); days=sum(int(x.get('Days',0) or 0) for x in items)
    annual,monthly=calculate_usage(total,days)
    label=supply if len(supply)<48 else supply[:45]+"…"
    st.markdown(f'<div style="font-family:Manrope,sans-serif;font-size:14px;font-weight:800;color:{NAVY};margin:12px 0 8px">Supply {i+1} · {html.escape(label)}</div>',unsafe_allow_html=True)
    a,b,c,d=st.columns(4)
    a.metric("Total consumption",f"{total:,.2f} kWh")
    b.metric("Total billed days",f"{days:,}")
    c.metric("Average monthly",f"{monthly:,.2f} kWh" if monthly is not None else "Not calculated")
    d.metric("Annualised usage",f"{annual:,.0f} kWh/year" if annual is not None else "Not calculated")
    st.caption(f"Calculation: {total:,.2f} kWh ÷ {days} days × 365 = {annual:,.2f} kWh/year." if annual is not None else "Annualisation not calculated because billed days were not reliably extracted or entered.")
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
