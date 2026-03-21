import asyncio
import json
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright
import google.generativeai as genai

# ================= 1. 保密設定與 AI 配置 =================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-1.5-flash')

if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, GEMINI_API_KEY]):
    print("Error: Missing Credentials")
    exit()

# ================= 2. LINE 發送功能 =================
def send_line_message(message):
    line_api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}
    try:
        response = requests.post(line_api_url, headers=headers, json=payload)
        response.raise_for_status()
        print("LINE notification sent successfully!")
    except Exception as e:
        print(f"LINE send failed: {e}")

# ================= 3. 核心：全面視覺抓取 =================
async def scrape_moovo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        print("[System] Visiting Moovo Webpage...")
        try:
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('.city-location-row', timeout=20000)
            
            scraped_data = await page.evaluate('''() => {
                const results = [];
                const rows = document.querySelectorAll('.city-location-row');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('.city-location-td');
                    if (cells.length >= 3) {
                        const name = cells[1].innerText.trim(); 
                        const bikes = cells[2].innerText.trim();
                        if (name !== "" && !isNaN(parseInt(bikes))) {
                            results.push({ name: name, bikes: bikes });
                        }
                    }
                });
                return results; // 🎯 修正處：這裡要用 // 註解，JS 才看得懂
            }''')
            await browser.close()
            return scraped_data
        except Exception as e:
            print(f"Scrape Error: {e}")
            await browser.close()
            return None

async def main():
    print("[System] Moovo Tracker Started!")
    raw_data = await scrape_moovo()
    
    if raw_data:
        print(f"[System] Scraped {len(raw_data)} stations.")
        
        # 🎯 調整 Prompt，讓 AI 更有溫度
        prompt = f"你是一個專業單車助理。請根據以下資料，整理成一段溫馨且包含**所有站點**的 LINE 監測報告。標題要醒目，並用 Emoji 區分有車與沒車。資料如下：{raw_data}"
        
        try:
            # 🚀 關鍵修改：使用 generate_content 且「不」手動指定 API 版本
            # 這是目前最能避開 v1beta 衝突的寫法
            response = model.generate_content(prompt)
            
            # 💡 增加「強大」的檢查機制
            if response and response.text:
                ai_message = response.text.strip()
                # 預防訊息過長
                if len(ai_message) > 4000:
                    ai_message = ai_message[:4000] + "..."
                send_line_message(ai_message)
                print("Success! AI Enhanced message sent.")
            else:
                # 如果 AI 回傳是空值，丟出錯誤去執行備案
                raise ValueError("Empty response from Gemini")
                
        except Exception as e:
            # 🛡️ 這裡就是您看到的「緊急備案」
            print(f"Gemini Error (Fallback triggered): {e}")
            backup_msg = "🚲 Moovo 完整報告：\n"
            for item in raw_data:
                status = "✅" if int(item['bikes']) > 0 else "❌"
                backup_msg += f"{status} {item['name']}: {item['bikes']} 輛\n"
            send_line_message(backup_msg)
    else:
        print("Failed to get data.")

# 這兩行要放在檔案的最底部，前面不要有空格
if __name__ == "__main__":
    asyncio.run(main())
