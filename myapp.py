import asyncio
import os
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# [System] 任務日誌
def spy_log(msg): print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8)
now = datetime.utcnow() + timedelta(hours=8)
current_time_tp = now.strftime("%Y-%m-%d %H:%M")

# ================= 1. 配置 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")
DATA_FILE = "last_data.json"
SHEET_NAME = "Moovo調度監測表"  # 🎯 請確保這跟您的試算表名稱一模一樣

# ================= 2. 衛星同步功能 =================

def update_google_sheet(changed, unchanged):
    """將情報同步至雲端指揮中心"""
    try:
        spy_log("[System] 正在與 Google Sheets 衛星連線...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # 讀取剛剛還原的 creds.json
        creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
        client = gspread.authorize(creds)
        
        # 開啟試算表
        sh = client.open(SHEET_NAME)
        worksheet = sh.get_worksheet(0) # 開啟第一個分頁
        
        # 準備數據
        headers = ["狀態", "場站名稱", "現有台數", "變動量", "最後更新時間"]
        rows = [headers]
        
        for i in changed:
            status = "🔥 變動" if i.get('hot') else "⚡ 變動"
            rows.append([status, i['name'], i['curr'], i['diff'], current_time_tp])
        for i in unchanged:
            rows.append(["⚪ 穩定", i['name'], i['curr'], "0", current_time_tp])
            
        # 寫入 (清空舊資料並填入新資料)
        worksheet.clear()
        worksheet.update('A1', rows)
        
        # 取得分享 URL (帶有表格視角)
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sh.id}/edit#gid=0"
        spy_log(f"✅ 衛星同步成功: {sheet_url}")
        return sheet_url
    except Exception as e:
        spy_log(f"❌ 衛星同步失敗: {e}")
        return None

def send_line(msg, sheet_url=None):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    
    full_text = msg
    if sheet_url:
        full_text += f"\n\n📊 雲端指揮中心 (即時表格)：\n{sheet_url}"
    
    payload = {"to": LINE_TARGET, "messages": [{"type": "text", "text": full_text}]}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        spy_log(f"[Line] 傳送狀態碼: {res.status_code}")
    except: pass

def call_gemini(prompt):
    api_key = AI_KEY.strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        res = requests.post(url, headers={"Content-Type": "application/json"}, 
                            json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        if res.status_code == 200: return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return None

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
            await browser.close(); return data
        except: await browser.close(); return None

async def main():
    raw_data = await scrape_moovo()
    if raw_data:
        # --- 數據分析 ---
        history = {}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f: history = json.load(f)
            except: history = {}
        
        changed, unchanged, new_history = [], [], {}
        max_abs_diff = 0
        for item in raw_data:
            name, curr = item['name'], int(item['bikes'])
            prev = history.get(name, {}).get("bikes", curr) if isinstance(history.get(name), dict) else int(history.get(name, curr))
            diff = curr - prev
            abs_diff = abs(diff); max_abs_diff = max(max_abs_diff, abs_diff)
            info = {"name": name, "curr": curr, "diff": f"{'+' if diff > 0 else ''}{diff}", "abs_diff": abs_diff}
            if diff != 0: changed.append(info)
            else: unchanged.append(info)
            new_history[name] = {"bikes": curr}
        for i in changed:
            if i['abs_diff'] == max_abs_diff and max_abs_diff > 0: i['hot'] = True
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(new_history, f, ensure_ascii=False)

        # --- Google Sheets 同步 ---
        sheet_url = update_google_sheet(changed, unchanged)
        
        # --- AI 報告 ---
        prompt = f"撰寫 Moovo 監測報告。指令：分⚡變動(hot加🔥)與⚪穩定區。格式:站名:台數 (較上次:變動)。100%繁體。時間:{current_time_tp}。數據：{changed}, {unchanged}"
        final_msg = call_gemini(prompt)
        
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip(), sheet_url)
        else:
            send_line(f"【📡 衛星備援報告】時間 {current_time_tp}", sheet_url)
    else: spy_log("[System] 偵察失敗")

if __name__ == "__main__":
    asyncio.run(main())
