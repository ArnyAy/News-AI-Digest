import os
import json
import re
import random
import time
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
    if not raw_html:
        return ""
    clean_text = re.sub(r'<[^>]+>', '', raw_html)
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return clean_text.strip()

def extract_json_from_text(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("JSON не найден в ответе")

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
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(recent_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения истории: {e}")

def get_unique_news(history):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
Ты — главный редактор IT-издания. Переведи новость НА РУССКИЙ ЯЗЫК.

Заголовок: {news_item['title']}
Текст: {news_item['summary']}

Верни строго JSON:
{{
  "post_text": "<b>Заголовок на русском</b>\\n\\nСуть новости на русском...\\n\\n#AI #Технологии",
  "poll_question": "Интересный опрос на русском",
  "poll_option_1": "Вариант 1",
  "poll_option_2": "Вариант 2"
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

    res = requests.post(url, json=payload, headers=headers, timeout=20)
    if res.status_code == 200:
        content = res.json()['choices'][0]['message']['content']
        return extract_json_from_text(content)
    else:
        raise Exception(f"Groq API Error {res.status_code}")

def translate_with_gemini(news_item):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
Переведи новость на русский язык и верни строго JSON:
Заголовок: {news_item['title']}
Текст: {news_item['summary']}

Формат JSON:
{{
  "post_text": "<b>Заголовок на русском</b>\\n\\nСуть новости на русском...\\n\\n#AI #Новости",
  "poll_question": "Вопрос для опроса на русском",
  "poll_option_1": "Вариант 1",
  "poll_option_2": "Вариант 2"
}}
"""
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    res = requests.post(url, json=payload, headers=headers, timeout=20)
    if res.status_code == 200:
        raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
        return extract_json_from_text(raw_text)
    else:
        raise Exception(f"Gemini API Error {res.status_code}")

def translate_fallback_free(text):
    try:
        url = f"https://api.mymemory.translated.net/get?q={quote(text[:450])}&langpair=en|ru"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()['responseData']['translatedText']
    except Exception as e:
        print(f"Ошибка бесплатного перевода: {e}")
    return text

def generate_ai_post_and_poll(news_item):
    if GROQ_API_KEY:
        try:
            print("⏳ Запрос к Groq...")
            return translate_with_groq(news_item)
        except Exception as e:
            print(f"⚠️ Groq пропущен: {e}")

    if GEMINI_API_KEY:
        try:
            print("⏳ Запрос к Gemini...")
            return translate_with_gemini(news_item)
        except Exception as e:
            print(f"⚠️ Gemini пропущен: {e}")

    print("⚠️ Используем резервный онлайн-перевод...")
    ru_title = translate_fallback_free(news_item['title'])
    ru_summary = translate_fallback_free(news_item['summary'][:400])

    return {
        "post_text": f"🚀 <b>{ru_title}</b>\n\n{ru_summary}...\n\n#AI #Технологии",
        "poll_question": "Как вам эта новость?",
        "poll_option_1": "👍 Перспективно",
        "poll_option_2": "🤔 Сомнительно"
    }

def generate_smart_image_prompt(news_title):
    """Генерирует сюжетный промпт в стиле мультиков Pixar/Disney"""
    if not GEMINI_API_KEY:
        return f"cute Pixar 3D animated character representing {news_title[:40]}, Disney animation style, vibrant colors, expressive character, detailed environment"
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        prompt = f"""
На основе новости: "{news_title}" придумай промпт для генерации картинки В СТИЛЕ МУЛЬТФИЛЬМОВ PIXAR / DISNEY / 3D ANIMATION.

Требования:
1. Придумай конкретного милого персонажа или предмет (например: робот, персонаж, метафора новости), который что-то делает.
2. Стиль: "Pixar 3D animation style, Disney, cute character, vibrant bright colors, expressive faces, octane render, highly detailed, soft lighting".
3. Ответ должен быть СТРОГО на английском языке, ровно 1 предложение. Без кавычек, без вводных слов.
"""
        
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            generated_prompt = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return generated_prompt
    except Exception as e:
        print(f"⚠️ Сбой генерации промпта для картинки: {e}")
        
    return f"cute Pixar 3D animated character working on high tech factory, vibrant colors, highly detailed, disney animation style"

def generate_free_image_url(news_title):
    art_prompt = generate_smart_image_prompt(news_title)
    print(f"🎨 Мультяшный промпт: {art_prompt}")
    
    # 1. Генерируем уникальный seed и timestamp для предотвращения кэширования
    seed = random.randint(1, 999999)
    ts = int(time.time())
    
    encoded_prompt = quote(f"{art_prompt}, masterpiece, 8k")
    
    # 2. Передаем seed и дополнительный параметр cb (cache buster)
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=675&model=flux&nologo=true&seed={seed}&cb={ts}"

def send_telegram_post(text, image_url, source_link):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": "🔗 Читать источник", "url": source_link}]]})
    }
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code != 200:
            print(f"❌ Ошибка отправки поста: {res.text}")
    except Exception as e:
        print(f"Ошибка отправки поста в Telegram: {e}")

def send_telegram_poll(question, option1, option2):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "question": question,
        "options": json.dumps([option1, option2]),
        "is_anonymous": True
    }
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка отправки опроса в Telegram: {e}")

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
        print("✅ Пост и опрос успешно обработаны!")
    else:
        print("ℹ️ Свежих новостей пока нет.")
