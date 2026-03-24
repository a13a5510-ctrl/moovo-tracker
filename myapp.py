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

# 🎯 台北時間 (UTC+8) 校正
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
    """特工防彈發送：嘗試發送檔案，失敗則自動降級為文字"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    
    # 在文字末尾加入下載連結作為終極備援
    full_text = msg
    if file_url:
        full_text += f"\n\n📂 完整情報表下載：\n{file_url}"
    
    # 策略 A：嘗試發送 [文字 + 檔案圖示]
    payload_a = {
        "to": LINE_TARGET,
        "messages": [
            {"type": "text", "text": full_text}
        ]
    }
    
    if file_url:
        payload_a["messages"].append({
            "type": "file",
            "fileName": EXCEL_FILE,
            "originalContentUrl": file_url
        })

    try:
        spy_log(f"[Line] 嘗試發送完整情報 (文字+檔案)...")
        res = requests.post(url, headers=headers, json=payload_a, timeout=20)
        
        if res.status_code == 200:
            spy_log("[Line] ✅ 全通訊成功送達")
        elif res.status_code == 400 and file_url:
            spy_log(f"⚠️ [Line] 檔案掛載遭拒 (400)，錯誤內容: {res.text}")
            spy_log("[Line] 執行降級方案：改發純文字情報...")
            # 策略 B：降級為純文字
            payload_b = {"to": LINE_TARGET, "messages": [{"type": "text", "text": full_text}]}
            res_b = requests.post(url, headers=headers, json=payload_b, timeout=20)
            spy_log(f"[Line] 降級發送狀態: {res_b.status_code}")
        else:
            spy_log(f"❌ [Line] 異常狀態碼: {res.status_code}, 內容: {res.text}")
    except Exception as e:
        spy_log(f"🚫 [Line] 通訊物理損壞: {e}")

def upload_excel(file_path):
    """三重上傳路徑：Catbox -> file.io -> transfer.sh"""
    if not os.path.exists(file_path): return None
    spy_log(f"[System] 準備上傳情報檔 ({os.path.getsize(file_path)} bytes)...")

    # 🚀 路徑 A: Catbox
    try:
        spy_log("[System] 嘗試路徑 A (Catbox)...")
        with open(file_path, 'rb') as f:
            res = requests.post('https://catbox.moe/user/api.php', 
                                data={'reqtype': 'fileupload'}, 
                                files={'fileToUpload': f}, timeout=25)
            if res.status_code == 200 and "https" in res.text:
                return res.text.strip()
    except: pass

    # 🚀 路徑 B: file.io
    try:
        spy_log("[System] 嘗試路徑 B (file.io)...")
        with open(file_path, 'rb') as f:
            res = requests.post('https://file.io', files={'file': f}, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if data.get('success'): return data.get('link')
    except: pass

    # 🚀 路徑 C: transfer.sh
    try:
        spy_log("[System] 嘗試路徑 C (transfer.sh)...")
        with open(file_path, 'rb') as f:
            res = requests.put(f'https://transfer.sh/{EXCEL_FILE}', data=f, timeout=20)
            if res.status_code == 200:
                url = res.text.strip()
                return url if url.startswith("http") else f"https://{url}"
    except: pass

    return None

def create_beautified_excel(changed, unchanged, filename):
    """建立並美化 Excel 報表"""
    spy_log("[System] 正在製作數位化美化情報表...")
    data = []
    for i in changed:
        data.append({"狀態": "⚡ 變動", "場站名稱": i['name'], "現有台數": i['curr'], "變動量": i['diff']})
    for i in unchanged:
        data.append({"狀態": "⚪ 穩定", "場站名稱": i['name'], "現有台數": i['curr'], "變動量": "0"})
    
    df = pd.DataFrame(data)
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Moovo')
        ws = writer.sheets['Moovo']
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
        # 數據分析
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

        # Excel 與傳輸
        excel_path = create_beautified_excel(changed, unchanged, EXCEL_FILE)
        file_url = upload_excel(excel_path)
        
        # AI 報告
        prompt = f"撰寫 Moovo 監測報告。指令：分⚡變動(hot加🔥)與⚪穩定區。格式:站名:台數 (較上次:變動)。100%繁體。時間:{current_time_tp}。數據：{changed}, {unchanged}"
        final_msg = call_gemini(prompt)
        
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip(), file_url)
        else:
            send_line(f"【📡 備援分類報告】時間 {current_time_tp}\n(AI 暫時離線)", file_url)
    else: spy_log("[System] 數據抓取失敗")

if __name__ == "__main__":
    asyncio.run(main())
