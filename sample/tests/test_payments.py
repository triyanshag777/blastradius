from payments import pay, charge_card, refund

def test_pay():
    assert pay("u", 10)

def test_charge_card():
    assert charge_card("u", 5)

def test_refund():
    assert refund("u", 5)
