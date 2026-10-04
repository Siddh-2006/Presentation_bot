import requests
import json

resp = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "gemma2:2b",
        "messages": [{"role": "user", "content": "What is the return policy?"}],
        "stream": True
    },
    stream=True
)

for raw_line in resp.iter_lines():
    if raw_line:
        print(raw_line.decode('utf-8'))
