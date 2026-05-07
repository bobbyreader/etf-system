import base64
with open('backtest/bt_engine.py', 'rb') as f:
    print(base64.b64encode(f.read()).decode())
