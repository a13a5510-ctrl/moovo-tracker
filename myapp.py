import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

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
    requests.post(url, headers=headers, json=payload, timeout=20)

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        return res.json()['candidates'][0]['content']['parts'][0]['text'] if res.status_code == 200 else None
    except: return None

async def scrape_moovo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('.city-location-row', timeout=20000)
            data = await page.evaluate('''() => {
                const results = [];
                document.querySelectorAll('.city-location-row').forEach(row => {
                    const cells = row.querySelectorAll('.city-location-td');
                    if (cells.length >= 3) {
                        results.push({ name: cells[1].innerText.trim(), bikes: cells[2].innerText.trim() });
                    }
                });
                return results;
            }''')
            await browser.close()
            return data
        except:
            await browser.close()
            return None

# ================= 3. 情報比對邏輯 =================
def analyze_market_activity(current_data):
    # 讀取上次存檔
    last_data = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            last_data = json.load(f)
    
    analysis_list = []
    for item in current_data:
        name = item['name']
        current_val = int(item['bikes'])
        last_val = last_data.get(name, current_val) # 若無紀錄則視為無變化
        diff = current_val - last_val
        
        analysis_list.append({
            "name": name,
            "current": current_val,
            "diff": diff
        })
    
    # 將本次數據寫入檔案供下次使用
    new_store = {item['name']: int(item['bikes']) for item in current_data}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_store, f, ensure_ascii=False, indent=4)
        
    return analysis_list

async def main():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        activity_report = analyze_market_activity(raw_data)
        
        prompt = f"""
你現在是敵對勢力派出的「市場流速分析特工」。你的任務是評估 Moovo 的場站熱度。

🔥 **情報規格**：
1. **採集時間**：{current_time}。
2. **市場流速分析**：
   - 「變動量」代表該場站的用戶活動頻率（熱度）。
   - 若變動量(diff)絕對值較大：標記為「⚡ 市場活躍點」，代表用戶反覆使用率極高。
   - 若變動量為 0：標記為「💤 市場冷區」，代表滲透失敗。
3. **商業觀察**：特別列出「變動量」最大的前三個場站，作為我方切入的重點參考。
4. **口吻**：冷酷、精確、去人性化。禁止任何讚美、禁止出現 YouBike。

數據清單（格式：場站名 | 目前數量 | 與上次比變動）：
{activity_report}
"""
        final_msg = call_gemini_direct(prompt)
        if final_msg:
            send_line(final_msg.strip())
            print("Success: 深度情報已發送")
    else:
        print("Error: 採集失敗")

if __name__ == "__main__":
    asyncio.run(main())
