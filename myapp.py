import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# [System] 腳本啟動日誌
print(f"[System] 特工腳本啟動: {datetime.now()}")

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
    # 🎯 偵測雷達：先確認這把金鑰能看見哪些模型
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        print("[AI] 正在掃描可用模型清單...")
        list_res = requests.get(list_url, timeout=20)
        if list_res.status_code != 200:
            print(f"❌ 金鑰權限檢查失敗: {list_res.text}")
            return None
        
        models_data = list_res.json()
        available_models = [m['name'] for m in models_data.get('models', [])]
        
        # 挑選優先級：1.5-flash > 1.5-pro > gemini-pro
        target_model = ""
        preferences = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-pro"]
        for p in preferences:
            if p in available_models:
                target_model = p
                break
        
        if not target_model:
            print("❌ 找不到可用的 Gemini 模型清單。")
            return None

        print(f"🚀 雷達鎖定模型: {target_model}")
        
        # 發送情報分析請求
        gen_url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        gen_res = requests.post(gen_url, headers=headers, json=payload, timeout=30)
        if gen_res.status_code == 200:
            return gen_res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"❌ 分析請求失敗: {gen_res.text}")
            return None

    except Exception as e:
        print(f"❌ 診斷異常: {e}")
        return None

async def scrape_moovo():
    print("[System] 正在滲透 Moovo 網頁抓取即時數據...")
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
            print(f"[System] 成功截獲 {len(data)} 個場站情報。")
            return data
        except Exception as e:
            print(f"[System] 數據截獲失敗: {e}")
            await browser.close()
            return None

def analyze_market_activity(current_data):
    last_data = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                last_data = json.load(f)
        except: last_data = {}
    
    analysis_list = []
    for item in current_data:
        name = item['name']
        curr_val = int(item['bikes'])
        last_val = last_data.get(name, curr_val)
        diff = curr_val - last_val
        analysis_list.append({"name": name, "curr": curr_val, "diff": diff})
    
    # 存檔供下次比對
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
你現在是敵對勢力派出的「市場流動率分析特工」。

🚨 **特工任務規範**：
1. **絕不讚美**：禁止出現任何「感謝、愛護、愉快、溫馨」等正向情感詞彙。
2. **採集時間**：{current_time}。
3. **情報比對分析**：
   - 變動量(diff)絕對值大：標記為「⚡ 市場活躍點」，代表該區用戶活動極度頻繁。
   - 變動量為 0：標記為「💤 市場冷區」，代表滲透率低。
4. **格式要求**：
   - 標題：[內部機密] Moovo 場站滲透熱度報告
   - 使用 Emoji：活躍點用 🔴，冷區用 ⚪。
5. **口吻**：冷酷、精確。嚴禁提到「YouBike」。

情報清單（格式：場站名 | 現有車數 | 流動差值）：
{activity_report}
"""
        final_msg = call_gemini_direct(prompt)
        if final_msg:
            send_line(final_msg.strip())
            print("[System] 深度情報已成功加密外洩至 LINE。")
        else:
            print("[System] AI 分析單元故障，中止傳送。")
    else:
        print("[System] 網頁抓取失敗，任務取消。")

if __name__ == "__main__":
    asyncio.run(main())
