import os
import json
import re
import requests
import feedparser
from urllib.parse import quote

# ---------------------------------------------------------
# КОНФИГУРАЦИЯ И ИСТОЧНИКИ
# ---------------------------------------------------------
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://habr.com/ru/rss/hub/artificial_intelligence/all/"
]

HISTORY_FILE = "published_history.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ---------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ---------------------------------------------------------
def clean_html(raw_html):
    """Очищает текст от HTML-тегов и лишних пробелов"""
    if not raw_html:
        return ""
    clean_text = re.sub(r'<[^>]+>', '', raw_html)
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return clean_text.strip()

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_history(history):
    recent_history = list(history)[-200:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(recent_history, f, ensure_ascii=False, indent=2)

def get_unique_news(history):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    for feed_url in RSS_FEEDS:
        try:
            response = requests.get(feed_url, headers=headers, timeout=10)
            feed = feedparser.parse(response.content)
            for entry in feed.entries:
                link = entry.link
                if link not in history:
                    raw_summary = entry.get("summary", entry.get("description", ""))
                    return {
                        "title": clean_html(entry.title),
                        "link": link,
                        "summary": clean_html(raw_summary)
                    }
        except Exception as e:
            print(f"Ошибка чтения ленты {feed_url}: {e}")
            continue
    return None

def translate_with_groq(news_item):
    """Основной перевод через Llama 3.3 70B"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
Ты — главный редактор русского IT-издания.
Переведи и адаптируй новость НА РУССКИЙ ЯЗЫК.

Оригинальный заголовок: {news_item['title']}
Оригинальный текст: {news_item['summary']}

ПРАВИЛА:
1. ВЕСЬ ТЕКСТ ПОСТА И ОПРОСА ДОЛЖЕН БЫТЬ 100% НА РУССКОМ ЯЗЫКЕ.
2. Сохраняй бренды и названия технологий на английском (OpenAI, ChatGPT, Claude, Apple, Google).
3. Форматирование: используй HTML (<b>жирный</b>). НЕ ИСПОЛЬЗУЙ Markdown (**).

Формат ответа — СТРОГО JSON:
{{
  "post_text": "<b>Заголовок с эмодзи на русском</b>\\n\\nГлавная суть новости на русском (2 коротких абзаца).\\n\\n<b>Что это меняет:</b> Вывод на русском.\\n\\n#AI #Технологии",
  "poll_question": "Интересный вопрос для опроса на русском",
  "poll_option_1": "Вариант 1 на русском",
  "poll_option_2": "Вариант 2 на русском"
}}
"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system", 
                "content": "You are a professional editor. Translate every single phrase into Russian. Do not output English sentences."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    res = requests.post(url, json=payload, headers=headers, timeout=25)
    if res.status_code == 200:
        return json.loads(res.json()['choices'][0]['message']['content'])
    else:
        raise Exception(f"Groq API Error {res.status_code}: {res.text}")

def translate_with_gemini(news_item):
    """Запасной перевод через Google Gemini 1.5 Flash"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
Ты — редактор русскоязычного Telegram-канала "News AI Digest". 
Переведи эту новость полностью на русский язык и сделай из неё качественный пост.

Заголовок: {news_item['title']}
Текст: {news_item['summary']}

Требования:
1. Текст поста и варианты ответа в опросе должны быть НА РУССКОМ ЯЗЫКЕ.
2. Используй HTML-разметку (<b>жирный</b>).
3. Верни результат строго в формате JSON:

{{
  "post_text": "<b>Заголовок на русском</b>\\n\\nСуть новости на русском...\\n\\n#AI #Новости",
  "poll_question": "Вопрос для опроса на русском",
  "poll_option_1": "Вариант 1 на русском",
  "poll_option_2": "Вариант 2 на русском"
}}
"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    res = requests.post(url, json=payload, headers=headers, timeout=25)
    if res.status_code == 200:
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        return json.loads(raw_text)
    else:
        raise Exception(f"Gemini API Error {res.status_code}: {res.text}")

def generate_ai_post_and_poll(news_item):
    # 1. Сначала пробуем Groq (Llama 3.3 70B)
    if GROQ_API_KEY:
        try:
            print("⏳ Запрос к Groq (Llama 3.3 70B)...")
            return translate_with_groq(news_item)
        except Exception as e:
            print(f"⚠️ Groq не ответил: {e}")

    # 2. Если Groq выдал ошибку — переключаемся на Gemini
    if GEMINI_API_KEY:
        try:
            print("⏳ Переключение на Google Gemini...")
            return translate_with_gemini(news_item)
        except Exception as e:
            print(f"⚠️ Gemini не ответил: {e}")

    # 3. Резервный случай
    return {
        "post_text": f"🚀 <b>{news_item['title']}</b>\n\n{news_item['summary'][:300]}...",
        "poll_question": "Что думаете?",
        "poll_option_1": "👍 Интересно",
        "poll_option_2": "👎 Нет"
    }

def generate_free_image_url(prompt_text):
    clean_prompt = f"vibrant colorful 3d digital render, futuristic tech concept, neon lighting, {prompt_text[:40]}"
    return f"https://image.pollinations.ai/prompt/{quote(clean_prompt)}?width=800&height=500&nologo=true"

def send_telegram_post(text, image_url, source_link):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": "🔗 Читать источник", "url": source_link}]]})
    }
    requests.post(url, json=payload, timeout=15)

def send_telegram_poll(question, option1, option2):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "question": question,
        "options": json.dumps([option1, option2]),
        "is_anonymous": True
    }
    requests.post(url, json=payload, timeout=15)

# ---------------------------------------------------------
# ОСНОВНОЙ ЗАПУСК
# ---------------------------------------------------------
if __name__ == "__main__":
    history = load_history()
    news = get_unique_news(history)

    if news:
        print(f"📰 Найдена новость: {news['title']}")
        ai_data = generate_ai_post_and_poll(news)
        image_url = generate_free_image_url(news['title'])
        
        send_telegram_post(ai_data['post_text'], image_url, news['link'])
        send_telegram_poll(ai_data['poll_question'], ai_data['poll_option_1'], ai_data['poll_option_2'])
        
        history.add(news['link'])
        save_history(history)
        print("✅ Пост и опрос успешно опубликованы!")
    else:
        print("ℹ️ Свежих новостей пока нет.")
