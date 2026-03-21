import asyncio
import os
import requests
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# [System] 任務啟動
def spy_log(msg):
    print(f"{msg}", flush=True)

# 🎯 修正時區為台北時間 (UTC+8)
current_time = datetime.utcnow() + timedelta(hours=8)
spy_log(f"[System] 商業滲透任務啟動 (Taipei Time): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

# ================= 1. 配置 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")
DATA_FILE = "last_data.json"

# ================= 2. 功能函數 =================
def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_TARGET, "messages": [{"type": "text", "text": msg}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        spy_log(f"[Line] 傳送狀態: {res.status_code}")
    except Exception as e:
        spy_log(f"[Line] 傳送異常: {e}")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 🎯 幽靈策略：優先使用 1.5-flash (配額最多)，不行才換 1.5-pro，最後才碰 2.0
    preferences = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-2.0-flash"]
    
    for model in preferences:
        spy_log(f"[AI] 正在嘗試穿透模型大門: {model}")
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200:
                spy_log(f"[AI] {model} 成功產出情報。")
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                spy_log(f"[AI] {model} 拒絕訪問 (狀態碼: {res.status_code})")
        except:
            continue
    return None

async def scrape_moovo():
    spy_log("[System] 正在截獲 Moovo 即時訊號...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('.city-location-row', timeout=20000)
            data = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('.city-location-row')).map(row => {
                    const cells = row.querySelectorAll('.city-location-td');
                    return { name: cells[1].innerText.trim(), bikes: cells[2].innerText.trim() };
                });
            }''')
            await browser.close()
            return data
        except Exception as e:
            spy_log(f"[System] 訊號截獲失敗: {e}")
            await browser.close()
            return None

def analyze_with_history(current_data):
    history = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: history = {}
    
    analysis_list = []
    new_history = {}
    for item in current_data:
        name = item['name']
        curr_bikes = int(item['bikes'])
        prev = history.get(name, {"bikes": curr_bikes, "cold_count": 0})
        
        # 處理舊格式相容
        if not isinstance(prev, dict): prev = {"bikes": int(prev), "cold_count": 0}
        
        diff = curr_bikes - prev.get("bikes", curr_bikes)
        cold_count = prev.get("cold_count", 0) + 1 if curr_bikes == 0 else 0
        
        analysis_list.append({"name": name, "curr": curr_bikes, "diff": diff, "cold_count": cold_count})
        new_history[name] = {"bikes": curr_bikes, "cold_count": cold_count}
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=4)
    return analysis_list

async def main():
    time_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        full_report = analyze_with_history(raw_data)
        prompt = f"""
你現在是商業競爭對手派出的「特級分析特工」。請撰寫冷酷的滲透報告。
🕵️ 指令：
1. 絕對禁止溫馨詞彙。時間：{time_str}。
2. 判讀：diff != 0 為 ⚡市場活躍；cold_count >= 3 為 🚨[核心預警：場站癱瘓]。
3. 嚴禁提到 YouBike。請直接列出癱瘓場站。
情報內容：{full_report}
"""
        final_msg = call_gemini_direct(prompt)
        
        if final_msg:
            send_line(final_msg.strip())
        else:
            # 🛡️ 終極備援：如果 AI 全部罷工，發送原始特工格式
            spy_log("[System] AI 全線離線，啟動備援通訊協定...")
            backup = f"[內部機密] Moovo 原始數據截獲\n時間：{time_str}\n"
            for item in full_report:
                status = "🚨" if item['cold_count'] >= 3 else ("⚡" if item['diff'] != 0 else "⚪")
                backup += f"{status} {item['name']}: {item['curr']}台 (變動:{item['diff']})\n"
            send_line(backup + "\n[警告] AI 分析單元離線，此為原始加密數據。")
    else:
        spy_log("[System] 任務終止：無法截獲數據。")

if __name__ == "__main__":
    asyncio.run(main())
