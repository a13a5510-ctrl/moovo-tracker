import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# [System] 特工環境檢查
print(f"[System] 偵察任務啟動: {datetime.now()}")

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
        print(f"[Line] 傳送狀態: {res.status_code}")
    except Exception as e:
        print(f"[Line] 傳送異常: {e}")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 🎯 採用 2026 最穩定的正式版路徑
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            # 🔍 這是抓鬼關鍵：印出 Google 拒絕我們的真正原因
            print(f"❌ AI 拒絕執行。代碼: {res.status_code}")
            print(f"❌ 原始報錯: {res.text}")
            return None
    except Exception as e:
        print(f"❌ 請求物理性失敗: {e}")
        return None

async def scrape_moovo():
    print("[System] 正在滲透 Moovo 官網...")
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
            print(f"[System] 截獲 {len(data)} 個站點情報。")
            return data
        except Exception as e:
            print(f"[System] 抓取失敗: {e}")
            await browser.close()
            return None

def analyze_market_activity(current_data):
    last_data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                last_data = json.load(f)
        except: pass
    
    analysis_list = []
    for item in current_data:
        name = item['name']
        curr_val = int(item['bikes'])
        last_val = last_data.get(name, curr_val)
        diff = curr_val - last_val
        analysis_list.append({"name": name, "curr": curr_val, "diff": diff})
    
    # 更新本地記憶
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
        
        # 🎯 敵對特工 Prompt：加強時間鎖定與冷酷度
        prompt = f"""
你現在是商業競爭對手派出的「數據分析特工」。請針對 Moovo 運行效率進行冷酷評估。

🕵️ **特工機密指令**：
1. **拒絕溫情**：絕對禁止讚美、感謝或暖心提醒。口吻要像寫給總部的機密報告。
2. **精確時間**：本次情報採集時間為：{current_time}。必須直接顯示此時間，嚴禁使用任何佔位符或自創時間。
3. **流動性分析**：
   - 變動量(diff)非 0：標記為「⚡ 市場活躍點」，代表場站車輛反覆使用率高，我方應警惕。
   - 變動量為 0：標記為「💤 市場冷區」，表示該區滲透效率低下。
4. **禁令**：禁止提到 YouBike。

情報清單（場站 | 現有 | 變動）：
{activity_report}
"""
        final_msg = call_gemini_direct(prompt)
        if final_msg:
            send_line(final_msg.strip())
            print("[System] 情報已解密發送。")
        else:
            print("[System] 分析單元離線，任務暫停。")
    else:
        print("[System] 無法取得原始數據。")

if __name__ == "__main__":
    asyncio.run(main())
