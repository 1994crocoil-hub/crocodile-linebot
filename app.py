import os, hashlib, hmac, base64, json, requests
from flask import Flask, request, abort
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
GEMINI_API_KEY            = os.environ.get("GEMINI_API_KEY", "")

def load_knowledge():
    base = os.path.dirname(__file__)
    with open(os.path.join(base, "data", "product_data.txt"), encoding="utf-8") as f:
        products = f.read()
    with open(os.path.join(base, "data", "qa_data.txt"), encoding="utf-8") as f:
        qa = f.read()
    return products, qa

PRODUCT_DATA, QA_DATA = load_knowledge()

SYSTEM_PROMPT = f"""你是鱷魚/必安住/孩樂/安德生品牌的「內部客服小幫手」，專門協助公司內部員工快速查詢產品資訊與回覆客戶問題。

【產品包裝標示資料庫】
{PRODUCT_DATA[:6000]}

【歷史客服Q&A記錄】
{QA_DATA[:6000]}

【回答原則】
- 用繁體中文回答，口語化親切
- 客訴問題提醒需收集：照片、購買憑證、批號
- 找不到資料就說「建議轉給相關部門確認」
- 回覆控制在200字以內
"""

def verify_signature(body, signature):
    h = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode() == signature

def ask_gemini(user_message):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\n員工問題：" + user_message}]}],
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.3}
    }
    try:
        resp = requests.post(url, json=payload, timeout=25)
        print(f"Gemini status: {resp.status_code}")
        print(f"Gemini response: {resp.text[:300]}")
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return f"⚠️ API錯誤({resp.status_code})，請稍後再試。"
    except Exception as e:
        print(f"Gemini error: {e}")
        return "⚠️ 系統暫時無法回應，請稍後再試。"

def reply_message(reply_token, text):
    requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(body, signature):
        abort(400)
    for event in json.loads(body).get("events", []):
        if event.get("type") != "message": continue
        if event["message"].get("type") != "text": continue
        reply_token = event["replyToken"]
        user_text = event["message"]["text"].strip()
        if user_text in ["你好","hello","hi","嗨"]:
            reply = "👋 嗨！我是內部客服小幫手 🦎\n\n直接輸入問題就好，例如：\n「BM020的有效成分是什麼」\n「水蒸式發煙失敗怎麼處理」"
        elif user_text in ["說明","help","功能"]:
            reply = "📖 使用說明\n\n輸入產品料號+問題，例如：\nBM020 成分\nBH60 許可證字號\n水蒸式沒有煙怎麼辦\n液體電蚊香可以給貓用嗎"
        else:
            reply = ask_gemini(user_text)
        reply_message(reply_token, reply)
    return "OK"

@app.route("/", methods=["GET"])
def health():
    return "🟢 鱷魚內部小幫手運作中"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
