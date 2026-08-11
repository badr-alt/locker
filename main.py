import os
import threading
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

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

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-this-secret")

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

# ============================================================
# CLIENTS
# ============================================================

app = Flask(__name__)

groq = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ذاكرة مؤقتة للمحادثات
# ستختفي عند إعادة تشغيل Render.
memory = {}

MAX_MESSAGES = 20

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def telegram(method, data):
    response = requests.post(
        f"{TELEGRAM_API}/{method}",
        json=data,
        timeout=20
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

    # حفظ المحادثة
    history.append({
        "role": "user",
        "content": user_text
    })

    history.append({
        "role": "assistant",
        "content": reply
    })

    # تحديد حجم الذاكرة
    if len(history) > MAX_MESSAGES:
        memory[chat_id] = history[-MAX_MESSAGES:]

    return reply


# ============================================================
# SEND MESSAGE AS BUSINESS ACCOUNT
# ============================================================

def send_business_message(
    chat_id,
    business_connection_id,
    text
):

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

        business_connection_id = message.get(
            "business_connection_id"
        )

        text = message.get("text")

        if not chat_id:
            return

        if not business_connection_id:
            return

        if not text:
            return

        # تجاهل الرسائل الفارغة
        text = text.strip()

        if not text:
            return

        print(
            f"[Telegram] {chat_id}: {text}"
        )

        # توليد الرد
        reply = generate_reply(
            chat_id,
            text
        )

        print(
            f"[AI] {reply}"
        )

        # إرسال الرد من الحساب الشخصي
        send_business_message(
            chat_id,
            business_connection_id,
            reply
        )

    except Exception as e:

        print(
            f"[ERROR] {type(e).__name__}: {e}"
        )


# ============================================================
# WEBHOOK
# ============================================================

@app.post("/webhook")
def webhook():

    # التحقق من Telegram Secret Token
    received_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )

    if received_secret != WEBHOOK_SECRET:
        return jsonify({
            "ok": False,
            "error": "Unauthorized"
        }), 401

    update = request.get_json(
        silent=True
    ) or {}

    # رسائل Business
    message = update.get(
        "business_message"
    )

    if message:

        # تشغيل المعالجة في الخلفية
        thread = threading.Thread(
            target=process_business_message,
            args=(message,),
            daemon=True
        )

        thread.start()

    return jsonify({
        "ok": True
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def home():

    return jsonify({
        "status": "online",
        "service": "Telegram AI Business Bot",
        "model": MODEL
    })


# ============================================================
# SET TELEGRAM WEBHOOK
# ============================================================

def setup_webhook():

    if not RENDER_URL:
        print(
            "[WARNING] RENDER_EXTERNAL_URL not found."
        )
        return

    webhook_url = (
        RENDER_URL.rstrip("/")
        + "/webhook"
    )

    result = telegram(
        "setWebhook",
        {
            "url": webhook_url,

            "secret_token": WEBHOOK_SECRET,

            "allowed_updates": [
                "business_connection",
                "business_message",
                "edited_business_message",
                "deleted_business_messages"
            ],

            "drop_pending_updates": False
        }
    )

    print(
        "[WEBHOOK]",
        result
    )


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":

    setup_webhook()

    port = int(
        os.getenv("PORT", "10000")
    )

    app.run(
        host="0.0.0.0",
        port=port
    )