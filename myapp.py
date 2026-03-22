import asyncio
import os
import requests
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# [System] 任務日誌
def spy_log(msg): print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8) 校正
current_time_tp = (datetime.utcnow() + timedelta(hours=8)).strftime("%H:%M")
spy_log(f"[System] 偵察任務啟動: {current_time_tp}")

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
    # 🎯 根據偵察報告 (image_c0c88a) 更新精確路徑
    # 優先使用 2.5-flash，這是目前最新最穩定的節點
    target_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    
    for m in target_models:
        # 使用 v1beta 搭配正確的 Model ID
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200:
                spy_log(f"[AI] {m} 覺醒成功。")
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            elif res.status_code == 429:
                spy_log(f"[AI] {m} 頻率限制 (429)，請勿頻繁重試。")
            else:
                spy_log(f"[AI] {m} 狀態碼: {res.status_code}")
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
            await browser.close(); return None

def analyze_logic(current_data):
    history = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: history = json.load(f)
        except: history = {}
    
    changed, unchanged, new_history = [], [], {}
    max_abs_diff = 0
    
    for item in current_data:
        name = item['name']
        curr = int(item['bikes'])
        prev_data = history.get(name, {})
        prev = prev_data.get("bikes", curr) if isinstance(prev_data, dict) else int(prev_data)
        
        diff = curr - prev
        abs_diff = abs(diff)
        if abs_diff > max_abs_diff: max_abs_diff = abs_diff
        
        diff_str = f"{'+' if diff > 0 else ''}{diff}"
        info = {"name": name, "curr": curr, "diff": diff_str, "abs_diff": abs_diff}
        
        if diff != 0: changed.append(info)
        else: unchanged.append(info)
        new_history[name] = {"bikes": curr}

    for item in changed:
        if item['abs_diff'] == max_abs_diff and max_abs_diff > 0:
            item['hot'] = True
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=4)
    return changed, unchanged

async def main():
    raw_data = await scrape_moovo()
    if raw_data:
        changed, unchanged = analyze_logic(raw_data)
        prompt = f"""
你現在是冷酷特工分析官。請撰寫監測報告。
指令：
1. **結構**：先列「⚡ 變動場站」，後列「⚪ 穩定場站」。
2. **標註**：若場站數據中有 'hot':True，在名稱前加上 🔥。
3. **格式**：每站一行。站名:台數 (較上次:變動)。
4. **語言**：100% 繁體中文。嚴禁多餘廢話。時間：{current_time_tp}。
數據：變動:{changed}，穩定:{unchanged}
"""
        final_msg = call_gemini_direct(prompt)
        
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip())
        else:
            # 備援模式
            report = f"【📡 原始數據監測】時間 {current_time_tp}\n\n"
            report += "⚡ 【變動場站】\n"
            if not changed: report += " (無變動)\n"
            for i in changed:
                p = "🔥" if i.get('hot') else " "
                report += f" {p}{i['name']}:{i['curr']} (較上次:{i['diff']})\n"
            report += "\n⚪ 【穩定場站】\n"
            for i in unchanged: report += f"   {i['name']}:{i['curr']} (較上次:0)\n"
            send_line(report)
    else: spy_log("[System] 抓取失敗")

if __name__ == "__main__":
    asyncio.run(main())
