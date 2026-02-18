# test_deepseek_fixed.py
import requests

key = "sk-6470e6afbcaa43ff9fbee0ea58acd271"
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

data = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": "You are a helpful farming assistant."},
        {"role": "user", "content": "How long do grapes take to grow?"}
    ]
}

response = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    json=data,
    headers=headers
)

print(f"Status: {response.status_code}")
print(response.json())
