import asyncio
import os
import requests
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# [System] 任務日誌輸出
def spy_log(msg): print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8) 校正
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
        spy_log(f"[Line] 狀態: {res.status_code}")
    except: spy_log("[Line] 傳輸失敗")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 🎯 偵測並嘗試可用模型
    preferences = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-2.0-flash"]
    for model in preferences:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200: return res.json()['candidates'][0]['content']['parts'][0]['text']
        except: continue
    return None

async def scrape_moovo():
    spy_log("[System] 正在截獲 Moovo 即時數據...")
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
    
    analysis_list = []
    new_history = {}
    for item in current_data:
        name = item['name']
        curr_bikes = int(item['bikes'])
        prev = history.get(name)
        
        if isinstance(prev, dict):
            prev_bikes = prev.get("bikes", curr_bikes)
            prev_cold = prev.get("cold_count", 0)
        else:
            prev_bikes = int(prev) if prev is not None else curr_bikes
            prev_cold = 0
            
        diff = curr_bikes - prev_bikes
        cold_count = prev_cold + 1 if curr_bikes == 0 else 0
        analysis_list.append({"name": name, "curr": curr_bikes, "diff": diff, "cold_count": cold_count})
        new_history[name] = {"bikes": curr_bikes, "cold_count": cold_count}
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=4)
    return analysis_list

# ================= 3. 主流程 =================
async def main():
    time_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%H:%M")
    raw_data = await scrape_moovo()
    
    legend = "【圖例說明】\n🚨 連續3次無車(癱瘓)\n⚡ 車輛流動中\n⚪ 無變動\n(冷區 = 場站0台，表示營運缺口)\n"
    
    if raw_data:
        full_report = analyze_with_history(raw_data)
        
        prompt = f"""
你現在是商業分析特工。請用冷酷專業口吻撰寫 Moovo 報告。
🕵️ 指令：
1. **身份**：冷淡。時間：{time_str}。
2. **極簡化**：開頭必須包含以下圖例：\n{legend}
3. **格式**：每站一行。格式：圖標 站名:台數 (較上次:變動|冷:計數)。
4. **判讀**：diff!=0 ⚡；cold_count>=3 🚨。
5. **語言**：100% 繁體中文。嚴禁提到 YouBike。
情報：{full_report}
"""
        final_msg = call_gemini_direct(prompt)
        
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip())
        else:
            # 🎯 📡 備援模式：加入 AI 罷工提示與極簡繁體格式
            spy_log("[System] AI 離線，啟動備援報告...")
            backup = f"【⚠️ AI 罷工休息中 (配額限制)】\n{legend}\n時間 {time_str}\n"
            for item in full_report:
                icon = "🚨" if item['cold_count'] >= 3 else ("⚡" if item['diff'] != 0 else "⚪")
                diff_sym = f"{'+' if item['diff']>0 else ''}{item['diff']}"
                backup += f"{icon}{item['name']}:{item['curr']}台 (較上次:{diff_sym}|冷:{item['cold_count']})\n"
            send_line(backup)
    else: spy_log("[System] 偵察失敗")

if __name__ == "__main__":
    asyncio.run(main())
