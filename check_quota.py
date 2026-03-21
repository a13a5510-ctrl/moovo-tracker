import requests
import os
from datetime import datetime, timedelta

def spy_check():
    # 🎯 取得金鑰並清理空格
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("❌ 錯誤：找不到 API 金鑰，請檢查 GitHub Secrets。")
        return

    # 偵察目標模型
    models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]
    
    # 台北時間校正
    current_time = datetime.utcnow() + timedelta(hours=8)
    
    print("="*50)
    print(f"🛡️ [後勤部隊：API 存量偵察報告]")
    print(f"⏰ 偵測時間：{current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        # 使用極低量數據 (1 個點) 進行測試，不浪費 Token
        payload = {"contents": [{"parts": [{"text": "."}]}]}
        
        try:
            res = requests.post(url, json=payload, timeout=15)
            if res.status_code == 200:
                print(f"✅ {model:18} | 狀態：正常 (可即時出動)")
            elif res.status_code == 429:
                # 取得 Google 的報錯訊息，通常會包含重試時間
                msg = res.json().get('error', {}).get('message', '配額已達上限')
                print(f"❌ {model:18} | 狀態：額度耗盡 (429)")
                print(f"   👉 訊息：{msg}")
            elif res.status_code == 404:
                print(f"⚠️ {model:18} | 狀態：路徑失效 (404)")
            else:
                print(f"❓ {model:18} | 狀態：異常 (代碼 {res.status_code})")
        except Exception as e:
            print(f"🚫 {model:18} | 狀態：連線超時 ({str(e)})")
            
    print("="*50)
    print("💡 提示：若 1.5-Flash 為正常，Moovo 監控即可正常運作。")
    print("="*50)

if __name__ == "__main__":
    spy_check()
