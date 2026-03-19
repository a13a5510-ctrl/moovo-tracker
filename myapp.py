# ================= 2. 資料處理與推播 =================
def parse_and_format_msg(stations_data):
    if not stations_data: 
        return "Warning: No table data found on webpage."
        
    msg = "Moovo Station Report:\n" # 這裡原本有單車圖示，請刪掉
    found = False
    
    for station in stations_data:
        name = station.get('name', '')
        bikes = station.get('bikes', 0)
        
        if TARGET_STATION in name:
            msg += f"Station: {name} | Bikes: {bikes}\n" # 這裡原本有圖釘圖示，請刪掉
            found = True
            
    if not found: return f"Cannot find station containing: {TARGET_STATION}"
    return msg

def send_line_message(message):
    # ... 中間 LINE 發送邏輯不變 ...
    try:
        response = requests.post(line_api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        print("LINE notification sent successfully!") # 原本有勾勾，請刪掉
    except Exception as e:
        print(f"LINE send failed: {e}")

# ... 中間 Playwright 抓取邏輯 ...

async def main():
    print("[System] Moovo Tracker Started!") # 原本有火箭，請刪掉
    scraped_data = await scrape_table_from_screen()
    
    if scraped_data:
        print(f"Success! Scraped {len(scraped_data)} stations.") # 原本有目標圖示，請刪掉
        message = parse_and_format_msg(scraped_data)
        if message:
            send_line_message(message)
    else:
        print("Scrape failed.")
