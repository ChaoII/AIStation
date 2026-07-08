import requests, json

BASE = "http://127.0.0.1:8001/api/v1"

# Login - try with various field combinations
for payload in [
    {"username": "admin", "password": "123456"},
    {"username": "admin", "password": "123456", "grant_type": "password"},
]:
    r = requests.post(f"{BASE}/system/auth/login", json=payload)
    print(f"Payload {payload}: status={r.status_code}, body={r.text[:200]}")
    if r.status_code == 200:
        data = r.json()
        if data.get("code") == 0:
            token = data.get("data", {}).get("access_token", "")
            if token:
                print(f"TOKEN: {token[:50]}...")
                h = {"Authorization": f"Bearer {token}"}
                r2 = requests.get(f"{BASE}/annotation/dataset/list?page_no=1&page_size=100", headers=h)
                print(f"Dataset list: {r2.status_code}")
                for ds in r2.json().get("data", {}).get("items", []):
                    if "dd" in ds.get("name", "").lower():
                        print(f"\n数据集: {ds['name']} (ID={ds['id']})")
                        for t in ds.get("tasks", []):
                            print(f"  任务 ID={t['id']}, task_type={t['task_type']}, status={t['status']}, name={t.get('name','')}")
                break
