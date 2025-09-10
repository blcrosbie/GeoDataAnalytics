def add_leading_zeros_county(num):
    if num < 10:
        return f'00{num}'
    elif num < 100:
        return f'0{num}'
    else:
        return str(num)

def add_leading_zeros_place(num):
    if num < 10:
        return f'0000{num}'
    elif num < 100:
        return f'000{num}'
    elif num < 1000:
        return f'00{num}'
    elif num < 10000:
        return f'0{num}'
    else:
        return str(num)