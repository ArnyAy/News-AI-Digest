def generate_ai_post(news_item):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    Ты — главный редактор популярного IT-медиа "News AI Digest".
    Преобразуй новость в сочный, структурированный и захватывающий пост на русском языке.

    Заголовок новости: {news_item['title']}
    Текст новости: {news_item['summary']}

    СТРОГИЕ ПРАВИЛА:
    1. Названия брендов, компаний и нейросетей ОСТАВЛЯЙ НА АНГЛИЙСКОМ (Claude, OpenAI, Anthropic, ChatGPT, Midjourney, Google и т.д.). Никакого транслита (НЕ ПИШИ "Клауд" или "Антропик").
    2. Используй HTML-разметку для Telegram (<b>жирный</b>, <i>курсив</i>). Не используй символы **.
    3. Структура поста:
       - <b>Яркий заголовок с 1-2 эмодзи</b>
       - Главный инфоповод (1-2 коротких предложения)
       - <b>Key Takeaways / Что это значит:</b> (3 быстрых буллета через эмодзи)
       - Завершающий вовлекающий вопрос к аудитории.
       - 3-4 актуальных хэштега.

    Выдавай ТОЛЬКО готовый текст поста, без вводных фраз.
    """

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Ошибка AI: {e}")
    
    return f"🚀 <b>{news_item['title']}</b>\n\n{news_item['summary'][:300]}..."

def send_telegram_post(text, image_url, source_link):
    """Отправка поста с интерактивной кнопкой-ссылкой на первоисточник"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    # Добавляем Inline-кнопку под карточкой
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "🔗 Читать первоисточник", "url": source_link}
            ]
        ]
    }
    
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": image_url,
        "caption": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
    }
    requests.post(url, json=payload, timeout=15)
