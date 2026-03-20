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

# 🔐 配置 Gemini
genai.configure(api_key=GEMINI_API_KEY)
# 使用最新的 gemini-1.5-flash，速度與穩定度兼具
model = genai.GenerativeModel('gemini-1.5-flash')

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
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
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

        print("[System] Evolution Started! Visiting Moovo Webpage...")
        try:
            # 設定 30 秒載入逾時，等待網路穩定
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=30000)
            # 等待表格現身
            await page.wait_for_selector('.city-location-row', timeout=20000)
            
            # 🚀 解開所有封印，把畫面上所有資料都刮下來！
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
                return results; # 🎯 關鍵：不進行 slice 切片，回傳完整列表
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
        print(f"[System] Scraped {len(raw_data)} stations in total.")
        
        # 🎯 優化指令：讓 Gemini 撰寫包含「所有站點」的溫馨監測報告
        prompt = f"""
        你是一個專業的單車助理。請根據以下單車資料，撰寫一段溫馨、易讀且**包含所有站點**的 LINE 訊息。
        要求：
        1. 使用繁體中文。
        2. 標題要醒目（例如：🚲 Moovo 單車完整監測報告）。
        3. 加上豐富的 Emoji（如 🚲, 📍, ✅ 有車, ❌ 沒車）。
        4. **重要**：必須列出**所有**站點，清楚標記哪些有車、哪些沒車。
        5. 不要包含任何程式碼標籤，直接給我結果文字。
        
        原始資料：{raw_data}
        """
        
        try:
            result = model.generate_content(prompt)
            
            if result and result.text:
                ai_message = result.text.strip()
                # 🛡️ 雙重保險：LINE 單則訊息字數限制約 5000 字
                if len(ai_message) > 4000:
                    ai_message = ai_message[:4000] + "... (訊息過長，已截斷)"
                send_line_message(ai_message)
                print("Success! AI Enhanced message sent.")
            else:
                raise ValueError("Gemini returned empty result")
                
        except Exception as e:
            print(f"Gemini Processing Error: {e}")
            # 🛡️ 大師最強備案：如果 AI 壞了，我們手動做一個完整的報告
            backup_msg = "🚲 Moovo 單車完整簡易報告：\n"
            for item in raw_data:
                status = "✅ 有車" if int(item['bikes']) > 0 else "❌ 沒車"
                backup_msg += f"{status} {item['name']}: {item['bikes']} 輛\n"
            send_line_message(backup_msg)
            print("AI failed, sent formatted backup message with all data.")
    else:
        print("Failed to get data.")

if __name__ == "__main__":
    asyncio.run(main())
