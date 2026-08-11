import os
import time
import requests
from openai import OpenAI
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ============================================================
# CONFIG
# ============================================================

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    """أنت مساعد ذكي يتحدث نيابة عن صاحب حساب Telegram.
رد بشكل طبيعي وودود ومختصر.
لا تقل إنك بوت أو ذكاء اصطناعي إلا إذا كان ذلك ضروريًا.
حافظ على سياق المحادثة.
"""
)

# ============================================================
# CLIENTS
# ============================================================

groq = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

memory = {}
MAX_MESSAGES = 20

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def telegram(method, data=None):
    response = requests.post(
        f"{TELEGRAM_API}/{method}",
        json=data or {},
        timeout=35
    )
    response.raise_for_status()
    return response.json()


# ============================================================
# AI
# ============================================================

def generate_reply(chat_id, user_text):
    if chat_id not in memory:
        memory[chat_id] = []

    history = memory[chat_id]

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": user_text
    })

    response = groq.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=800
    )

    reply = response.choices[0].message.content.strip()

    history.append({
        "role": "user",
        "content": user_text
    })

    history.append({
        "role": "assistant",
        "content": reply
    })

    if len(history) > MAX_MESSAGES:
        memory[chat_id] = history[-MAX_MESSAGES:]

    return reply


# ============================================================
# SEND MESSAGE AS BUSINESS ACCOUNT
# ============================================================

def send_business_message(chat_id, business_connection_id, text):
    return telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "business_connection_id": business_connection_id
        }
    )


# ============================================================
# MESSAGE PROCESSING
# ============================================================

def process_business_message(message):
    try:
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        business_connection_id = message.get("business_connection_id")
        text = message.get("text")

        if not chat_id or not business_connection_id or not text:
            return

        text = text.strip()
        if not text:
            return

        print(f"[Telegram] {chat_id}: {text}")

        reply = generate_reply(chat_id, text)

        print(f"[AI] {reply}")

        send_business_message(chat_id, business_connection_id, reply)

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")



# خادم بسيط لفتح Port يستجيب لـ Render
def run_dummy_server():
    port = int(os.getenv("PORT", "10000"))
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running via Long Polling")
        def log_message(self, format, *args):
            return  # إخفاء سجلات طلبات Health Check

    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

if __name__ == "__main__":
    # تشغيل خادم الـ Port في الخلفية
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # بدء البولينج
    start_polling()
