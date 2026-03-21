import asyncio
import os
import requests
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# [System] 任務啟動
def spy_log(msg):
    print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8) 校正
current_time_tp = datetime.utcnow() + timedelta(hours=8)
spy_log(f"[System] 偵察任務啟動 (Taipei Time): {current_time_tp.strftime('%Y-%m-%d %H:%M:%S')}")

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
        spy_log(f"[Line] 報告傳輸狀態: {res.status_code}")
    except Exception as e:
        spy_log(f"[Line] 傳輸異常: {e}")

def call_gemini_direct(prompt):
    api_key = AI_KEY.strip()
    # 🎯 配額避險策略：優先使用 1.5-flash，若失敗再換 Pro
    preferences = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-2.0-flash"]
    
    for model in preferences:
        spy_log(f"[AI] 正在嘗試穿透模型閘門: {model}")
        url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200:
                spy_log(f"[AI] {model} 成功產出情報。")
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                spy_log(f"[AI] {model} 拒絕訪問 (狀態: {res.status_code})")
        except:
            continue
    return None

async def scrape_moovo():
    spy_log("[System] 滲透 Moovo 即時訊號...")
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
    spy_log("[System] 正在比對歷史滲透數據 (Cold Count Compatible Mode)...")
    history = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: history = {}
    
    analysis_list = []
    new_history = {}
    for item in current_data:
        name = item['name']
        curr_bikes = int(item['bikes'])
        prev = history.get(name)
        
        # 🎯 格式相容處理 (數字 vs 字典)
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
    time_str = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    raw_data = await scrape_moovo()
    
    if raw_data:
        full_report = analyze_with_history(raw_data)
        
        # 🕵️ 特工 Prompt：加強視覺描述指令
        prompt = f"""
你現在是敵對勢力派出的「特級情報分析官」。請撰寫冷酷的場站運行報告。
🕵️ 指令：
1. **身份**：冷淡、專業。嚴禁出現讚美、感謝。時間：{time_str}。
2. **數據判讀**：
   - 累積冷區計數 (cold_count) >= 3：🚨 [特級預警：場站癱瘓]。代表補車效率極低，我方應趁虛而入。
3. **數據描述修正**：
   - 在列出數據變動(diff)時，請將描述變得更直白，例如：(較上次監測數據相比: +2台) 或 (較上次監測數據相比: -3台)。
4. **禁令**：嚴禁提到 YouBike。請直接分析 Moovo 的死穴。
情報數據（格式：站名|現有|變動|計數）：
{full_report}
"""
        final_msg = call_gemini_direct(prompt)
        
        if final_msg:
            # 🎯 🧠 視覺升級 1：AI 精準分析標題
            header = f"[🧠 AI 深度情報分析]\n本次採集時間：{time_str}\n\n"
            send_line(header + final_msg.strip())
            spy_log("[System] AI 情報已加密傳輸。")
        else:
            # 🎯 📡 視覺升級 2：原始數據標題與直白變動描述
            spy_log("[System] AI 分析單元故障，啟動備援幽靈通訊協定...")
            
            backup = f"[📡 原始情報攔截 - AI 單元離線]\n本次截獲時間 (TP)：{time_str}\n\n"
            backup += "數據清單：\n-------------------\n"
            for item in full_report:
                # 預警圖示
                status = "🔴" if item['cold_count'] >= 3 else ("⚡" if item['diff'] != 0 else "⚪")
                
                # 直白變動描述
                diff_val = f"{item['diff']}"
                if item['diff'] > 0:
                    diff_str = f"⬆️ 較上次監測數據相比: +{diff_val}台"
                elif item['diff'] < 0:
                    diff_str = f"⬇️ 較上次監測數據相比: {diff_val}台"
                else:
                    diff_str = f"➡ 較上次監測數據相比: 無變動"
                    
                backup += f"{status} {item['name']}: {item['curr']}台\n   ({diff_str}, 冷區計數:{item['cold_count']})\n"
                
            send_line(backup + "\n[警告] 此為原始加密數據，未經 AI 分析。")
    else:
        spy_log("[System] 網頁抓取失敗，任務終止。")

if __name__ == "__main__":
    asyncio.run(main())
