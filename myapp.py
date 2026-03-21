import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# [System] 任務啟動
print(f"[System] 商業滲透任務啟動: {datetime.now()}")

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
    # 🎯 取得可用模型清單
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        list_res = requests.get(list_url, timeout=20)
        available = [m['name'] for m in list_res.json().get('models', [])]
        
        # 🎯 優先級清單：將 1.5 放在前面以避開 2.0 的配額限制，或保持 2.0 優先但失敗時切換
        # 考慮到穩定性，大師幫您把 1.5-flash 調前，因為它目前最不容易報 429
        preferences = ["models/gemini-1.5-flash", "models/gemini-2.0-flash", "models/gemini-1.5-pro"]
        
        target_models = [p for p in preferences if p in available]
        
        for model in target_models:
            print(f"[AI] 嘗試使用模型: {model}")
            gen_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
            res = requests.post(gen_url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            elif res.status_code == 429:
                print(f"⚠️ {model} 配額用盡，嘗試下一個備案...")
                continue
            else:
                print(f"❌ {model} 報錯: {res.text}")
        return None
    except: return None

async def scrape_moovo():
    print("[System] 滲透 Moovo 官網抓取即時數據...")
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
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: pass
    
    analysis_list = []
    new_history = {}
    for item in current_data:
        name = item['name']
        curr_bikes = int(item['bikes'])
        prev = history.get(name, {"bikes": curr_bikes, "cold_count": 0})
        
        diff = curr_bikes - prev["bikes"]
        cold_count = prev.get("cold_count", 0) + 1 if curr_bikes == 0 else 0
        
        analysis_list.append({"name": name, "curr": curr_bikes, "diff": diff, "cold_count": cold_count})
        new_history[name] = {"bikes": curr_bikes, "cold_count": cold_count}
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=4)
    return analysis_list

async def main():
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        full_report = analyze_with_history(raw_data)
        prompt = f"""
你現在是敵對勢力的「特級商業間諜」。請進行冷酷的 Moovo 場站分析。
🕵️ **指令**：
1. **絕不讚美**：口吻專業、批判，嚴禁出現任何正向詞彙。
2. **時間**：{time_str}。
3. **數據判讀**：
   - diff 非 0：⚡ 市場活躍點。
   - cold_count >= 3：🚨 [特級預警：場站癱瘓]。
4. **禁令**：嚴禁提到 YouBike。
情報：{full_report}
"""
        msg = call_gemini_direct(prompt)
        if msg:
            send_line(msg.strip())
            print("[System] 情報已解密送達。")
        else:
            print("[System] 所有 AI 節點均忙線或報錯。")
    else:
        print("[System] 數據抓取失敗。")

if __name__ == "__main__":
    asyncio.run(main())
