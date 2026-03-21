import requests
import os
import time
from datetime import datetime, timedelta

def spy_check():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("❌ 錯誤：找不到金鑰")
        return

    models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
    tp_time = datetime.utcnow() + timedelta(hours=8)
    
    print(f"🛡️ [後勤診斷] 台北時間：{tp_time.strftime('%H:%M:%S')}")
    
    for model in models:
        # 🎯 雙重門路測試：先試 v1，不行再試 v1beta
        versions = ["v1", "v1beta"]
        success = False
        
        for ver in versions:
            url = f"https://generativelanguage.googleapis.com/{ver}/models/{model}:generateContent?key={api_key}"
            try:
                res = requests.post(url, json={"contents": [{"parts": [{"text": "."}]}]}, timeout=10)
                if res.status_code == 200:
                    print(f"✅ {model:18} | 門路 {ver:6}：正常")
                    success = True
                    break # 成功就跳出這型號的測試
                elif res.status_code == 429:
                    print(f"❌ {model:18} | 門路 {ver:6}：頻率限制 (429) - 請稍後再試")
                    success = True # 雖失敗但路徑是對的
                    break
            except: continue
        
        if not success:
            print(f"⚠️ {model:18} | 狀態：全線 404 (權限尚未同步或模型不可用)")
        
        # 🛑 暫停 2 秒，避免敲門太快觸發 429
        time.sleep(2)

if __name__ == "__main__":
    spy_check()
