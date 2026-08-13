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
# Вспомогательные функции
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

def generate_ai_post_and_poll(news_item):
    """Ггенерирует пост НА РУССКОМ и сочный опрос"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    Ты — шеф-редактор ведущего русскоязычного IT-медиа "News AI Digest".
    Твоя задача: перевести английскую новость и переписать её в увлекательный пост ДЛЯ РУССКОЯЗЫЧНОЙ АУДИТОРИИ.

    Оригинальный заголовок: {news_item['title']}
    Оригинальный текст: {news_item['summary']}

    ЖЁСТКИЕ ПРАВИЛА:
    1. ТЕКСТ ПОСТА И ОПРОС ДОЛЖНЫ БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ!
    2. Все названия компаний и технологий пиши на английском без транслита (Amazon, Twitch, Claude, OpenAI, ChatGPT, Midjourney).
    3. Используй HTML для Telegram (<b>жирный</b>). НЕ ИСПОЛЬЗУЙ **.
    4. Структура поста:
       - Яркий заголовок с 1-2 эмодзи
       - Главная суть новости (2 коротких понятных абзаца)
       - Главный вывод / Что это меняет
       - 3-4 релевантных хэштега на русском/английском.
    5. Формат ответа — СТРОГО JSON:
    {{
        "post_text": "<b>Заголовок</b>\\n\\nТекст новости на русском...\\n\\n#AI #Twitch",
        "poll_question": "Интересный вопрос для опроса на русском (до 100 символов)",
        "poll_option_1": "Вариант ответа 1 на русском",
        "poll_option_2": "Вариант ответа 2 на русском"
    }}
    """

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a professional editor writing strictly in RUSSIAN language."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "response_format": {"type": "json_object"}
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            return json.loads(res.json()['choices'][0]['message']['content'])
    except Exception as e:
        print(f"Ошибка AI API: {e}")
    
    return {
        "post_text": f"🚀 <b>{news_item['title']}</b>\n\n{news_item['summary'][:300]}...",
        "poll_question": "Что думаете про эту новость?",
        "poll_option_1": "👍 Отличные новости",
        "poll_option_2": "👎 Сомнительно"
    }

def generate_free_image_url(prompt_text):
    """Генерация яркой, сочной 3D/cyberpunk обложки"""
    clean_prompt = f"vibrant colorful 3d digital render, futuristic tech concept, neon lighting, highly detailed, sharp focus, {prompt_text[:40]}"
    encoded_prompt = quote(clean_prompt)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=500&nologo=true"

def send_telegram_post(text, image_url, source_link):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    reply_markup = {
        "inline_keyboard": [[{"text": "🔗 Читать источник", "url": source_link}]]
    }
    
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
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
        print(f"Найдена новость: {news['title']}")
        ai_data = generate_ai_post_and_poll(news)
        image_url = generate_free_image_url(news['title'])
        
        send_telegram_post(ai_data['post_text'], image_url, news['link'])
        
        send_telegram_poll(
            ai_data['poll_question'], 
            ai_data['poll_option_1'], 
            ai_data['poll_option_2']
        )
        
        history.add(news['link'])
        save_history(history)
        print("Пост и опрос успешно опубликованы!")
    else:
        print("Свежих новостей пока нет.")
