#!/usr/bin/env python3
import sys
import json
import hashlib
import time
import urllib.request

# ── 配置 ──────────────────────────────────────────
APP_ID    = "100003"
APP_KEY   = "38d2391985e2369a5fb8227d8e6cd5e5"
API_KEY = "121e73665f58457ba83a369fcedbd6f8.xDPzlqmQ4jQeFZUL"
URL       = "https://autoglm-api.zhipuai.cn/agentdr/v1/assistant/skills/web-search"

# ── Step 1: 使用直接配置的 API Key ──────────────────
token = f"Bearer {API_KEY}"

# ── Step 2: 读取搜索词 ────────────────────────────
query = "AI+测试领域 前沿技术 2026"

# ── Step 3: 生成签名 Headers ──────────────────────
timestamp = str(int(time.time()))
sign_data = f"{APP_ID}&{timestamp}&{APP_KEY}"
sign      = hashlib.md5(sign_data.encode("utf-8")).hexdigest()

# ── Step 4: 发起请求 ──────────────────────────────
payload = json.dumps({"queries": [{"query": query}]}).encode("utf-8")
headers = {
    "Authorization":    token,
    "Content-Type":     "application/json",
    "X-Auth-Appid":     APP_ID,
    "X-Auth-TimeStamp": timestamp,
    "X-Auth-Sign":      sign,
}

req = urllib.request.Request(URL, data=payload, headers=headers, method="POST")
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
