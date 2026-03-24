import asyncio
import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# [System] 任務日誌
def spy_log(msg): print(f"{msg}", flush=True)

# 🎯 台北時間 (UTC+8)
current_time_tp = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
file_date = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y%m%d_%H%M")

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
    
    # 準備文字消息
    messages = [{"type": "text", "text": msg}]
    
    # 如果有檔案 URL，加入檔案消息
    if file_url:
        messages.append({
            "type": "file",
            "fileName": EXCEL_FILE,
            "originalContentUrl": file_url
        })
        
    payload = {"to": LINE_TARGET, "messages": messages}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        spy_log(f"[Line] 報告傳送狀態: {res.status_code}")
    except: spy_log("[Line] 傳輸異常")

def upload_excel(file_path):
    """強化版上傳邏輯：多重路徑確保傳輸"""
    spy_log("[System] 正在加密傳輸 Excel 情報檔...")
    
    # 檢查檔案是否存在且有內容
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        spy_log("[System] 錯誤：情報檔為空，取消傳輸")
        return None

    # 路徑 A: file.io
    try:
        with open(file_path, 'rb') as f:
            res = requests.post('https://file.io', files={'file': f}, timeout=20)
            if res.status_code == 200:
                return res.json().get('link')
            else:
                spy_log(f"[System] 路徑 A 阻塞 (代碼 {res.status_code})")
    except: pass

    # 路徑 B: catbox.moe (備援傳輸)
    try:
        spy_log("[System] 切換備援路徑 B...")
        with open(file_path, 'rb') as f:
            res = requests.post('https://catbox.moe/user/api.php', 
                                data={'reqtype': 'fileupload'}, 
                                files={'fileToUpload': f}, timeout=20)
            if res.status_code == 200:
                return res.text.strip() # Catbox 直接回傳 URL 文本
    except Exception as e:
        spy_log(f"[System] 全線傳輸崩潰: {e}")
    
    return None

def create_beautified_excel(changed, unchanged, filename):
    """建立並美化 Excel 檔案"""
    spy_log("[System] 正在繪製精美情報圖表...")
    data = []
    for i in changed:
        data.append({"狀態": "⚡ 變動", "場站名稱": i['name'], "現有台數": i['curr'], "變動量": i['diff']})
    for i in unchanged:
        data.append({"狀態": "⚪ 穩定", "場站名稱": i['name'], "現有台數": i['curr'], "變動量": "0"})
    
    df = pd.DataFrame(data)
    writer = pd.ExcelWriter(filename, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='Moovo即時情報')
    
    workbook = writer.book
    worksheet = writer.sheets['Moovo即時情報']
    
    # 🎨 設定美化樣式
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=12)
    center_align = Alignment(horizontal='center', vertical='center')
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    # 標題欄美化
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = border

    # 內容美化：自動調整欄寬與條件格式
    for row in range(2, len(data) + 2):
        status_cell = worksheet.cell(row=row, column=1)
        diff_cell = worksheet.cell(row=row, column=4)
        
        # ⚡ 變動行著色
        if "⚡" in str(status_cell.value):
            row_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
            for cell in worksheet[row]:
                cell.fill = row_fill
        
        # 設定邊框與對齊
        for cell in worksheet[row]:
            cell.border = border
            cell.alignment = center_align

    # 自動調整欄位寬度
    for col in worksheet.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except: pass
        worksheet.column_dimensions[column].width = max_length + 5

    writer.close()
    return filename

def call_gemini(prompt):
    api_key = AI_KEY.strip()
    # 🎯 鎖定您 list_models 偵察到的 2.5 節點
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

def analyze(current_data):
    history = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: history = json.load(f)
        except: history = {}
    
    changed, unchanged, new_history = [], [], {}
    max_abs_diff = 0
    for item in current_data:
        name = item['name']
        curr = int(item['bikes'])
        prev = history.get(name, {}).get("bikes", curr) if isinstance(history.get(name), dict) else int(history.get(name, curr))
        diff = curr - prev
        abs_diff = abs(diff)
        if abs_diff > max_abs_diff: max_abs_diff = abs_diff
        info = {"name": name, "curr": curr, "diff": f"{'+' if diff > 0 else ''}{diff}", "abs_diff": abs_diff}
        if diff != 0: changed.append(info)
        else: unchanged.append(info)
        new_history[name] = {"bikes": curr}

    for item in changed:
        if item['abs_diff'] == max_abs_diff and max_abs_diff > 0: item['hot'] = True
    
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=4)
    return changed, unchanged

async def main():
    raw_data = await scrape_moovo()
    if raw_data:
        changed, unchanged = analyze(raw_data)
        
        # 1. 生成並美化 Excel
        excel_path = create_beautified_excel(changed, unchanged, EXCEL_FILE)
        file_url = upload_excel(excel_path)
        
        # 2. AI 整理文字報告
        prompt = f"""
你現在是冷酷特工分析官。請撰寫監測報告。
指令：
1. 結構：先列「⚡ 變動場站」，後列「⚪ 穩定場站」。
2. 標註：'hot':True 的站名前加 🔥。
3. 格式：站名:台數 (較上次:變動)。
4. 語言：100% 繁體中文。時間：{current_time_tp}。
數據：變動:{changed}，穩定:{unchanged}
"""
        final_msg = call_gemini(prompt)
        
        # 3. 傳送
        if final_msg:
            send_line(f"[🧠 AI 深度情報]\n" + final_msg.strip(), file_url)
        else:
            send_line(f"【📡 備援分類報告】時間 {current_time_tp}\n(AI 暫時離線，請查閱附件 Excel)", file_url)
    else: spy_log("[System] 抓取失敗")

if __name__ == "__main__":
    asyncio.run(main())
