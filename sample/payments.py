def check_balance(user):
    return True

def charge_card(user, amount):
    if check_balance(user):
        return True
    return False

def pay(user, amount):
    return charge_card(user, amount)

def checkout(cart, user):
    return pay(user, cart.total)

def refund(user, amount):
    return charge_card(user, -amount)
