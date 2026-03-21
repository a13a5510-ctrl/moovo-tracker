import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# [System] 環境與時鐘對齊
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
        print(f"[Line] 傳送成功，狀態: {res.status_code}")
    except Exception as e:
        print(f"[Line] 傳送異常: {e}")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 🎯 採用 #41 成功的自動偵測雷達
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        print("[AI] 正在鎖定衛星頻譜 (偵測模型)...")
        list_res = requests.get(list_url, timeout=20)
        if list_res.status_code != 200:
            print(f"❌ 衛星連線失敗: {list_res.text}")
            return None
        
        models_data = list_res.json()
        available_models = [m['name'] for m in models_data.get('models', [])]
        
        # 🎯 優先級排序：2.0-flash (之前成功的關鍵) > 1.5-flash > 1.5-pro
        target_model = ""
        preferences = ["models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-1.5-pro"]
        for p in preferences:
            if p in available_models:
                target_model = p
                break
        
        if not target_model:
            print("❌ 本區段無可用分析模型。")
            return None

        print(f"🚀 已鎖定情報處理單元: {target_model}")
        
        # 發送情報分析請求
        gen_url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        gen_res = requests.post(gen_url, headers=headers, json=payload, timeout=30)
        if gen_res.status_code == 200:
            return gen_res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"❌ 分析失敗: {gen_res.text}")
            return None
    except Exception as e:
        print(f"❌ 診斷異常: {e}")
        return None

async def scrape_moovo():
    print("[System] 滲透 Moovo 伺服器...")
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
            print(f"[System] 成功截獲 {len(data)} 個場站數據。")
            return data
        except Exception as e:
            print(f"[System] 滲透失敗: {e}")
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
    # 🎯 修正時間顯示問題：直接傳入真實時間字串
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        activity_report = analyze_market_activity(raw_data)
        
        # 🕵️ 敵對特工 Prompt：加強冷酷度與數據敏感度
        prompt = f"""
你現在是商業競爭對手派出的「數據分析特工」。請針對 Moovo 運行效率進行冷酷評估。

🕵️ **特工指令**：
1. **身份**：冷淡、專業、去人性化。嚴禁出現讚美、感謝或暖心提醒。
2. **精確紀錄**：情報採集時間為：{current_time_str}。
3. **熱度指標**：
   - 變動量(diff)非 0：標記為「⚡ 市場活躍點」，代表場站車輛流動率高，具備商業價值。
   - 變動量為 0：標記為「💤 市場冷區」，代表滲透效率低。
4. **重點標記**：請特別挑出「流動差值」最大的三個站點，分析其異常活動。
5. **禁令**：嚴禁提到 YouBike。

數據情報（場站 | 現有 | 流動差值）：
{activity_report}
"""
        final_msg = call_gemini_direct(prompt)
        if final_msg:
            send_line(final_msg.strip())
            print("[System] 情報已加密傳輸至總部。")
        else:
            print("[System] 分析單元離線。")
    else:
        print("[System] 偵察無果。")

if __name__ == "__main__":
    asyncio.run(main())
