import base64
with open('web/server.py', 'rb') as f:
    print(base64.b64encode(f.read()).decode())
