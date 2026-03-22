import asyncio
import os
import requests
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# [System] 任務日誌
def spy_log(msg): print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8)
current_time_tp = datetime.utcnow() + timedelta(hours=8)
spy_log(f"[System] 偵察任務啟動: {current_time_tp.strftime('%Y-%m-%d %H:%M:%S')}")

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
    except: spy_log("[Line] 傳送失敗")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 嘗試多重路徑避開 404
    for model in ["models/gemini-1.5-flash", "models/gemini-2.0-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200: return res.json()['candidates'][0]['content']['parts'][0]['text']
        except: continue
    return None

async def scrape_moovo():
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
        except:
            await browser.close()
            return None

def analyze_with_history(current_data):
    history = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: history = json.load(f)
        except: history = {}
    
    changed = []
    unchanged = []
    new_history = {}

    for item in current_data:
        name = item['name']
        curr = int(item['bikes'])
        prev = history.get(name, {}).get("bikes", curr) if isinstance(history.get(name), dict) else int(history.get(name, curr))
        
        diff = curr - prev
        diff_str = f"{'+' if diff > 0 else ''}{diff}"
        
        station_info = {"name": name, "curr": curr, "diff": diff_str}
        
        if diff != 0:
            changed.append(station_info)
        else:
            unchanged.append(station_info)
        
        new_history[name] = {"bikes": curr}
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=4)
        
    return changed, unchanged

async def main():
    time_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%H:%M")
    raw_data = await scrape_moovo()
    
    if raw_data:
        changed, unchanged = analyze_with_history(raw_data)
        
        prompt = f"""
你現在是特級情報員。請撰寫 Moovo 監測報告。
🕵️ 指令：
1. **結構**：分兩區。第一區「⚡ 數據變動場站」，第二區「⚪ 無變動場站」。
2. **格式**：每站一行。站名:台數 (較上次:變動)。
3. **語言**：100% 繁體中文。嚴禁讚美，口吻冷酷。
4. **時間**：{time_str}。
情報內容：
變動站點：{changed}
穩定站點：{unchanged}
"""
        final_msg = call_gemini_direct(prompt)
        
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip())
        else:
            # 🎯 備援模式：手動分類並移除冷區
            spy_log("[System] AI 離線，啟動直覺分類備援模式...")
            report = f"【⚠️ AI 監控離線】時間 {time_str}\n\n"
            
            report += "⚡ 【數據變動場站】\n"
            if not changed: report += "   (無變動數據)\n"
            for item in changed:
                report += f"   {item['name']}: {item['curr']}台 (較上次: {item['diff']})\n"
            
            report += "\n⚪ 【無變動場站】\n"
            for item in unchanged:
                report += f"   {item['name']}: {item['curr']}台 (較上次: 0)\n"
                
            send_line(report)
    else: spy_log("[System] 抓取失敗")

if __name__ == "__main__":
    asyncio.run(main())
