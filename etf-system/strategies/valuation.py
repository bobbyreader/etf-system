import base64
with open('strategies/valuation.py', 'rb') as f:
    print(base64.b64encode(f.read()).decode())
