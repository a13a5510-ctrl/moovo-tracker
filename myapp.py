import asyncio
import json
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright
# 🎯 2026 全新版 Google AI 套件
from google import genai 

# ================= 1. 保密設定與 AI 配置 =================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID") # 這裡現在存放的是您的 Group ID (C開頭)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 🔐 使用最新版 Client 呼叫方式，徹底解決 404 問題
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"AI Client Setup Error: {e}")

if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID, GEMINI_API_KEY]):
    print("Error: 遺漏環境變數設定 (Secrets)，請檢查 GitHub 設定。")
    exit()

# ================= 2. LINE 發送功能 =================
def send_line_message(message):
    if not message: return
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

# ================= 3. 核心：全面網頁抓取 =================
async def scrape_moovo():
    async with async_playwright() as p:
        # 啟動瀏覽器
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        print("[System] 正在前往 Moovo 網頁抓取即時資料...")
        try:
            # 載入台北市地圖頁面
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=30000)
            # 等待場站清單現身
            await page.wait_for_selector('.city-location-row', timeout=20000)
            
            # 抓取所有站點名稱與車輛數
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
                return results; // 回傳完整清單
            }''')
            await browser.close()
            return scraped_data
        except Exception as e:
            print(f"Scrape Error: {e}")
            await browser.close()
            return None

# ================= 4. 主程式：AI 美化與排程執行 =================
async def main():
    print(f"[System] 萬用杯麵啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    raw_data = await scrape_moovo()
    
    if raw_data:
        print(f"[System] 成功抓取 {len(raw_data)} 個場站資訊。")
        
        # 🎯 給 Gemini 的精準指令
        prompt = f"""
你現在是群組專屬的「Moovo 場站監測員」。請根據以下資料，撰寫一段溫馨、專業且易讀的監測報告。
要求：
1. 使用繁體中文。
2. 標題要醒目（例如：🚲 Moovo 完整巡邏報報）。
3. 使用 Emoji 區分「有車 ✅」與「目前沒車 ❌」。
4. 請列出**所有**場站，不要省略任何一站。
5. 最後給予一句溫馨的小提醒（關於騎車安全或天氣）。
資料如下：{raw_data}
"""
        
        try:
            # 🚀 2026 全新呼叫語法，徹底閃避 404 錯誤
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            
            if response and response.text:
                ai_message = response.text.strip()
                # 防止訊息過長 (LINE 限制為 5000 字)
                if len(ai_message) > 4000:
                    ai_message = ai_message[:4000] + "\n...(訊息過長已截斷)"
                
                send_line_message(ai_message)
                print("Success! AI Enhanced message sent.")
            else:
                raise ValueError("Gemini 回傳內容為空")
                
        except Exception as e:
            # 🛡️ 救災系統：AI 故障時的備案
            print(f"Gemini Error (啟動緊急備案): {e}")
            backup_msg = "🚲 Moovo 場站簡易報告 (AI 休息中)：\n"
            for item in raw_data:
                status = "✅" if int(item['bikes']) > 0 else "❌"
                backup_msg += f"{status} {item['name']}: {item['bikes']} 輛\n"
            send_line_message(backup_msg)
            
    else:
        print("Error: 無法抓取到任何資料，請檢查網頁連線。")

if __name__ == "__main__":
    asyncio.run(main())
