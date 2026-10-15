def login(user):
    return True

def home(user):
    login(user)
    return checkout(user.cart, user)
