import requests, json

BASE = "http://127.0.0.1:8001/api/v1"
r = requests.post(f"{BASE}/system/auth/login", data={"username": "admin", "password": "123456", "captcha_id": "", "captcha_code": ""})
token = r.json().get("data", {}).get("access_token", "")
if not token:
    print("Login failed:", r.text[:200])
    exit(1)

headers = {"Authorization": f"Bearer {token}"}
r = requests.get(f"{BASE}/annotation/dataset/list?page_no=1&page_size=100", headers=headers)
for ds in r.json().get("data", {}).get("items", []):
    if "dd" in ds.get("name", "").lower():
        print(f"Dataset: {ds['name']}")
        for t in ds.get("tasks", []):
            print(f"  {t['name']}: progress={t.get('progress','?')}, status={t['status']}")
