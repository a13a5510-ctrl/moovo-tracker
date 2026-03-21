import asyncio
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright
from google import genai

# ================= 1. 配置與初始化 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")

# 🔐 初始化 AI 客戶端 (確保縮排正確且指定 v1 版本)
try:
    client = genai.Client(api_key=AI_KEY, http_options={'api_version': 'v1'})
except Exception as e:
    print(f"Client Setup Error: {e}")

# ================= 2. 功能函數 =================
def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_TARGET, "messages": [{"type": "text", "text": msg}]}
    requests.post(url, headers=headers, json=payload)

async def scrape_moovo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('.city-location-row', timeout=20000)
            data = await page.evaluate('''() => {
                const results = [];
                document.querySelectorAll('.city-location-row').forEach(row => {
                    const cells = row.querySelectorAll('.city-location-td');
                    if (cells.length >= 3) {
                        results.push({ name: cells[1].innerText.trim(), bikes: cells[2].innerText.trim() });
                    }
                });
                return results;
            }''')
            await browser.close()
            return data
        except Exception as e:
            print(f"Scrape Error: {e}")
            await browser.close()
            return None

# ================= 3. 主流程 =================
async def main():
    print(f"[System] 啟動監測: {datetime.now()}")
    raw_data = await scrape_moovo()
    
    if raw_data:
        prompt = f"你是一個專業單車助理。請根據資料整理成溫馨的 LINE 報告。標題醒目，用 Emoji 區分有車✅與沒車❌，並列出所有場站。資料：{raw_data}"
        
        try:
            # 🚀 AI 美化處理 (嚴格縮排)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            if response and response.text:
                final_msg = response.text.strip()
                if len(final_msg) > 4000: final_msg = final_msg[:4000] + "..."
                send_line(final_msg)
                print("Success: AI 報告已發送")
            else:
                raise ValueError("AI 回傳空值")
                
        except Exception as e:
            # 🛡️ 緊急備案 (嚴格縮排)
            print(f"Fallback Error: {e}")
            backup = "🚲 Moovo 報告 (AI 休息中):\n"
            for item in raw_data:
                status = "✅" if int(item['bikes']) > 0 else "❌"
                backup += f"{status} {item['name']}: {item['bikes']} 輛\n"
            send_line(backup)
    else:
        print("Error: 抓取不到資料")

if __name__ == "__main__":
    asyncio.run(main())
