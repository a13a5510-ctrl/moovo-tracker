import asyncio
import os
import requests
import json
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 1. 配置 =================
LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TARGET = os.getenv("LINE_USER_ID")
AI_KEY = os.getenv("GEMINI_API_KEY")

# ================= 2. 功能函數 =================
def send_line(msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_TARGET, "messages": [{"type": "text", "text": msg}]}
    requests.post(url, headers=headers, json=payload)

def call_gemini_direct(prompt):
    # 🎯 終極對位：注意 models 前面沒有斜線，它是跟在 v1/ 後面的
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={AI_KEY}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

try:
        # 🚀 增加偵錯資訊，讓我們知道到底發生了什麼
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            res_json = response.json()
            return res_json['candidates'][0]['content']['parts'][0]['text']
        else:
            # 這裡會印出詳細的錯誤訊息，幫我們抓鬼
            print(f"[Debug] API 失敗回傳: {response.text}")
            return None
            
    except Exception as e:
        print(f"[Debug] 請求異常: {e}")
        return None
            
        res_json = response.json()
        return res_json['candidates'][0]['content']['parts'][0]['text']
        
    except Exception as e:
        print(f"[Debug] API 請求發生異常: {e}")
        return None
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    else:
        raise Exception(f"API 報錯: {response.text}")

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
            # 🚀 使用手動擋呼叫 AI
            final_msg = call_gemini_direct(prompt)
            
            if final_msg:
                final_msg = final_msg.strip()
                if len(final_msg) > 4000: final_msg = final_msg[:4000] + "..."
                send_line(final_msg)
                print("Success: AI 報告已發送")
            else:
                raise ValueError("AI 回傳空值")
                
        except Exception as e:
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
