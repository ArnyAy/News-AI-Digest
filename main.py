import os
import json
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

# ---------------------------------------------------------
# ФУНКЦИИ
# ---------------------------------------------------------
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
    """Ищет свежую новость, которой нет в истории"""
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            link = entry.link
            if link not in history:
                return {
                    "title": entry.title,
                    "link": link,
                    "summary": entry.get("summary", entry.get("description", ""))
                }
    return None

def generate_ai_post(news_item):
    """Генерация текста поста через бесплатный Groq API (Llama 3)"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    Ты — главный редактор популярного Telegram-канала про ИИ и технологии.
    Преобразуй новость в сочный, структурированный и уникальный пост на русском языке.

    Заголовок: {news_item['title']}
    Текст: {news_item['summary']}

    Правила:
    1. Завлекающий заголовок с цепляющими эмодзи.
    2. Суть новости в 2-3 коротких и понятных абзацах.
    3. Вывод или почему это важно.
    4. 3-4 релевантных хэштега в конце.
    Выдавай ТОЛЬКО готовый текст поста, без приветствий и вводных фраз.
    """

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Ошибка AI API: {e}")
    
    # Резервный формат, если AI недоступен
    return f"🚀 <b>{news_item['title']}</b>\n\n{news_item['summary'][:300]}...\n\n🔗 <a href='{news_item['link']}'>Читать источник</a>"

def generate_free_image_url(prompt_text):
    """Создание обложки по теме новости без API-ключей"""
    clean_prompt = f"abstract futuristic concept AI technology, {prompt_text[:50]}"
    encoded_prompt = quote(clean_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=500&nologo=true"

def send_telegram_post(text, image_url):
    """Отправка поста в Telegram-канал"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": text,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload, timeout=15)

# ---------------------------------------------------------
# ОСНОВНОЙ ЗАПУСК
# ---------------------------------------------------------
if __name__ == "__main__":
    history = load_history()
    news = get_unique_news(history)

    if news:
        print(f"Найдена новость: {news['title']}")
        post_text = generate_ai_post(news)
        image_url = generate_free_image_url(news['title'])
        
        send_telegram_post(post_text, image_url)
        
        history.add(news['link'])
        save_history(history)
        print("Пост успешно опубликован в канал!")
    else:
        print("Свежих новостей пока не найдено.")
