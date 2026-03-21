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
    try:
        requests.post(url, headers=headers, json=payload, timeout=20)
    except Exception as e:
        print(f"LINE 發送異常: {e}")

def call_gemini_direct(prompt):
    # 🎯 徹底清理金鑰（移除空格、換行、甚至引號）
    api_key = AI_KEY.strip().replace('"', '').replace("'", "")
    
    # 🔍 第一步：向 Google 索取「模型清單」，看看這把金鑰到底能看見誰
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        print("[Diagnostics] 正在檢查模型可用清單...")
        list_res = requests.get(list_url, timeout=20)
        
        if list_res.status_code != 200:
            print(f"❌ 金鑰權限檢查失敗，狀態碼: {list_res.status_code}")
            print(f"內容: {list_res.text}")
            return None
        
        models_data = list_res.json()
        # 抓出清單中所有模型的 ID
        available_models = [m['name'] for m in models_data.get('models', [])]
        print(f"✅ 偵測到可用模型: {len(available_models)} 個")

        # 🎯 第二步：從清單中挑選一個最強的來用
        target_model = ""
        preferences = ["models/gemini-1.5-flash", "models/gemini-1.5-pro", "models/gemini-pro"]
        
        for p in preferences:
            if p in available_models:
                target_model = p
                break
        
        if not target_model and available_models:
            target_model = available_models[0] # 沒魚蝦也好，抓第一個

        if not target_model:
            print("❌ 這把金鑰完全看不到任何 Gemini 模型！")
            return None

        print(f"🚀 決定使用模型: {target_model}")
        
        # 🎯 第三步：發送請求
        gen_url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        gen_res = requests.post(gen_url, headers=headers, json=payload, timeout=30)
        
        if gen_res.status_code == 200:
            return gen_res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"❌ 模型呼叫失敗: {gen_res.text}")
            return None

    except Exception as e:
        print(f"❌ 診斷過程發生異常: {e}")
        return None

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
    # 🔍 大師偵錯補丁：檢查金鑰格式
    if AI_KEY:
        prefix = AI_KEY[:4]
        print(f"[Diagnostics] 金鑰開頭為: {prefix}")
        if prefix != "AIza":
            print("❌ 警告：金鑰開頭應該是 AIza (大寫 I)，目前的看起來不對！")
        else:
            print("✅ 金鑰開頭格式正確。")
    
    print(f"[System] 啟動監測: {datetime.now()}")
    raw_data = await scrape_moovo()
    
    if raw_data:
        prompt = f"你是一個專業單車助理。請根據資料整理成溫馨的 LINE 報告。標題醒目，用 Emoji 區分有車✅與沒車❌，並列出所有場站。資料：{raw_data}"
        
        try:
            # 🚀 這裡的空格大師已經幫您算好了
            final_msg = call_gemini_direct(prompt)
            
            if final_msg:
                final_msg = final_msg.strip()
                if len(final_msg) > 4000: final_msg = final_msg[:4000] + "..."
                send_line(final_msg)
                print("Success: AI 報告已發送")
            else:
                raise ValueError("AI 回傳空值")
                
        except Exception as e:
            print(f"Fallback 啟動: {e}")
            backup = "🚲 Moovo 報告 (AI 休息中):\n"
            for item in raw_data:
                status = "✅" if int(item['bikes']) > 0 else "❌"
                backup += f"{status} {item['name']}: {item['bikes']} 輛\n"
            send_line(backup)
    else:
        print("Error: 抓取不到資料")

if __name__ == "__main__":
    asyncio.run(main())
