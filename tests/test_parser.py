"""Sanitised regression tests for the core parsing and annualisation rules.
Run with: python -m unittest discover -s tests
"""
import unittest
from bill_parser import parse_bill, calculate_usage

class ParserTests(unittest.TestCase):
    def test_edf_split_charge_periods_sum_energy_and_standing_days(self):
        text='''EDF Energy\nGlendale Court (Teignmouth) Ltd\nYour VAT invoice\nAccount number: A-7F9353E3\nYour charges: 01 April 2026 - 30 April 2026\nSupply number\nS\n03\n0393\nN12\n2200042504439\nSupply address: Glendale Muse, Second Drive, Teignmouth, TQ14 9JS\nElectricity used\n347.8000 kWh @ 43.930p/kWh\nStanding charge\n27 days @ 215.000p/day\nElectricity used\n52.4500 kWh @ 41.060p/kWh\nStanding charge\n4 days @ 200.000p/day\n'''
        r=parse_bill(text,'edf.pdf','text',1)
        self.assertEqual(r['supplier'],'EDF Energy')
        self.assertEqual(r['mpan'],'2200042504439')
        self.assertAlmostEqual(r['usage'],400.25,places=2)
        self.assertEqual(r['days'],31)
        self.assertIn('43.93',[str(x['rate']) for x in r['rates']])
        self.assertIn('215',r['standing'])

    def test_totalenergies_gas_kwh_and_mprn(self):
        text='''TotalEnergies Gas & Power Ltd\nCustomer Company Ltd\nYour Account No.\nA-12345678\nMeter Point Reference Number : 53690008\nSupply address: 1 Example Road, Leeds, LS1 1AA\nProduct: Fixed\nContract end date for current charges: 31 December 2026\nConsumption dates: 31 May 2026 - 29 June 2026\nMeter serial number: E016K0243419D6\nUnit Rate\n4961.8550 kWh @ 4.9900p/kWh\nGovernment Climate Change Levy\n4961.85500 kWh @ 0.80100 p/kWh\n'''
        r=parse_bill(text,'te.pdf','text',1)
        self.assertEqual(r['mprn'],'53690008')
        self.assertAlmostEqual(r['usage'],4961.855,places=3)
        self.assertEqual(r['days'],30)
        self.assertTrue(any(abs(x['rate']-4.99)<.001 for x in r['rates']))
        self.assertEqual(r['ced'],'31 December 2026')

    def test_eon_explicit_total_wins_and_weighted_rate_is_not_register_rate(self):
        text='''E.ON Next\nYour account number: A-CED623EC\nFor your electricity (on meter point 1300052181960)\nYour charges in detail.\nElectricity\nNext Smart Saver Fixed 12m (25th May 2026 - 24th June 2026)\n12.349p/kWh\n1.7 kWh\n17.702p/kWh\n12.3 kWh\n37.276p/kWh\n2.2 kWh\nTotal consumption\n16.3kWh @ 19.84p/kWh\nStanding charge\n31 days @ 64.432p/day\nPrice guaranteed until\n18 August 2026\n'''
        r=parse_bill(text,'eon.pdf','text',1)
        self.assertEqual(r['mpan'],'1300052181960')
        self.assertAlmostEqual(r['usage'],16.3,places=1)
        self.assertEqual(r['days'],31)
        self.assertEqual([round(x['rate'],3) for x in r['rates']],[12.349,17.702,37.276])
        self.assertEqual(r['price_guarantee'],'18 August 2026')

    def test_scottishpower_registers_are_kept_separate(self):
        text='''ScottishPower\nAccount number\n1611 8995 159\nKUCKOO OPS LTD\nSupply Address: 17 FOX STREET, PRESTON, PR1 2AB\nS\n04\n0327\n024\n16\n1001 3017\n775\nInvoice period 04 April 2026-22 May 2026\nEvening & Weekend E7 :Day Charge\nMeter number E12Z109433\nUnits used\n1153 = 1153 KWh (kilowatt-hrs) used\nConsumption charge, 1153 kWh x 32.670p =\nStanding charge, 49 days x 204.290p =\nEvening & Weekend E7 :Evening & Weekend Charge\nMeter number E12Z109433\nUnits used\n1704 = 1704 KWh (kilowatt-hrs) used\nConsumption charge, 1704 kWh x 24.310p =\nEvening & Weekend E7 :Night Charge\nMeter number E12Z109433\nUnits used\n859 = 859 KWh (kilowatt-hrs) used\nConsumption charge, 859 kWh x 21.990p =\n'''
        r=parse_bill(text,'sp.pdf','text',1)
        self.assertAlmostEqual(r['usage'],3716,places=1)
        self.assertEqual([x['kwh'] for x in r['registers']],[1153,1704,859])
        self.assertEqual(r['days'],49)

    def test_annualisation_formula_and_missing_days(self):
        annual,monthly=calculate_usage(400.25,31)
        self.assertAlmostEqual(annual,400.25/31*365,places=8)
        self.assertAlmostEqual(monthly,annual/12,places=8)
        self.assertEqual(calculate_usage(400.25,0),(None,None))

if __name__=='__main__': unittest.main()
