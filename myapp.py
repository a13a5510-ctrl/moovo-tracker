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

# 🎯 台北時間 (UTC+8) 校正
now = datetime.utcnow() + timedelta(hours=8)
current_time_tp = now.strftime("%Y-%m-%d %H:%M")

# ================= 1. 配置 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")
DATA_FILE = "last_data.json"
SHEET_NAME = "Moovo調度監測表"
DASHBOARD_URL = "https://a13a5510-ctrl.github.io/moovo-tracker/"

# ================= 2. 衛星同步功能 (雙軌存儲) =================

def update_google_sheet(changed, unchanged):
    try:
        spy_log("[System] 正在同步雲端指揮中心...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)
        client = gspread.authorize(creds)
        sh = client.open(SHEET_NAME)

        # --- 分頁 A: 即時情報 (維持現狀，每次覆蓋) ---
        try:
            ws_now = sh.worksheet("即時情報")
        except:
            ws_now = sh.add_worksheet(title="即時情報", rows="100", cols="20")
        
        # --- 分頁 B: 歷史紀錄 (追加模式) ---
        try:
            ws_hist = sh.worksheet("歷史紀錄")
        except:
            ws_hist = sh.add_worksheet(title="歷史紀錄", rows="1000", cols="20")
            ws_hist.append_row(["更新時間", "狀態", "場站名稱", "現有台數", "變動量"])

        # 準備即時數據 (含標題)
        now_rows = [["狀態", "場站名稱", "現有台數", "變動量", "最後更新時間"]]
        # 準備歷史數據 (不含標題，純資料)
        history_rows = []

        # 處理變動資料
        for i in changed:
            row = [i['name'], i['curr'], i['diff']]
            status = "⚡ 變動"
            now_rows.append([status] + row + [current_time_tp])
            history_rows.append([current_time_tp, status] + row)
            
        # 處理穩定資料
        for i in unchanged:
            row = [i['name'], i['curr'], "0"]
            status = "⚪ 穩定"
            now_rows.append([status] + row + [current_time_tp])
            history_rows.append([current_time_tp, status] + row)

        # 1. 更新即時情報 (覆蓋式)
        ws_now.clear()
        ws_now.update(values=now_rows, range_name='A1')
        
        # 2. 追加至歷史紀錄 (追加式)
        if history_rows:
            ws_hist.append_rows(history_rows)
            spy_log(f"✅ 歷史數據已追加 {len(history_rows)} 筆")

        sheet_url = f"https://docs.google.com/spreadsheets/d/{sh.id}/edit#gid=0"
        return sheet_url
    except Exception as e:
        spy_log(f"⚠️ 衛星連線異常: {e}")
        return None

def call_gemini(prompt):
    api_key = AI_KEY.strip()
    target_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    for m in target_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers={"Content-Type": "application/json"}, 
                                json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                spy_log(f"⚠️ AI 呼叫失敗 ({m}): {res.status_code} - {res.text}") # 👈 抓出 API 拒絕的原因
        except Exception as e:
            spy_log(f"⚠️ AI 連線異常 ({m}): {e}") # 👈 抓出網路斷線的原因
            continue
    return None

def send_line(msg, sheet_url=None):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    
    full_text = msg
    
    # 👇 新增的排版邏輯：加入分隔線與兩種連結
    full_text += "\n\n" + "═"*15
    if DASHBOARD_URL:
        full_text += f"\n📈 戰情儀表板 (視覺化)：\n{DASHBOARD_URL}"
    if sheet_url:
        full_text += f"\n📊 原始數據表 (備查用)：\n{sheet_url}"
        
    payload = {"to": LINE_TARGET, "messages": [{"type": "text", "text": full_text}]}
    try:
        requests.post(url, headers=headers, json=payload, timeout=20)
        spy_log(f"[Line] 報告已送達")
    except: pass

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
            prev_data = history.get(name, {})
            prev = prev_data.get("bikes", curr) if isinstance(prev_data, dict) else int(prev_data)
            diff = curr - prev
            abs_diff = abs(diff); max_abs_diff = max(max_abs_diff, abs_diff)
            info = {"name": name, "curr": curr, "diff": f"{'+' if diff > 0 else ''}{diff}", "abs_diff": abs_diff}
            if diff != 0: changed.append(info)
            else: unchanged.append(info)
            new_history[name] = {"bikes": curr}
        
        for i in changed:
            if i['abs_diff'] == max_abs_diff and max_abs_diff > 0: i['hot'] = True
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(new_history, f, ensure_ascii=False)

        # --- 衛星同步 (雙軌) ---
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
