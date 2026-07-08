import requests, json

BASE = "http://127.0.0.1:8001/api/v1"

# Login
r = requests.post(f"{BASE}/system/auth/login", json={
    "username": "admin", "password": "123456",
    "captcha_id": "", "captcha_code": ""
})
token = r.json().get("data", {}).get("access_token", "")
if not token:
    print("Login failed")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# List datasets
r = requests.get(f"{BASE}/annotation/dataset/list?page_no=1&page_size=100", headers=headers)
datasets = r.json().get("data", {}).get("items", [])

for ds in datasets:
    if "dd" in ds.get("name", "").lower():
        print(f"数据集: {ds['name']} (ID={ds['id']})")
        tasks = ds.get("tasks", [])
        if not tasks:
            print("  (无关联标注任务)")
        for t in tasks:
            print(f"  任务: ID={t['id']}, 名称={t['name']}, 类型={t['task_type']}, 状态={t['status']}")
        break
else:
    print("未找到 dd 数据集")
