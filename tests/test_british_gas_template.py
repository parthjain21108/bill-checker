from bill_parser import parse_bill, calculate_usage

def test_british_gas_inline_meter_row_extracts_usage_and_rate():
    text = """
    British Gas
    DAVID CLIFF PROPERTY SERVICES LIMITED
    Account number 604166635
    Site Address
    Ashleigh, Terrace Road South, Binfield
    BRACKNELL, Berkshire, RG42 4DS
    Your business electricity bill
    Billing period: 15 August 2026 to 14 September 2026
    Your Fixed Price Energy Plan
    Details of charges
    Meter ID 2513336182
    Unit Charge
    5534 READ 14 Aug 2026 5840 READ 14 Sep 2026 306.00 24.830p £75.98
    Standing Charge 31.00 days at 64.520p £20.00
    """
    result = parse_bill(text, "fixture.pdf", "synthetic OCR text", 4)
    assert result["supplier"] == "British Gas"
    assert result["usage"] == 306.0
    assert result["rates"][0]["rate"] == 24.83
    assert result["standing"] == "64.52"
    assert result["days"] == 31
    annual, monthly = calculate_usage(result["usage"], result["days"])
    assert round(annual) == 3603
    assert round(monthly) == 300

def test_missing_usage_is_not_a_confirmed_zero():
    result = parse_bill("British Gas\nAccount number 123456789\n", "empty.pdf", "OCR", 1)
    assert result["usage"] is None
