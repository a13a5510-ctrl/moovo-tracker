import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# [System] 確保腳本一啟動就印出日誌
print(f"[System] 腳本啟動成功: {datetime.now()}")

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
        print(f"[Line] 傳送結果狀態碼: {res.status_code}")
    except Exception as e:
        print(f"[Line] 傳送異常: {e}")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 這裡使用最穩定的自動偵測模式
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"[AI] 錯誤回傳: {res.text}")
            return None
    except Exception as e:
        print(f"[AI] 請求異常: {e}")
        return None

async def scrape_moovo():
    print("[System] 正在前往 Moovo 網頁抓取資料...")
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
            print(f"[System] 成功抓取 {len(data)} 個站點。")
            return data
        except Exception as e:
            print(f"[System] 抓取過程失敗: {e}")
            await browser.close()
            return None

def analyze_market_activity(current_data):
    last_data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                last_data = json.load(f)
        except:
            last_data = {}
    
    analysis_list = []
    for item in current_data:
        name = item['name']
        curr_val = int(item['bikes'])
        last_val = last_data.get(name, curr_val)
        diff = curr_val - last_val
        analysis_list.append({"name": name, "curr": curr_val, "diff": diff})
    
    # 更新記憶檔案
    new_store = {item['name']: int(item['bikes']) for item in current_data}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_store, f, ensure_ascii=False, indent=4)
        
    return analysis_list

# ================= 3. 主流程 =================
async def main():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        activity_report = analyze_market_activity(raw_data)
        
        prompt = f"""
你現在是敵對勢力派出的「市場流速分析特工」。你的任務是監控 Moovo 的場站熱度。

🚨 **特工行為準則**：
1. **絕不讚美**：禁止使用「感謝、支持、愛護、愉快」等任何正向詞彙。
2. **採集時間**：{current_time}。
3. **熱度分析**：
   - 變動量(diff)絕對值愈大：標記為「⚡ 市場活躍點」，代表該區用戶活動頻率極高。
   - 變動量為 0：標記為「💤 市場冷區」，代表滲透失敗。
4. **口吻**：冷酷、專業。嚴禁提到「YouBike」。

情報清單（格式：場站名 | 現有車數 | 流動差值）：
{activity_report}
"""
        final_msg = call_gemini_direct(prompt)
        if final_msg:
            send_line(final_msg.strip())
            print("[System] 情報已加密發送至 LINE。")
        else:
            print("[System] AI 分析失敗，跳過發送。")
    else:
        print("[System] 網頁抓取無結果，中止任務。")

# 🎯 確保這一行在最左邊，沒有縮排！
if __name__ == "__main__":
    asyncio.run(main())
