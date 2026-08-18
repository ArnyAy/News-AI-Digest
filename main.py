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

# ---------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ---------------------------------------------------------
def clean_html(raw_html):
    """Удаляет HTML-теги и лишние пробелы из текста RSS"""
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    for feed_url in RSS_FEEDS:
        try:
            # Получаем ленту с заголовками, чтобы избежать блокировок
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
            print(f"Ошибка при чтении ленты {feed_url}: {e}")
            continue
    return None

def generate_ai_post_and_poll(news_item):
    """Генерирует переведенный пост НА РУССКОМ и опрос через Groq API"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
Переведи и перепиши эту IT-новость НА РУССКИЙ ЯЗЫК для Telegram-канала "News AI Digest".

Оригинальный заголовок: {news_item['title']}
Оригинальный текст: {news_item['summary']}

СТРОГИЕ ПРАВИЛА:
1. ВЕСЬ ТЕКСТ, ЗАГОЛОВОК И ОПРОС ДОЛЖНЫ БЫТЬ СТРОГО НА РУССКОМ ЯЗЫКЕ!
2. Все названия компаний и технологий оставляй на английском без транслитерации (Amazon, Twitch, Claude, OpenAI, ChatGPT, Midjourney).
3. Используй HTML для Telegram (<b>жирный</b>). НЕ ИСПОЛЬЗУЙ Markdown (**).
4. Формат ответа — СТРОГО JSON с указанными ключами:
{{
  "post_text": "<b>Яркий заголовок с эмодзи на русском</b>\\n\\nГлавная суть новости на русском (2 коротких понятных абзаца).\\n\\n<b>Что это меняет:</b> Вывод на русском.\\n\\n#AI #Технологии",
  "poll_question": "Интересный вопрос для опроса на русском (до 100 символов)",
  "poll_option_1": "Вариант ответа 1 на русском",
  "poll_option_2": "Вариант ответа 2 на русском"
}}
"""

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system", 
                "content": "You are a professional Russian translator and editor. Always output valid JSON and translate everything into Russian."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=20)
        if res.status_code == 200:
            content = res.json()['choices'][0]['message']['content']
            return json.loads(content)
        else:
            print(f"❌ Ошибка Groq API (Код {res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ Исключение при запросе к AI API: {e}")
    
    # Аварийный вариант (fallback), если Groq API вернул ошибку
    return {
        "post_text": f"🤖 <b>[Ошибка перевода AI] {news_item['title']}</b>\n\nНе удалось автоматически перевести новость. Оригинальное описание:\n{news_item['summary'][:300]}...",
        "poll_question": "Интересна ли вам эта тема?",
        "poll_option_1": "👍 Да",
        "poll_option_2": "👎 Нет"
    }

def generate_free_image_url(prompt_text):
    """Генерация яркой 3D/cyberpunk обложки"""
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
    res = requests.post(url, json=payload, timeout=15)
    if res.status_code != 200:
        print(f"❌ Ошибка отправки поста в Telegram: {res.text}")

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
        print(f"❌ Ошибка отправки опроса в Telegram: {res.text}")

# ---------------------------------------------------------
# ОСНОВНОЙ ЗАПУСК
# ---------------------------------------------------------
if __name__ == "__main__":
    if not GROQ_API_KEY or not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("❌ Ошибка: Не все переменные окружения (GROQ_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID) заданы!")
        exit(1)

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
