import asyncio
import json
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright

# ================= 1. 保密設定：讀取金鑰 =================
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
    print("Error: Missing LINE Credentials in Environment Secrets")
    exit()

TARGET_STATION = "" 

# ================= 2. 資料處理與推播 =================
def parse_and_format_msg(stations_data):
    if not stations_data: 
        return "Warning: No table data found on webpage."
        
    msg = "Moovo Station Report:\n"
    found = False
    
    for station in stations_data:
        name = station.get('name', '')
        bikes = station.get('bikes', 0)
        
        if TARGET_STATION in name:
            msg += f"Station: {name} | Bikes: {bikes}\n"
            found = True
            
    if not found: return f"Cannot find station containing: {TARGET_STATION}"
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
        print(f"LINE API Response: {response.status_code} | {response.text}")
        response.raise_for_status()
        print("LINE notification sent successfully!")
    except Exception as e:
        print(f"LINE send failed: {e}")

# ================= 3. 核心：物理級視覺爬蟲 =================
async def scrape_table_from_screen():
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
                            results.push({ name: name, bikes: parseInt(bikes) });
                        }
                    }
                });
                return results;
            }''')
            await browser.close()
            return scraped_data
        except Exception as e:
            print(f"Scrape Error: {e}")
            await browser.close()
            return None

async def main():
    print("[System] Moovo Tracker Started!")
    scraped_data = await scrape_table_from_screen()
    
    if scraped_data:
        print(f"Success! Scraped {len(scraped_data)} stations.")
        message = parse_and_format_msg(scraped_data)
        if message:
            send_line_message(message)
    else:
        print("Scrape failed.")

if __name__ == "__main__":
    asyncio.run(main())
