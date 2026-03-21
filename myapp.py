import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# [System] 任務啟動，強迫輸出
def spy_log(msg):
    print(f"{msg}", flush=True)

spy_log(f"[System] 商業滲透任務啟動: {datetime.now()}")

# ================= 1. 配置 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")
DATA_FILE = "last_data.json"

# ================= 2. 功能函數 =================
def send_line(msg):
    spy_log("[Line] 正在嘗試穿透防火牆發送報告...")
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_TARGET, "messages": [{"type": "text", "text": msg}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            spy_log(f"[Line] 報告發送成功。")
        else:
            spy_log(f"[Line] 報告攔截失敗，代碼: {res.status_code}, 原因: {res.text}")
    except Exception as e:
        spy_log(f"[Line] 傳輸異常: {e}")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        spy_log("[AI] 正在鎖定衛星頻譜 (偵測模型)...")
        list_res = requests.get(list_url, timeout=20)
        models_data = list_res.json()
        available = [m['name'] for m in models_data.get('models', [])]
        
        # 配額避險：1.5-flash 最穩
        target = ""
        for p in ["models/gemini-1.5-flash", "models/gemini-2.0-flash", "models/gemini-1.5-pro"]:
            if p in available: target = p; break
        
        if not target:
            spy_log("[AI] 無可用模型節點。")
            return None
        
        spy_log(f"[AI] 決定使用處理單元: {target}")
        gen_url = f"https://generativelanguage.googleapis.com/v1beta/{target}:generateContent?key={api_key}"
        res = requests.post(gen_url, headers={"Content-Type": "application/json"}, 
                            json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        
        if res.status_code == 200:
            spy_log("[AI] 情報分析完成。")
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            spy_log(f"[AI] 分析單元報錯: {res.text}")
            return None
    except Exception as e:
        spy_log(f"[AI] 衛星連線中斷: {e}")
        return None

async def scrape_moovo():
    spy_log("[System] 正在滲透 Moovo 官網...")
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
            spy_log(f"[System] 情報採集成功，共 {len(data)} 站點。")
            return data
        except Exception as e:
            spy_log(f"[System] 官網滲透失敗: {e}")
            await browser.close()
            return None

def analyze_with_history(current_data):
    spy_log("[System] 正在比對歷史滲透數據...")
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
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        full_report = analyze_with_history(raw_data)
        prompt = f"""
你現在是商業競爭對手派出的「特級情報分析官」。請根據以下數據，針對 Moovo 進行冷酷的運行效率評估。

🕵️ **分析指令**：
1. **絕對禁止溫情**：嚴禁出現讚美、感謝、或任何祝願詞彙。
2. **紀錄時間**：情報採集時間為：{time_str}。
3. **數據判讀指標**：
   - 「流動差值」非 0：標記為「⚡ 市場活躍」。
   - 「冷區計數」>= 3：🚨 [核心預警：場站癱瘓]。這代表對手補車體系崩潰。
4. **重點標記**：請將「場站癱瘓」的站點列在報告最頂部。
5. **禁令**：嚴禁提到 YouBike。

情報清單：
{full_report}
"""
        final_msg = call_gemini_direct(prompt)
        if final_msg:
            send_line(final_msg.strip())
            spy_log("[System] 情報已解密送達。")
        else:
            spy_log("[System] 分析單元故障，情報無法外洩。")
    else:
        spy_log("[System] 無法截獲原始數據，中止任務。")

if __name__ == "__main__":
    asyncio.run(main())
