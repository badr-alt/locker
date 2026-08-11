import os
import time
import requests
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


# ============================================================
# POLLING LOOP
# ============================================================

def start_polling():
    # إلغاء الـ Webhook القديم لتجنب التعارض (Conflict Error)
    try:
        telegram("deleteWebhook", {"drop_pending_updates": False})
        print("[WEBHOOK] Deleted successfully.")
    except Exception as e:
        print(f"[WEBHOOK DELETE ERROR] {e}")

    offset = 0
    print("[BOT] Starting Long Polling...")

    while True:
        try:
            data = {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": [
                    "business_connection",
                    "business_message",
                    "edited_business_message",
                    "deleted_business_messages"
                ]
            }

            updates = telegram("getUpdates", data).get("result", [])

            for update in updates:
                offset = update["update_id"] + 1

                message = update.get("business_message")
                if message:
                    process_business_message(message)

        except requests.exceptions.RequestException as e:
            print(f"[NETWORK ERROR] {e}")
            time.sleep(5)
        except Exception as e:
            print(f"[POLLING ERROR] {e}")
            time.sleep(3)


if __name__ == "__main__":
    start_polling()
