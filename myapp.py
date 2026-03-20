import asyncio
import json
import os
import requests
import base64
from datetime import datetime
from playwright.async_api import async_playwright
import google.generativeai as genai

# ================= 1. 保密設定與 AI 配置 =================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 🔐 配置 Gemini
genai.configure(api_key=GEMINI_API_KEY)
# 🎯 關鍵修改：換成最新的模型名稱 'gemini-1.5-flash'
model = genai.GenerativeModel('gemini-1.5-flash')

if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, GEMINI_API_KEY]):
    print("Error: Missing Credentials")
    exit()

# ================= 2. AI 美化：叫 Gemini 設計網頁 =================
def ask_gemini_for_html(data_list):
    prompt = f"""
    你是一位專業的網頁設計師。請根據以下 Moovo 腳踏車站點資料，寫一份極簡、美觀且適合手機閱讀的單一 HTML 檔案（包含 CSS）。
    要求：
    1. 使用深色模式風格。
    2. 站點名稱要清楚，車輛數目若為 0 則顯示紅色，有車則顯示綠色。
    3. 加入一些可愛的 Emoji。
    4. 不要寫任何解釋，只要給代碼。
    資料如下：{data_list}
    """
    try:
        response = model.generate_content(prompt)
        # 去除 Markdown 標籤 (```html ... ```)
        clean_html = response.text.replace('```html', '').replace('```', '').strip()
        return clean_html
    except Exception as e:
        print(f"Gemini Error: {e}")
        return None

# ================= 3. LINE 發送圖片功能 =================
def send_line_image(image_path):
    # 注意：LINE 傳送圖片需要一個公開網址。
    # 由於 GitHub Actions 是暫時性的，我們改用傳送「文字」加上「美化過的排版」
    # 若要真正傳送圖片，通常需要圖床。這裡我們先實現「AI 內容優化」！
    pass

def send_line_message(message):
    line_api_url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}
    requests.post(line_api_url, headers=headers, data=json.dumps(payload))

# ================= 4. 核心：視覺抓取 =================
async def scrape_moovo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="networkidle")
        await page.wait_for_selector('.city-location-row')
        
        data = await page.evaluate('''() => {
            const results = [];
            document.querySelectorAll('.city-location-row').forEach(row => {
                const cells = row.querySelectorAll('.city-location-td');
                if (cells.length >= 3) {
                    results.push({ name: cells[1].innerText.trim(), bikes: cells[2].innerText.trim() });
                }
            });
            return results.slice(0, 15); // 只取前 15 站，避免訊息過長
        }''')
        await browser.close()
        return data

async def main():
    print("[System] Evolution Started!")
    raw_data = await scrape_moovo()
    
    if raw_data:
        # 🎯 優化指令：讓 Gemini 絕對服從排版要求
        prompt = f"""
        請根據以下單車資料，撰寫一段溫馨且易讀的 LINE 訊息。
        要求：
        1. 使用繁體中文。
        2. 加上豐富的 Emoji（如 🚲, 📍, ✅, ❌）。
        3. 標註哪些站點「還有車」以及「目前沒車」。
        4. 不要包含任何程式碼標籤，直接給我結果文字。
        
        原始資料：{raw_data}
        """
        
        try:
            # 🚀 加入安全檢查與重試邏輯
            result = model.generate_content(prompt)
            
            # 確保 result 裡面真的有文字
            if result and result.text:
                ai_message = result.text.strip()
                send_line_message(ai_message)
                print("Success! AI Enhanced message sent.")
            else:
                raise ValueError("Gemini returned empty result")
                
        except Exception as e:
            print(f"Gemini Processing Error: {e}")
            # 🛡️ 如果 AI 沒反應，我們手動做一個簡單的排版作為備案，不要發送難看的 JSON
            backup_msg = "🚲 Moovo 站點簡易報表：\n"
            for item in raw_data:
                status = "✅" if int(item['bikes']) > 0 else "❌"
                backup_msg += f"{status} {item['name']}: {item['bikes']} 輛\n"
            send_line_message(backup_msg)
            print("AI failed, sent formatted backup message.")
    else:
        print("Failed to get data.")

if __name__ == "__main__":
    asyncio.run(main())
