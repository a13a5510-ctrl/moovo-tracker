import asyncio
import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# [System] 任務日誌
def spy_log(msg): print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8)
now = datetime.utcnow() + timedelta(hours=8)
current_time_tp = now.strftime("%Y-%m-%d %H:%M")
file_date = now.strftime("%Y%m%d_%H%M")

# ================= 1. 配置 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")
DATA_FILE = "last_data.json"
EXCEL_FILE = f"Moovo_Report_{file_date}.xlsx"

# ================= 2. 功能函數 =================
def send_line(msg, file_url=None):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    messages = [{"type": "text", "text": msg}]
    if file_url:
        spy_log(f"[Line] 附加情報 URL：{file_url}")
        messages.append({
            "type": "file",
            "fileName": EXCEL_FILE,
            "originalContentUrl": file_url
        })
    payload = {"to": LINE_TARGET, "messages": messages}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        spy_log(f"[Line] 傳送狀態碼: {res.status_code}")
    except Exception as e:
        spy_log(f"[Line] 傳輸崩潰: {e}")

def upload_excel(file_path):
    """三層防禦上傳邏輯：確保檔案送達"""
    if not os.path.exists(file_path):
        spy_log(f"[System] 找不到檔案: {file_path}"); return None
    
    spy_log(f"[System] 開始傳輸情報檔 ({os.path.getsize(file_path)} bytes)...")

    # 🚀 路徑 A: Catbox (穩定首選)
    try:
        spy_log("[System] 嘗試路徑 A (Catbox)...")
        with open(file_path, 'rb') as f:
            res = requests.post('https://catbox.moe/user/api.php', 
                                data={'reqtype': 'fileupload'}, 
                                files={'fileToUpload': f}, timeout=20)
            if res.status_code == 200 and "https" in res.text:
                return res.text.strip()
    except: pass

    # 🚀 路徑 B: file.io (第二備援)
    try:
        spy_log("[System] 嘗試路徑 B (file.io)...")
        with open(file_path, 'rb') as f:
            res = requests.post('https://file.io', files={'file': f}, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if data.get('success'): return data.get('link')
    except: pass

    # 🚀 路徑 C: transfer.sh (終極備援)
    try:
        spy_log("[System] 嘗試路徑 C (transfer.sh)...")
        with open(file_path, 'rb') as f:
            res = requests.put(f'https://transfer.sh/{EXCEL_FILE}', data=f, timeout=20)
            if res.status_code == 200: return res.text.strip()
    except: pass

    spy_log("[System] ❌ 所有傳輸路徑皆已阻塞")
    return None

def create_beautified_excel(changed, unchanged, filename):
    """Excel 繪製與美化"""
    spy_log("[System] 正在繪製視覺化情報表...")
    data = []
    for i in changed:
        data.append({"狀態": "⚡ 變動", "場站名稱": i['name'], "現有台數": i['curr'], "變動量": i['diff']})
    for i in unchanged:
        data.append({"狀態": "⚪ 穩定", "場站名稱": i['name'], "現有台數": i['curr'], "變動量": "0"})
    
    df = pd.DataFrame(data)
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Moovo')
        ws = writer.sheets['Moovo']
        # 美化樣式
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        center = Alignment(horizontal='center', vertical='center')
        border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        
        for cell in ws[1]:
            cell.fill, cell.font, cell.alignment, cell.border = header_fill, header_font, center, border
        for row in range(2, len(data) + 2):
            fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid") if "⚡" in str(ws.cell(row=row, column=1).value) else None
            for cell in ws[row]:
                if fill: cell.fill = fill
                cell.alignment, cell.border = center, border
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 25
    return filename

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
        # --- 數據處理 ---
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

        # --- Excel 與傳輸 ---
        excel_path = create_beautified_excel(changed, unchanged, EXCEL_FILE)
        file_url = upload_excel(excel_path)
        
        # --- AI 報告 ---
        prompt = f"撰寫 Moovo 監測報告。指令：分⚡變動(hot加🔥)與⚪穩定區。格式:站名:台數 (較上次:變動)。100%繁體。時間:{current_time_tp}。數據：{changed}, {unchanged}"
        final_msg = call_gemini(prompt)
        
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip(), file_url)
        else:
            send_line(f"【📡 備援報告】時間 {current_time_tp}\n(AI 暫時離線，請查閱 Excel)", file_url)
    else: spy_log("[System] 抓取失敗")

if __name__ == "__main__":
    asyncio.run(main())
