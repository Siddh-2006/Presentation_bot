import requests

resp = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "gemma4:e2b",
        "messages": [{"role": "user", "content": "Say hello!"}],
        "stream": False
    }
)
print("Status Code:", resp.status_code)
print("Response JSON:", resp.text)
