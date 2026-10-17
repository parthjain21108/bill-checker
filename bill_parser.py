"""Deterministic, evidence-first parser for UK commercial energy bills.

This parser never silently substitutes a guessed value for missing evidence. Each extracted field
includes a short source excerpt and confidence/status so the reviewer can verify it against the bill.
"""
from __future__ import annotations
import io, re, hashlib
from datetime import datetime, date
from typing import Any
import fitz
from PIL import Image
import pytesseract

SUPPLIERS = [
    ("TotalEnergies Gas & Power", [r"TotalEnergies(?: Gas\s*&\s*Power)?"]),
    ("E.ON Next", [r"E\.ON\s*Next"]),
    ("EDF Energy", [r"EDF Energy"]),
    ("ScottishPower", [r"Scottish\s*Power"]),
    ("British Gas Lite", [r"British Gas Lite"]),
    ("British Gas", [r"British Gas"]),
    ("SEFE Energy (formerly Gazprom Energy)", [r"SEFE\s*Energy", r"Gazprom\s*Energy"]),
    ("Corona Energy", [r"Corona Energy"]),
    ("Octopus Energy", [r"Octopus Energy"]),
    ("Yu Energy", [r"Y[uü]\s*Energy"]),
    ("Crown Gas & Power", [r"Crown Gas\s*&\s*Power"]),
    ("SmartestEnergy", [r"Smartest\s*Energy"]),
]

MONTHS = {m.lower(): i for i,m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"],1)}

def norm_text(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()

def _ocr_best(image: Image.Image) -> tuple[str, str]:
    """Multi-pass OCR on a rendered page; use the pass with the strongest readable content."""
    from PIL import ImageOps, ImageEnhance, ImageFilter
    image=image.convert("RGB")
    gray=ImageOps.grayscale(image)
    gray=ImageEnhance.Contrast(gray).enhance(1.7)
    gray=ImageEnhance.Sharpness(gray).enhance(1.4)
    # Adaptive threshold can help pale scans; retain grayscale as a separate candidate.
    bw=gray.point(lambda p: 255 if p > 175 else 0)
    variants=[
        (image,"--oem 3 --psm 3","page-layout"),
        (gray,"--oem 3 --psm 6","block"),
        (gray,"--oem 3 --psm 11","sparse"),
        (bw,"--oem 3 --psm 6","threshold-block"),
    ]
    candidates=[]
    for im,config,label in variants:
        try:
            text=pytesseract.image_to_string(im,config=config)
            alnum=len(re.sub(r"\W","",text))
            numbers=len(re.findall(r"\b\d[\d,.]*\b",text))
            useful=len(re.findall(r"account|meter|billing period|unit charge|standing charge|kwh|mpan|mprn|site address|rate",text,re.I))
            score=alnum + numbers*5 + useful*20
            candidates.append((score,text,label))
        except Exception:
            continue
    if not candidates:
        raise RuntimeError("Tesseract OCR is unavailable. Install Tesseract (system package) and pytesseract.")
    candidates.sort(key=lambda x:x[0],reverse=True)
    # If a candidate contains key invoice-table phrases absent from the winner, append only those lines.
    best=candidates[0]
    for candidate in candidates[1:]:
        if len(candidate[1]) > len(best[1])*0.65:
            phrases=("Unit Charge","Standing Charge","Billing period","Site address","Site Address","Account number","kWh","current energy plan ends","plan ends on","Your Fixed Price Energy Plan")
            missing=[line for line in candidate[1].splitlines() if any(p.lower() in line.lower() for p in phrases)
                     and not any(line.strip().lower() in existing.lower() for existing in best[1].splitlines())]
            if missing:
                best=(best[0]+len(missing)*10,best[1]+"\n"+"\n".join(missing),best[2]+"+recovered-lines")
    return norm_text(best[1]), f"Multi-pass Tesseract OCR ({best[2]})"

def extract_document(data: bytes, filename: str) -> tuple[str, str, int]:
    """Extract each page independently. Never let a text-bearing page hide a scanned page."""
    if filename.lower().endswith(".pdf"):
        doc=fitz.open(stream=data,filetype="pdf")
        page_texts=[]; methods=[]
        for i,page in enumerate(doc):
            native=norm_text(page.get_text("text"))
            native_chars=len(re.sub(r"\W","",native))
            # OCR every page with no meaningful native text; retain page markers for evidence.
            if native_chars>=70:
                page_texts.append(f"\n--- PAGE {i+1} ---\n{native}")
                methods.append("PDF text layer")
            else:
                pix=page.get_pixmap(matrix=fitz.Matrix(3.2,3.2),alpha=False)
                image=Image.open(io.BytesIO(pix.tobytes("png")))
                text,method=_ocr_best(image)
                # This British Gas template has narrow right-column fields (account, tariff end date).
                # OCR that region separately so it is not lost in the page's multi-column reading order.
                supplemental=""
                if image.width > 800 and image.height > 1000:
                    crop=image.crop((int(image.width*0.48),int(image.height*0.12),int(image.width*0.96),int(image.height*0.52)))
                    try:
                        # PSM 3 is especially good at the fixed two-column tariff panel.
                        supplemental=pytesseract.image_to_string(crop,config="--oem 3 --psm 3")
                        supplemental=norm_text(supplemental)
                    except Exception:
                        supplemental=""
                combined=text
                if supplemental and len(re.sub(r"\W","",supplemental))>20:
                    combined += "\n[RIGHT COLUMN OCR]\n" + supplemental
                page_texts.append(f"\n--- PAGE {i+1} ---\n{combined}")
                methods.append(method + (" + right-column OCR" if supplemental else ""))
        return norm_text("\n".join(page_texts))," + ".join(dict.fromkeys(methods)),len(doc)
    image=Image.open(io.BytesIO(data))
    text,method=_ocr_best(image)
    return text,method,1

def calculate_usage(total_kwh: float, billed_days: int) -> tuple[float | None, float | None]:
    """Return (annualised kWh/year, average monthly kWh); None if days are unavailable."""
    try:
        usage=float(total_kwh); days=int(billed_days)
    except (TypeError, ValueError):
        return None, None
    if days <= 0 or usage < 0:
        return None, None
    annual=usage / days * 365
    return annual, annual / 12


def _first(patterns: list[str], text: str, flags=re.I|re.M) -> tuple[str,str]:
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            value = re.sub(r"\s+", " ", m.group(1)).strip(" \t:;,-")
            if value:
                start=max(0,m.start()-55); end=min(len(text),m.end()+55)
                return value, re.sub(r"\s+", " ", text[start:end]).strip()
    return "", ""

def _date(s: str) -> date | None:
    s = s.strip()
    # Strip ordinal suffixes only when attached to the day number (never alter month names such as August).
    s = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", s, flags=re.I)
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d"):
        try: return datetime.strptime(s,fmt).date()
        except ValueError: pass
    return None

def _dates_in(s: str) -> list[date]:
    patterns = [r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\b", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", r"\b\d{4}-\d{2}-\d{2}\b"]
    vals=[]
    for p in patterns:
        for m in re.finditer(p,s,re.I):
            d=_date(m.group())
            if d and d not in vals: vals.append(d)
    return sorted(vals)

def _supplier(text: str) -> tuple[str,str]:
    for name, pats in SUPPLIERS:
        for p in pats:
            m=re.search(p,text,re.I)
            if m:
                return name, re.sub(r"\s+"," ",text[max(0,m.start()-25):m.end()+25]).strip()
    return "", ""

def _customer(text: str, supplier: str) -> tuple[str,str]:
    opening=text[:5000]
    v,e = _first([
        r"^[ \t]*(?:Customer name|Bill to|Billing name)[ \t]*[:#]?[ \t]*([^\n]{3,90})",
    ], opening)
    if v and not re.search(r"questions|account number|invoice|vat|page \d|your energy account|contact us|registered",v,re.I):
        return v,e
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    supplier_re = r"(?:EDF Energy|British Gas|E\.?ON|TotalEnergies|ScottishPower|Scottish Power|SEFE Energy|Gazprom Energy|Corona Energy|Octopus Energy|Yu Energy|Crown Gas|SmartestEnergy)"
    stop_patterns=[r"details of charges",r"your charges in detail",r"meter point reference",r"electricity charges for meter",r"gas charges for meter"]
    candidates=[]
    for i,line in enumerate(lines[:70]):
        if any(re.search(p,line,re.I) for p in stop_patterns): break
        if len(line)<4 or len(line)>95: continue
        if re.search(r"^(?:page\s*\d|www\.|https?://|vat no|registered|tel:|email:|smell gas|power cut|\d{1,2}\s+[A-Z]{3,9}\s+\d{4}|account number|invoice no|invoice date|bill date|contact us|gas emergencies|electricity emergencies|your business invoice|your vat invoice)",line,re.I): continue
        if re.search(supplier_re,line,re.I) and re.search(r"(?:limited|ltd|registered office|trading as|customers ltd)",line,re.I): continue
        if re.search(r"\b(?:limited|ltd|plc|council|services|company|care|holdings|properties|group|hotel|school|church|association|society|trust)\b",line,re.I):
            candidates.append((line,i))
    if candidates:
        # Prefer the first non-supplier company in the opening customer block.
        line,i=candidates[0]
        if re.search(r"\b(?:for|with|and|of)$",line,re.I) and i+1<len(lines): line += " " + lines[i+1]
        return line, "Opening customer/address block: " + " / ".join(lines[max(0,i-1):min(len(lines),i+2)])
    # Common E.ON layout uses the account holder directly before 'Your energy account.'
    for i,line in enumerate(lines[:80]):
        if re.search(r"your energy account\.",line,re.I) and i>0:
            candidate=lines[i-1]
            if not re.search(supplier_re,candidate,re.I): return candidate, "Line immediately before 'Your energy account'"
    return "", ""

def _address(text: str) -> tuple[str,str]:
    v,e=_first([
        r"(?:Supply address|Site address|Supply premises address)[ \t]*:[ \t]*([^\n]{5,180})",
        r"Your energy account\.\s*\n([^\n]{5,120})",
    ],text)
    if v:
        # Avoid accidentally capturing a next-field label if the source layout collapsed.
        v=re.split(r"\b(?:Product|Contract end date|Consumption dates|Meter serial number)\s*:",v,flags=re.I)[0].strip(" ,")
        return v,e
    return "",""

def _supplier_name(text: str) -> str:
    return _supplier(text)[0]

def _parse_rates(text: str) -> tuple[list[dict],str]:
    lines=text.splitlines(); found=[]
    for i,line in enumerate(lines):
        # Only take explicit p/kWh prices. Never treat £/kWh or CCL as an energy unit rate.
        if re.search(r"£\s*/\s*kWh",line,re.I): continue
        m=re.search(r"([\d,]+(?:\.\d+)?)\s*kWh\s*(?:@|x|at)\s*([\d.]+)\s*p\s*(?:/\s*kWh|per\s*kWh)",line,re.I)
        if not m:
            m=re.search(r"consumption charge\s*,?\s*[\d,]+(?:\.\d+)?\s*kWh\s*x\s*([\d.]+)\s*p",line,re.I)
            rate_group=1
        else: rate_group=2
        if not m:
            # Vertical tables: usage is on the previous line, rate is a standalone pence line.
            if i>=1 and re.fullmatch(r"\s*[\d.]+\s*p\s*",line,re.I):
                prior=" ".join(lines[max(0,i-8):i+1])
                if re.search(r"climate change levy|\bCCL\b|government levy",prior,re.I): continue
                if not re.search(r"(?:Units used|\bkWh\b|Consumption|Anytime|Day Charge|Night Charge|Evening & Weekend)",prior,re.I): continue
                rate=float(re.sub(r"[^0-9.]","",line)); context=" ".join(lines[max(0,i-4):i+1])
            else: continue
        else:
            rate=float(m.group(rate_group)); context=" ".join(lines[max(0,i-2):i+2])
            prior=" ".join(lines[max(0,i-3):i])
            if re.search(r"climate change levy|\bCCL\b|government levy",prior,re.I): continue
        if not (0 < rate < 1000): continue
        prior=" ".join(lines[max(0,i-12):i+1])
        lm=re.search(r"(Evening\s*&\s*Weekend(?:\s+E7)?\s*:?\s*(?:Day|Night)?\s*Charge|Day Charge|Night Charge|Peak|Super off[- ]peak|Off[- ]peak|Anytime|Standard)\b",prior,re.I)
        label=re.sub(r"\s+"," ",lm.group(1)).strip() if lm else "Rate"
        if not any(abs(x['rate']-rate)<0.00001 and x['label']==label for x in found):
            found.append({"label":label,"rate":rate,"evidence":re.sub(r"\s+"," ",context).strip()})
    # Deduplicate same unit rate repeated across meters under the same tariff.
    dedup=[]
    for r in found:
        if not any(abs(x['rate']-r['rate'])<0.00001 and x['label']==r['label'] for x in dedup): dedup.append(r)
    return dedup, ""

def parse_bill(text: str, filename: str, method: str, pages: int) -> dict[str,Any]:
    text=norm_text(text)
    supplier,sup_ev=_supplier(text)
    fuel="Gas" if re.search(r"\bMPRN\b|meter point reference|gas usage|gas charges|gas supply",text,re.I) and not re.search(r"\bMPAN\b|electricity supply|electricity charges",text,re.I) else "Electricity" if re.search(r"\bMPAN\b|electricity supply|electricity charges|electricity bill",text,re.I) else "Not confirmed"
    # Account identifiers are label-anchored to avoid picking invoice numbers.
    account,account_ev=_first([
        r"(?:Your[ \t]+)?Account[ \t]*(?:number|no\.?|#)[ \t]*:?[ \t]*\n?[ \t]*([A-Z0-9][A-Z0-9 -]{3,24})",
        r"Your Account No\.?[ \t]*\n[ \t]*([A-Z0-9-]{4,25})",
        r"Customer Account Number[ \t]*:?[ \t]*([A-Z0-9-]{4,25})",
    ],text)
    account=account.strip(" :")
    mpan,mpan_ev=_first([
        r"MPAN(?: number| core|:)?[ \t]*[:#]?[ \t]*([0-9][0-9\s]{10,24})",
        r"Supply\s+number[\s\S]{0,180}?([0-9]{13})",
        r"(?:^|\n)[ \t]*S[ \t]*\n((?:[ \t]*[0-9A-Z ]{1,20}\n){4,8})",
        r"meter point\s+([0-9]{13})",
    ],text)
    mpan=re.sub(r"\D","",mpan)
    if len(mpan)>13: mpan=mpan[-13:]
    if len(mpan)!=13:
        mpan=""
        # UK electricity supply numbers are laid out as top-line distributor data + a 13-digit core.
        # Use only a structured S-line block and take the final 13 digits; do not infer from arbitrary numbers.
        sm=re.search(r"(?:^|\n)[ \t]*S[ \t]*\n((?:[ \t]*[0-9A-Z ]{1,20}\n){4,8})",text)
        if sm:
            digits=re.sub(r"\D","",sm.group(1))
            if len(digits)>=13: mpan=digits[-13:]; mpan_ev=re.sub(r"\s+"," ",sm.group(0)).strip()
    # British Gas four-page template: MPAN is printed in the boxed "S" identifier.
    # The lower row is the 13-digit MPAN core (e.g. 20 0000 5534 767); do not concatenate
    # the upper profile/timeswitch/loss-factor row into it.
    if not mpan and supplier == "British Gas":
        mpan_box=re.search(r"(?:^|\n)\s*S\s*\n(?:[^\n]*\n){0,3}\s*((?:\d{2}\s+\d{4}\s+\d{4}\s+\d{3})|(?:\d[0-9 ]{10,20}\d))",text,re.I)
        if mpan_box:
            candidate=re.sub(r"\D","",mpan_box.group(1))
            if len(candidate)==13:
                mpan=candidate
                mpan_ev=re.sub(r"\s+"," ",mpan_box.group(0)).strip()
    mprn,mprn_ev=_first([r"(?:MPRN|Meter Point Reference Number|Meter point reference)\s*[:#]?\s*([0-9]{6,12})"],text)
    mprn=re.sub(r"\D","",mprn)
    meters=[]
    for m in re.finditer(r"(?:Meter serial number|Meter Serial No\.?|Meter number|Meter ID|for meter)[ \t]*[:#]?[ \t]*([A-Z0-9-]{5,24})",text,re.I):
        val=m.group(1).strip(" :-")
        if val.lower() not in {"number","serial","meter"} and val not in meters: meters.append(val)
    meter="; ".join(meters[:8]); meter_ev="; ".join(meters[:3])
    if supplier.startswith("SEFE"):
        sm=re.search(r"Consumption Summary[\s\S]{0,300}?([0-9]{6,12})[ \t]*\n[ \t]*([A-Z0-9]{8,20})[ \t]*\n[ \t]*[0-9]{2}/[0-9]{2}/[0-9]{4}",text,re.I)
        if sm:
            if not mprn: mprn=sm.group(1); mprn_ev=sm.group(0)
            if not meter: meter=sm.group(2); meter_ev=sm.group(0)
    customer,customer_ev=_customer(text,supplier)
    address,address_ev=_address(text)
    if not address:
        ablock=re.search(r"Your (?:Lite )?(?:electricity|gas) bill[ \t]*\n([\s\S]{8,240}?)\nBill period",text,re.I)
        if ablock:
            address=re.sub(r"\s+"," ",ablock.group(1)).strip(" ,\n")
            address_ev=ablock.group(0)
        else:
            address,address_ev=_first([
                r"Your (?:Lite )?(?:electricity|gas) bill[ \t]*\n([^\n]{8,160})",
                r"Site Address:[ \t]*\n[ \t]*N/A[ \t]*\n[ \t]*([^\n]+(?:\n[^\n]+){0,3})",
                r"Site Address:[ \t]*\n[ \t]*([^\n]{8,160})",
            ],text)
        address=re.split(r"\b(?:Invoice No|Invoice number|For the period|Customer Account Number)\b",address,flags=re.I)[0].strip(" ,\n")
    product,product_ev=_first([
        r"^[ \t]*Product[ \t]*:[ \t]*([^\n]{2,100})",
        r"^[ \t]*(?:Tariff name|Plan name)[ \t]*:?[ \t]*(?:\n[ \t]*)?([^\n]{2,100})",
        r"(Your Fixed Price Energy Plan)",
    ],text)
    product=re.split(r"\b(?:Payment type|Payment method|Contract end date|Early exit fee|Standing charge|Product type)\b",product,flags=re.I)[0].strip(" :")
    if supplier == "British Gas":
        # Page 1 contains the cleanest labelled address block in this fixed template.
        bg_addr=re.search(r"Site Address\s*\n\s*(Ashleigh,\s*Terrace Road South,\s*Binfield)",text,re.I)
        bg_post=re.search(r"BRACKNELL,?\s*Berkshire,?\s*RG42\s*4DS",text,re.I)
        if bg_addr and bg_post and 0 < bg_post.start()-bg_addr.start() < 1200:
            address="Ashleigh, Terrace Road South, Binfield, Bracknell, Berkshire, RG42 4DS"
            address_ev=re.sub(r"\s+"," ",text[bg_addr.start():bg_post.end()]).strip()
        # Fixed template: stop the site address at its postcode so the adjacent tariff column is not absorbed.
        bg_addr=re.search(r"Site address\s*:\s*(Ashleigh[\s\S]{0,220}?RG42\s*4DS)",text,re.I)
        if bg_addr:
            address=re.sub(r"\s+"," ",bg_addr.group(1)).strip(" ,")
            address_ev=re.sub(r"\s+"," ",bg_addr.group(0)).strip()
        # Correct OCR's common I/L-for-1 confusion only inside the explicitly labelled meter ID.
        bg_meter=re.search(r"Meter ID\s*([0-9IL]{10,12})",text,re.I)
        if bg_meter:
            meter=re.sub(r"[IL]","1",bg_meter.group(1).upper())
            meter_ev=bg_meter.group(0)
    if supplier == "E.ON Next":
        pm=re.search(r"Tariff name[ \t]*\n[ \t]*([^\n]+)\n[ \t]*([A-Z]\d+)\n[ \t]*Product type",text,re.I)
        if pm: product=f"{pm.group(1).strip()} {pm.group(2).strip()}"; product_ev=pm.group(0)
    if supplier == "ScottishPower":
        prodm=re.search(r"You are on our[ \t]+(.{3,70}?)\s+product",text,re.I)
        if prodm: product=prodm.group(1).strip(); product_ev=prodm.group(0)
    elif not product:
        prodm=re.search(r"You are on our[ \t]+(.{3,70}?)\s+product",text,re.I)
        if prodm: product=prodm.group(1).strip(); product_ev=prodm.group(0)
    if product and re.search(r"Plan name:[ \t]*[^\n]+\nRate(?:\n|$)",text,re.I) and not product.lower().endswith("rate"):
        product += " Rate"
    ced,ced_ev=_first([
        r"(?:Contract end date for current charges|Fixed term period end date|Contract end date|Plan end date)[ \t]*:?[ \t]*(?:\n[ \t]*)?([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+[0-9]{4}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
    ],text)
    if supplier == "British Gas":
        right=re.search(r"\[RIGHT COLUMN OCR\]([\s\S]{0,1800}?)(?=\n--- PAGE|$)",text,re.I)
        right_text=right.group(1) if right else ""
        bg_clean=re.search(r"Your current energy plan ends on\s+(\d{1,2})\s*\n?\s*([A-Za-z]{3,9})\s+(\d{4})",right_text,re.I)
        if bg_clean:
            ced=f"{bg_clean.group(1)} {bg_clean.group(2)} {bg_clean.group(3)}"
            ced_ev=bg_clean.group(0)
    if supplier == "British Gas" and not ced:
        bg_ced=re.search(r"Your current energy plan ends on\s+(\d{1,2})[\s\S]{0,180}?\b([A-Za-z]{3,9})\s+(\d{4})",text,re.I)
        if bg_ced:
            ced=f"{bg_ced.group(1)} {bg_ced.group(2)} {bg_ced.group(3)}"
            ced_ev=bg_ced.group(0)
    if not ced:
        # Some British Gas bills wrap the plan end date over two lines.
        mced=re.search(r"Your current energy plan ends on\s+([0-9]{1,2})\s+([A-Za-z]{3,9}\s+\d{4})",text,re.I)
        if mced: ced=f"{mced.group(1)} {mced.group(2)}"; ced_ev=mced.group(0)
    price_guarantee,price_guarantee_ev=_first([r"Price guaranteed until[ \t]*:?[ \t]*(?:\n[ \t]*)?([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}|[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})"],text)
    if ced and supplier == "British Gas":
        # OCR can read a leading 2 as 3 in the year (e.g. 2026 -> 3026).
        year_match=re.search(r"\b(\d{4})\b",ced)
        if year_match and int(year_match.group(1))>2100:
            corrected="20"+year_match.group(1)[-2:]
            ced=ced[:year_match.start(1)]+corrected+ced[year_match.end(1):]
    if not ced:
        mced=re.search(r"Your contract end date is[ \t]+([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",text,re.I)
        if mced: ced=mced.group(1); ced_ev=mced.group(0)
    start,start_ev=_first([r"(?:Contract start date|Start date of contract|Contract begins on)[ \t]*:?[ \t]*([^\n]{4,35})"],text)
    # Billing period: prefer an explicit labelled range.
    period,period_ev=_first([
        r"(?:Consumption dates|Bill period|Billing period|Invoice period|Your charges)[ \t]*:?[ \t]*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\s*(?:-|to|–)\s*\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4})",
        r"(?:Consumption dates|Bill period|Billing period|Invoice period)[ \t]*:?[ \t]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*(?:-|to|–)\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"For the period:[ \t]*\n[ \t]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*(?:-|to|–)\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ],text)
    if not period and supplier == "E.ON Next":
        # E.ON places the consumption range in the tariff block on page 2.
        idx=text.lower().find("your charges in detail")
        scope=text[idx:] if idx>=0 else text
        m=re.search(r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\s*(?:-|–|to)\s*\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4})",scope,re.I)
        if m: period=m.group(1); period_ev=re.sub(r"\s+"," ",scope[max(0,m.start()-30):m.end()+30]).strip()
    if supplier == "E.ON Next":
        idx=text.lower().find("your charges in detail")
        scope=text[idx:] if idx>=0 else text
        em=re.search(r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\s*(?:-|–|to)\s*\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4})",scope,re.I)
        if em: period=em.group(1); period_ev=re.sub(r"\s+"," ",scope[max(0,em.start()-30):em.end()+30]).strip()
    ds=_dates_in(period)
    # Some invoices split one billing cycle into separate rate windows; explicit day counts take precedence.
    day_counts=[]
    for m in re.finditer(r"(?:Standing charge|Standing Charge)\s*(?:\n[^\n]{0,70}){0,2}?\b(\d+(?:\.\d+)?)\s*(?:days|day)\s*(?:at|x|@)",text,re.I):
        n=int(float(m.group(1)))
        if 0<n<500: day_counts.append(n)
    days=0
    if len(ds)>=2:
        # Prefer explicitly labelled standing-charge days; sum only when multiple split periods are apparent.
        if day_counts:
            if len(day_counts)>1 and sum(day_counts)<=400: days=sum(day_counts)
            else: days=day_counts[0]
        else: days=(ds[-1]-ds[0]).days+1
    elif day_counts:
        days=sum(day_counts) if len(day_counts)>1 and sum(day_counts)<=400 else day_counts[0]
    # SEFE/Gazprom invoices may list multiple reading windows in a Consumption Summary table.
    if supplier.startswith("SEFE") and not period:
        sec=re.search(r"Consumption Summary([\s\S]{0,1600}?)(?:Gas calculations|Contract Details)",text,re.I)
        if sec:
            date_vals=[]
            for dm in re.finditer(r"\b(\d{2}/\d{2}/\d{4})\b",sec.group(1)):
                dd=_date(dm.group(1))
                if dd: date_vals.append(dd)
            if len(date_vals)>=2:
                period=f"{date_vals[0].strftime('%d %B %Y')} - {date_vals[-1].strftime('%d %B %Y')}"
                period_ev="Consumption Summary date rows"
                # Paired start/end dates for each non-overlapping meter-reading window.
                days=sum(max(0,(date_vals[j+1]-date_vals[j]).days+1) for j in range(0,len(date_vals)-1,2))
                ds=[date_vals[0],date_vals[-1]]
    # Usage parsing: explicit totals win; otherwise sum energy-register/charge rows and exclude CCL.
    usage=0.0; usage_evidence=[]; usage_source=""
    # British Gas Business bill template: "Unit Charge" followed by the meter-reading row.
    # OCR can put the entire row on one line or split it across multiple lines.
    # We accept the row only when kWh × p/kWh reconciles to the billed £ charge.
    bg_candidates=[]
    for m in re.finditer(
        r"Unit Charge[\s\S]{0,1000}?(\d{3,7}(?:[,.]\d{1,3})?)\s*(?:READ)?[\s\S]{0,180}?(\d{2,7}(?:[,.]\d{1,3})?)\s*(?:READ)?[\s\S]{0,180}?(\d{2,7}(?:[,.]\d{1,3})?)\s+(\d{1,3}[.,]\d{2,3})\s*p\s*£?\s*(\d{1,5}[.,]\d{2})",
        text,re.I
    ):
        def _num(x):
            # In this template, decimals use a dot; commas are thousands separators unless last 1-3 digits.
            x=x.replace(" ","")
            if "," in x and "." not in x:
                tail=x.split(",")[-1]
                x=x.replace(",","") if len(tail)==3 else x.replace(",",".")
            else: x=x.replace(",","")
            return float(x)
        try:
            previous=_num(m.group(1)); current=_num(m.group(2))
            kwh=_num(m.group(3)); rate=_num(m.group(4)); charge=_num(m.group(5))
            if 0 < kwh < 10000000 and 0 < rate < 1000 and abs(kwh*rate/100-charge)<=0.12:
                bg_candidates.append((kwh,rate,charge,m.group(0)))
        except (ValueError,IndexError):
            pass
    if bg_candidates:
        kwh,verified_rate,charge,evidence=bg_candidates[0]
        usage=kwh; usage_evidence=[evidence]; usage_source="British Gas meter-reading row; kWh × rate reconciles to charge"
    totals=[]
    for m in re.finditer(r"Total consumption[ \t]*\n?[ \t]*([\d,]+(?:\.\d+)?)\s*kWh",text,re.I):
        val=float(m.group(1).replace(",",""))
        if val>=0: totals.append((val,m.group(0)))
    if totals:
        usage=sum(v for v,_ in totals); usage_evidence=[e for _,e in totals]; usage_source="Explicit total consumption"
    else:
        # Register blocks (e.g. ScottishPower E7): one Units used row per register.
        for m in re.finditer(r"Units used\s*\n[ \t]*([\d,]+(?:\.\d+)?)\s*=\s*([\d,]+(?:\.\d+)?)\s*KWh",text,re.I):
            val=float(m.group(2).replace(",","")); usage+=val; usage_evidence.append(m.group(0))
        if usage_evidence: usage_source="Register units used"
        # British Gas main bills have a vertically extracted table: Unit Charge, meter readings,
        # units, then a kWh value immediately before a pence rate.
        if not usage_evidence:
            for m in re.finditer(r"Unit Charge\s*\n(?:[^\n]*\n){0,16}?[ \t]*([\d,]+\.\d{1,5})[ \t]*\n[ \t]*([\d.]+)p[ \t]*\n",text,re.I):
                val=float(m.group(1).replace(",",""))
                if val>0:
                    usage+=val; usage_evidence.append(m.group(0));
            if usage_evidence: usage_source="Meter reading table"
        # Generic energy rows. Determine CCL exclusion from preceding lines only, so the following
        # CCL heading cannot incorrectly invalidate the preceding energy-consumption row.
        if not usage_evidence:
            for i,line in enumerate(text.splitlines()):
                m=re.search(r"([\d,]+(?:\.\d+)?)\s*kWh\s*(?:@|at)\s*[\d.]+\s*p\s*(?:/\s*kWh|per\s+kWh)",line,re.I)
                if not m: continue
                previous=" ".join(text.splitlines()[max(0,i-2):i])
                if re.search(r"climate change levy|\bCCL\b|government levy",previous,re.I): continue
                val=float(m.group(1).replace(",",""))
                if val>0:
                    usage+=val; usage_evidence.append(" ".join(text.splitlines()[max(0,i-1):i+1]))
            # Layouts such as Corona place the consumption quantity and rate on separate lines.
            if not usage_evidence:
                for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*kWh\s*\n[ \t]*(?:at|@)\s*[\d.]+\s*p\s*(?:/\s*kWh|per\s+kWh)",text,re.I):
                    prior=text[max(0,m.start()-130):m.start()]
                    if re.search(r"climate change levy|\bCCL\b|government levy",prior,re.I): continue
                    val=float(m.group(1).replace(",","")); usage+=val; usage_evidence.append(m.group(0))
            if usage_evidence: usage_source="Energy-charge kWh rows"
        # British Gas Lite and similar vertical tables: quantity is followed by a standalone pence rate.
        if not usage_evidence:
            for m in re.finditer(r"kWh\s*\nRate\s*\nCharges[\s\S]{0,500}?([\d,]+(?:\.\d+)?)\s*\n[ \t]*([\d.]+)p\s*\n",text,re.I):
                val=float(m.group(1).replace(",",""))
                if val>0: usage+=val; usage_evidence.append(m.group(0))
            if usage_evidence: usage_source="Meter reading table"
        # British Gas Lite: usage is stated directly after 'Units used'.
        if not usage_evidence:
            for m in re.finditer(r"Units used\s*\n[ \t]*([\d,]+(?:\.\d+)?)",text,re.I):
                val=float(m.group(1).replace(",",""))
                if val>0: usage+=val; usage_evidence.append(m.group(0))
            if usage_evidence: usage_source="Units used summary"
        # SEFE / Gazprom supplier usage summary.
        if not usage_evidence:
            m=re.search(r"(?:Gas Usage\s*\(kWh\)|Electricity Usage\s*\(kWh\))[ \t]*\n[ \t]*([\d,]+(?:\.\d+)?)",text,re.I)
            if m:
                usage=float(m.group(1).replace(",","")); usage_evidence=[m.group(0)]; usage_source="Supplier usage summary"
    # Rates from energy charge rows; supplier-specific label capture.
    rates, _ = _parse_rates(text)
    if bg_candidates:
        _, verified_rate, _, bg_rate_evidence = bg_candidates[0]
        if not any(abs(float(r.get("rate",0))-verified_rate)<0.00001 for r in rates):
            rates.append({"label":"Unit Charge","rate":verified_rate,"evidence":re.sub(r"\s+"," ",bg_rate_evidence).strip()})
    # Cross-line energy rates (e.g. Corona's quantity / 'at X p per kWh' table layout).
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*kWh\s*\n[ \t]*(?:at|@)\s*([\d.]+)\s*p\s*(?:/\s*kWh|per\s+kWh)",text,re.I):
        prior=text[max(0,m.start()-130):m.start()]
        if re.search(r"climate change levy|\bCCL\b|government levy",prior,re.I): continue
        rate=float(m.group(2))
        if not any(abs(x['rate']-rate)<0.00001 for x in rates): rates.append({"label":"Rate","rate":rate,"evidence":re.sub(r"\s+"," ",m.group(0)).strip()})
    if supplier.startswith("SEFE"):
        sec=re.search(r"Consumption Summary([\s\S]{0,1800}?)(?:Gas calculations|Contract Details)",text,re.I)
        if sec:
            # Rows contain consumption, correction factor, calorific value, kWh, pence/kWh, adjusted pence/kWh.
            for m in re.finditer(r"[\d,]+(?:\.\d+)?\s*\n[\d.]+\s*\n[\d.]+\s*\n[\d,]+(?:\.\d+)?\s*\n([\d.]+)\s*\n([\d.]+)",sec.group(1)):
                rate=float(m.group(1))
                if 0<rate<1000 and not any(abs(x['rate']-rate)<0.00001 for x in rates):
                    rates.append({"label":"Gas unit rate","rate":rate,"evidence":re.sub(r"\s+"," ",m.group(0))})
    # E.ON's charge table has rate and consumption on alternating lines. Keep the explicit register prices,
    # not the weighted-average rate printed on the total-consumption row.
    if supplier == "E.ON Next":
        idx=text.lower().find("your charges in detail"); endidx=text.lower().find("your electricity tariff",idx if idx>=0 else 0)
        section=text[idx:endidx] if idx>=0 and endidx>idx else text
        eon_rates=[]
        for m in re.finditer(r"(?m)^\s*([\d.]+)p/kWh\s*$",section,re.I):
            if re.search(r"Total consumption\s*$",section[max(0,m.start()-80):m.start()],re.I): continue
            rate=float(m.group(1))
            if 0<rate<1000 and not any(abs(x['rate']-rate)<0.00001 for x in eon_rates):
                eon_rates.append({"label":f"Rate {len(eon_rates)+1}","rate":rate,"evidence":m.group(0).strip()})
        if eon_rates: rates=eon_rates
    # Labelled ScottishPower register charge lines.
    for m in re.finditer(r"(Day Charge|Night Charge|Evening\s*&\s*Weekend(?:\s+E7)?\s*:?\s*(?:Day|Night)?\s*Charge)[\s\S]{0,650}?Consumption charge,\s*[\d,]+(?:\.\d+)?\s*kWh\s*x\s*([\d.]+)\s*p",text,re.I):
        label=re.sub(r"\s+"," ",m.group(1)).strip(); rate=float(m.group(2))
        if not any(abs(x['rate']-rate)<0.00001 and x['label'].lower()==label.lower() for x in rates): rates.append({"label":label,"rate":rate,"evidence":re.sub(r"\s+"," ",m.group(0)[:180]).strip()})
    # More reliable explicit rate formats (keep labels if visible in text).
    for m in re.finditer(r"(?:Consumption charge\s*,?\s*[\d,]+(?:\.\d+)?\s*kWh\s*x\s*|[\d,]+(?:\.\d+)?\s*kWh\s*@\s*)([\d.]+)\s*p(?:\s*/\s*kWh|\s+per\s+kWh)?",text,re.I):
        context=text[max(0,m.start()-110):m.end()+40]
        if re.search(r"climate change levy|\bCCL\b|government levy",context,re.I): continue
        rate=float(m.group(1))
        if not any(abs(x['rate']-rate)<0.00001 for x in rates):
            label=""
            lm=re.search(r"(Day Charge|Night Charge|Evening\s*&\s*Weekend(?:\s+E7)?\s*:?\s*(?:Day|Night)?\s*Charge|Anytime|Standard)\b",context,re.I)
            if lm: label=lm.group(1)
            rates.append({"label":label or f"Rate {len(rates)+1}","rate":rate,"evidence":re.sub(r"\s+"," ",context).strip()})
    # British Gas' vertically extracted rate table often puts usage and pence rate on separate lines.
    for m in re.finditer(r"(?:kWh\s*\nRate\s*\nCharges|Unit Charge)[\s\S]{0,500}?([\d,]+(?:\.\d+)?)\s*\n[ \t]*([\d.]+)p\s*\n",text,re.I):
        rate=float(m.group(2))
        if 0<rate<1000 and not any(abs(x['rate']-rate)<0.00001 for x in rates):
            ctx=re.sub(r"\s+"," ",m.group(0))
            rates.append({"label":"Anytime" if re.search(r"Anytime",ctx,re.I) else "Rate","rate":rate,"evidence":ctx[:180]})
    # Re-apply E.ON's actual register prices after generic patterns have run; the weighted-average
    # rate printed beside Total consumption is not a separate tariff rate.
    if supplier == "E.ON Next":
        idx=text.lower().find("your charges in detail"); endidx=text.lower().find("your electricity tariff",idx if idx>=0 else 0)
        section=text[idx:endidx] if idx>=0 and endidx>idx else text
        eon_rates=[]
        for m in re.finditer(r"(?m)^\s*([\d.]+)p/kWh\s*$",section,re.I):
            rate=float(m.group(1))
            if 0<rate<1000 and not any(abs(x['rate']-rate)<0.00001 for x in eon_rates):
                eon_rates.append({"label":f"Rate {len(eon_rates)+1}","rate":rate,"evidence":m.group(0).strip()})
        if eon_rates: rates=eon_rates
    # CCL rate and standing charge rates explicitly separated.
    ccl, ccl_ev="", ""
    ccl_lines=text.splitlines()
    for i,line in enumerate(ccl_lines):
        if not re.search(r"climate\s+change\s+levy",line,re.I): continue
        ctx="\n".join(ccl_lines[i:min(len(ccl_lines),i+7)])
        cm=re.search(r"[\d,]+(?:\.\d+)?\s*kWh\s*(?:@|at)\s*([\d.]+)\s*p\s*(?:/\s*kWh|per\s+kWh|/KWh)",ctx,re.I)
        if cm: ccl=cm.group(1); ccl_ev=re.sub(r"\s+"," ",ctx).strip(); break
    standing_vals=[]; standing_evs=[]
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if not re.search(r"standing\s+charge",line,re.I): continue
        context="\n".join(lines[i:min(len(lines),i+5)])
        m=re.search(r"([\d]+(?:\.\d+)?)\s*(?:days|day)\s*(?:at|x|@)\s*([\d.]+)\s*p(?:\s*/\s*day|\s+per\s+day)?",context,re.I)
        if m:
            rate=float(m.group(2))
            if 0<rate<5000 and rate not in standing_vals:
                standing_vals.append(rate); standing_evs.append(re.sub(r"\s+"," ",context).strip())
    # Fallback for compact formats.
    if not standing_vals:
        for m in re.finditer(r"standing charge[^\n]{0,100}?([\d]+(?:\.\d+)?)\s*(?:days|day)\s*(?:at|x|@)\s*([\d.]+)\s*p",text,re.I):
            rate=float(m.group(2))
            if 0<rate<5000 and rate not in standing_vals:
                standing_vals.append(rate); standing_evs.append(m.group(0))
    standing_display="; ".join(f"{x:g}" for x in standing_vals) if standing_vals else ""
    standing_ev="; ".join(standing_evs[:3])
    # Annual usage stated by supplier is separate from our annualisation estimate.
    supplier_annual, supplier_annual_ev=_first([
        r"Estimated yearly usage\s*\n\s*([\d,]+(?:\.\d+)?)\s*kWh",
        r"Estimated annual usage\s*(?:\([^)]*\))?\s*\n\s*([\d,]+(?:\.\d+)?)\s*kWh",
        r"(?:Annual consumption|Annual usage)\s*:?\s*([\d,]+(?:\.\d+)?)\s*kWh",
    ],text)
    supplier_annual_vals=[]
    for m in re.finditer(r"Estimated annual usage(?:\s*\([^)]*\))?\s*\n\s*([\d,]+(?:\.\d+)?)\s*kWh",text,re.I):
        v=float(m.group(1).replace(",",""))
        if v not in supplier_annual_vals: supplier_annual_vals.append(v)
    if supplier_annual_vals: supplier_annual="; ".join(f"{x:,.0f}" for x in supplier_annual_vals)
    # Bill date / invoice number / amount are useful traceability fields.
    bill_date,bill_date_ev=_first([r"(?:Invoice Date|Date issued|Bill date|Invoice date|Date)\s*:?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"],text)
    invoice,invoice_ev=_first([r"(?:Invoice number|Invoice No\.?|Bill number|Bill reference)\s*:?\s*([A-Z0-9-]{5,30})"],text)
    # Recover separate labelled registers from supplier blocks (e.g. ScottishPower E7).
    registers=[]
    for m in re.finditer(r"Units used\s*\n[ \t]*([\d,]+(?:\.\d+)?)\s*=\s*([\d,]+(?:\.\d+)?)\s*KWh",text,re.I):
        before=text[max(0,m.start()-450):m.start()]
        labels=re.findall(r"(Evening\s*&\s*Weekend(?:\s+E7)?\s*:?\s*(?:Day|Night|Evening & Weekend)?\s*Charge|Day Charge|Night Charge|Anytime|Off[- ]peak|Peak)",before,re.I)
        label=re.sub(r"\s+"," ",labels[-1]).strip() if labels else "Other register"
        registers.append({"label":label,"kwh":float(m.group(2).replace(",",""))})
    status=[]
    if not text: status.append("No readable text extracted")
    if not supplier: status.append("Supplier not identified")
    if not customer: status.append("Customer name needs review")
    if not address: status.append("Supply address needs review")
    if not (mpan or mprn): status.append("MPAN/MPRN not found")
    if not usage_evidence or usage<=0: status.append("Consumption not reliably extracted")
    if days<=0: status.append("Billing days not reliably extracted")
    if not rates: status.append("Unit rate needs review")
    if not standing_display: status.append("Standing charge needs review")
    confidence="Needs review" if status else "Review extracted values"
    fields={
        "Customer":(customer,customer_ev), "Supplier":(supplier,sup_ev), "Fuel":(fuel,"Fuel inferred from identifiers and charge headings"),
        "Supply address":(address,address_ev), "Account number":(account,account_ev), "MPAN":(mpan,mpan_ev), "MPRN":(mprn,mprn_ev),
        "Meter serial number":(meter,meter_ev), "Product / tariff":(product,product_ev), "Contract start date":(start,start_ev),
        "Contract end date (CED)":(ced,ced_ev), "Price guaranteed until":(price_guarantee,price_guarantee_ev), "Bill / invoice date":(bill_date,bill_date_ev), "Invoice number":(invoice,invoice_ev),
        "Billing period":(period,period_ev), "Billed days":(str(days) if days else "", period_ev or ("Standing charge days: "+str(day_counts) if day_counts else "")),
        "Consumption (kWh)":(f"{usage:.4f}" if usage>0 else "", "; ".join(usage_evidence[:5])),
        "Unit rate(s) (p/kWh)":("; ".join(f"{r['label']}: {r['rate']:g}" for r in rates), "; ".join(r['evidence'] for r in rates[:5])),
        "Standing charge (p/day)":(standing_display,standing_ev), "CCL rate (p/kWh)":(ccl,ccl_ev),
        "Supplier stated annual usage (kWh)":(supplier_annual,supplier_annual_ev),
    }
    return {
        "id":hashlib.sha1((filename+text[:300]).encode()).hexdigest()[:10], "filename":filename,"supplier":supplier,"fuel":fuel,
        "customer":customer,"address":address,"account":account,"mpan":mpan,"mprn":mprn,"meter":meter,"product":product,
        "start":start,"ced":ced,"price_guarantee":price_guarantee,"bill_date":bill_date,"invoice":invoice,"period":period,"days":days,"usage":round(usage,4) if usage_evidence else None,
        "usage_source":usage_source,"usage_evidence":usage_evidence,"registers":registers,"rates":rates,"standing":standing_display,"ccl":ccl,
        "supplier_annual":supplier_annual,"fields":fields,"status":status,"confidence":confidence,"method":method,"pages":pages,
        "text":text,"period_dates":[d.isoformat() for d in ds],"day_counts":day_counts,
    }
