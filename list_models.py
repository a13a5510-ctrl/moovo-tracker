import requests
import os

def list_available_models():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    print("📡 [後勤部隊：可用模型清單偵察]")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            models = res.json().get('models', [])
            print(f"✅ 成功截獲 {len(models)} 個可用模型節點：")
            for m in models:
                print(f"   - {m['name']}")
        else:
            print(f"❌ 偵察失敗，代碼：{res.status_code}")
            print(f"   訊息：{res.text}")
    except Exception as e:
        print(f"🚫 連線中斷：{e}")

if __name__ == "__main__":
    list_available_models()
