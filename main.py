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

def extract_json_from_text(text):
    """Извлекает чистый JSON из ответа модели, даже если есть лишний текст"""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("JSON не найден в ответе ИИ")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Ошибка чтения истории: {e}")
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
    """Основной перевод через Groq"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
Ты — главный редактор русского IT-издания.
Переведи и перепиши эту новость НА РУССКИЙ ЯЗЫК.

Оригинальный заголовок: {news_item['title']}
Оригинальный текст: {news_item['summary']}

СТРОГИЕ ТРЕБОВАНИЯ:
1. ВЕСЬ ТЕКСТ ПОСТА И ОПРОС ДОЛЖНЫ БЫТЬ 100% НА РУССКОМ ЯЗЫКЕ.
2. Сохраняй названия компаний и технологий на английском (OpenAI, ChatGPT, Claude, Apple).
3. Используй разметку HTML (<b>жирный</b>). НЕ ИСПОЛЬЗУЙ Markdown.

Формат ответа — СТРОГО JSON:
{{
  "post_text": "<b>Заголовок на русском с эмодзи</b>\\n\\nГлавная суть новости на русском (2 коротких понятных абзаца).\\n\\n<b>Что это меняет:</b> Вывод на русском.\\n\\n#AI #Технологии",
  "poll_question": "Интересный вопрос для опроса на русском (до 100 символов)",
  "poll_option_1": "Вариант ответа 1 на русском",
  "poll_option_2": "Вариант ответа 2 на русском"
}}
"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You output strictly JSON in Russian language."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    res = requests.post(url, json=payload, headers=headers, timeout=25)
    if res.status_code == 200:
        content = res.json()['choices'][0]['message']['content']
        return extract_json_from_text(content)
    else:
        raise Exception(f"Groq HTTP {res.status_code}: {res.text}")

def translate_with_gemini(news_item):
    """Резервный перевод через Google Gemini API v1beta (обновлённый эндпоинт)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
Ты — редактор Telegram-канала "News AI Digest". Переведи новость на русский язык.

Заголовок: {news_item['title']}
Текст: {news_item['summary']}

Верни результат ИСКЛЮЧИТЕЛЬНО в формате JSON без каких-либо вводных слов:
{{
  "post_text": "<b>Заголовок на русском с эмодзи</b>\\n\\nСуть новости на русском...\\n\\n#AI #Новости",
  "poll_question": "Вопрос для опроса на русском",
  "poll_option_1": "Вариант 1 на русском",
  "poll_option_2": "Вариант 2 на русском"
}}
"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    res = requests.post(url, json=payload, headers=headers, timeout=25)
    if res.status_code == 200:
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        return extract_json_from_text(raw_text)
    else:
        raise Exception(f"Gemini HTTP {res.status_code}: {res.text}")

def generate_ai_post_and_poll(news_item):
    # 1. Запрос к Groq
    if GROQ_API_KEY:
        try:
            print("⏳ Запрос к Groq...")
            return translate_with_groq(news_item)
        except Exception as e:
            print(f"⚠️ Groq не сработал: {e}")

    # 2. Запрос к Gemini
    if GEMINI_API_KEY:
        try:
            print("⏳ Переключение на Google Gemini...")
            return translate_with_gemini(news_item)
        except Exception as e:
            print(f"⚠️ Gemini не сработал: {e}")

    # Если ни один API не ответил — возбуждаем ошибку, чтобы увидеть логи в GitHub Actions
    raise RuntimeError("❌ Ошибка: Ни Groq, ни Gemini API не смогли перевести новость. Проверьте секреты (API keys) в GitHub!")

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
    res = requests.post(url, json=payload, timeout=15)
    if res.status_code != 200:
        print(f"❌ Ошибка отправки поста: {res.text}")

def send_telegram_poll(question, option1, option2):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "question": question,
        "options": json.dumps([option1, option2]),
        "is_anonymous": True
    }
    res = requests.post(url, json=payload, timeout=15)
    if res.status_code != 200:
        print(f"❌ Ошибка отправки опроса: {res.text}")

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
