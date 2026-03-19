import asyncio
import json
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 1. 保密設定：讀取外部金鑰 =================

# 優先從「雲端環境變數 (GitHub Secrets)」讀取
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# 如果雲端找不到，就退回讀取「本機端的 config.json」
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            LINE_CHANNEL_ACCESS_TOKEN = config["LINE_CHANNEL_ACCESS_TOKEN"]
            LINE_USER_ID = config["LINE_USER_ID"]
    except Exception as e:
        print(f"❌ 讀取金鑰失敗，請確認設定: {e}")
        exit()

# 🎯 在這裡補上這一行！
TARGET_STATION = ""

# ================= 2. 資料處理與推播 =================
def parse_and_format_msg(stations_data):
    if not stations_data: 
        return "⚠️ 無法從網頁上讀取到表格資料。"
        
    msg = "🚲 Moovo 站點車輛即時回報：\n"
    found = False
    
    for station in stations_data:
        name = station.get('name', '')
        bikes = station.get('bikes', 0)
        
        if TARGET_STATION in name:
            msg += f"📍 {name}：剩餘 {bikes} 輛\n"
            found = True
            
    if not found: return f"找不到包含「{TARGET_STATION}」的站點。"
    return msg

def send_line_message(message):
    if not message: return
    line_api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}
    try:
        response = requests.post(line_api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        print("✅ 完美！LINE 通知已成功發送！")
    except Exception as e:
        print(f"❌ LINE 發送失敗: {e}")

# ================= 3. 核心：精準打擊的物理級視覺爬蟲 =================
async def scrape_table_from_screen():
    async with async_playwright() as p:
        # 可以維持 headless=True 背景執行，速度更快
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 機器人已登陸 Moovo 網頁...")
        try:
            await page.goto("https://www.ridemoovo.com/city_map_Taipei", wait_until="domcontentloaded", timeout=20000)
            print("⏳ 網頁已載入，正在等待『幻影表格』現身...")
            
            # 🎯 大師升級：不要死等 3 秒，我們直接叫機器人「盯著」那個 class 出現！
            await page.wait_for_selector('.city-location-row', timeout=15000)
            print("👁️ 看到表格了！正在刮取資料...")

            # 🚀 根據您的截圖量身打造的 JavaScript 抓取邏輯
            scraped_data = await page.evaluate('''() => {
                const results = [];
                // 鎖定所有名為 city-location-row 的 Div (這就是每一列)
                const rows = document.querySelectorAll('.city-location-row');
                
                rows.forEach(row => {
                    // 在這一列裡面，尋找名為 city-location-td 的 Div (這就是每一格)
                    const cells = row.querySelectorAll('.city-location-td');
                    
                    // 確保這一列至少有 3 格 (編號、站名、車輛數)
                    if (cells.length >= 3) {
                        const name = cells[1].innerText.trim(); 
                        const bikes = cells[2].innerText.trim();
                        
                        // 過濾掉第一列的中文標題 (例如 "租借站點查詢" 或 "可借車輛")
                        if (name !== "" && !isNaN(parseInt(bikes))) {
                            results.push({ name: name, bikes: parseInt(bikes) });
                        }
                    }
                });
                return results;
            }''')

            await browser.close()
            return scraped_data
            
        except Exception as e:
            print(f"❌ 讀取畫面發生異常: {e}")
            await browser.close()
            return None

async def main():
    print("🚀 大師級「精準打擊物理爬蟲」系統啟動！")
    scraped_data = await scrape_table_from_screen()
    
    if scraped_data:
        print(f"🎯 成功從畫面上刮下 {len(scraped_data)} 筆站點資料！")
        message = parse_and_format_msg(scraped_data)
        if message:
            send_line_message(message)
    else:
        print("❌ 抓取失敗。")

if __name__ == "__main__":
    asyncio.run(main())