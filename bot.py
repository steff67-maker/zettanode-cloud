import io, os, asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from groq import Groq
from PIL import Image

# 🛡️ Берём токены из настроек сервера
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = Groq(api_key=GROQ_API_KEY)

# Используем модель Llama 3.3 70B (она бесплатная, мощная и очень быстрая)
MODEL_NAME = "llama-3.3-70b-versatile"

user_languages, user_history, last_ai_response = {}, {}, {}

TEXTS = {
    'ru': {
        'welcome': "✨ Система ZettaNode запущена на бесплатном облаке через Groq API!\n\nЗадай мне любой вопрос, пришли фото или .txt файл — я во всем разберусь!",
        'error': "Произошла ошибка, попробуй еще раз.",
        'clear_mem': "🧹 Память ZettaNode успешно очищена!",
        'simplify_btn': "👶 Упростить ответ",
        'clear_btn': "🧹 Стереть память",
        'simplified_title': "<b>Простыми словами:</b>\n\n",
        'system': "Ты — ZettaNode, продвинутый искусственный интеллект. Отвечай глубоко, экспертно и только на русском языке."
    },
    'en': {
        'welcome': "✨ ZettaNode system online on a free cloud server via Groq API!\n\nAsk me anything, send an image or a .txt file!",
        'error': "An error occurred, please try again.",
        'clear_mem': "🧹 ZettaNode memory cleared successfully!",
        'simplify_btn': "👶 Simplify answer",
        'clear_btn': "🧹 Clear memory",
        'simplified_title': "<b>In simple terms:</b>\n\n",
        'system': "You are ZettaNode, an advanced artificial intelligence. Provide deep and expert responses in English."
    }
}

def get_lang_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    b.button(text="🇬🇧 English", callback_data="set_lang_en")
    return b.as_markup()

def get_action_keyboard(l):
    b = InlineKeyboardBuilder()
    b.button(text=TEXTS[l]['simplify_btn'], callback_data="action_simplify")
    b.button(text=TEXTS[l]['clear_btn'], callback_data="action_clear")
    return b.as_markup()

@dp.message(CommandStart())
async def start_cmd(m: types.Message):
    await m.answer("Choose language / Выберите язык:", reply_markup=get_lang_keyboard())

@dp.callback_query(F.data.startswith('set_lang_'))
async def process_language(c: types.CallbackQuery):
    l = c.data.split('_')[-1] 
    user_languages[c.from_user.id] = l
    user_history[c.from_user.id] = []
    
    await c.answer()
    await bot.send_message(c.from_user.id, TEXTS[l]['welcome'])

@dp.callback_query(F.data.startswith('action_'))
async def process_actions(c: types.CallbackQuery):
    uid = c.from_user.id
    act = c.data.split('_')[-1] 
    l = user_languages.get(uid, 'ru')
    
    await c.answer()
    
    if act == "clear":
        user_history[uid], last_ai_response[uid] = [], ""
        await bot.send_message(uid, TEXTS[l]['clear_mem'])
    elif act == "simplify":
        txt = last_ai_response.get(uid, "")
        if not txt: 
            return
        await bot.send_chat_action(chat_id=uid, action="typing")
        try:
            r = ai_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": TEXTS[l]['system']},
                    {"role": "user", "content": f"Упрости этот текст для ребенка:\n\n{txt}"}
                ]
            )
            await bot.send_message(uid, f"{TEXTS[l]['simplified_title']}{r.choices[0].message.content}", parse_mode="HTML")
        except:
            await bot.send_message(uid, TEXTS[l]['error'])

import base64  # Добавьте этот импорт в самый верх файла, если его там нет

@dp.message()
async def handle_everything(m: types.Message):
    uid = m.from_user.id
    l = user_languages.get(uid, 'ru')
    
    if uid not in user_history: 
        user_history[uid] = []
        
    await bot.send_chat_action(chat_id=m.chat.id, action="typing")

    prompt = m.caption if m.caption else m.text
    photo_base64 = None
    current_model = MODEL_NAME

    # 1. Текстовые файлы
    if m.document and m.document.mime_type == "text/plain":
        fi = await bot.get_file(m.document.file_id)
        fb = await bot.download_file(fi.file_path)
        prompt = f"{prompt if prompt else ''}\n\n[File]:\n{fb.read().decode('utf-8', errors='ignore')}"
        
   # 2. Изображения (используем бесплатный Gemini для зрения)
    elif m.photo:
        try:
            import requests
            photo = m.photo[-1]
            fi = await bot.get_file(photo.file_id)
            fb = await bot.download_file(fi.file_path)
            
            # Обязательно переводим картинку в Base64, иначе Google её не увидит
            photo_base64 = base64.b64encode(fb.read()).decode('utf-8')
            
            gemini_key = os.getenv("GEMINI_API_KEY")
            url = f"h t t p s : / / g e n e r a t i v e l a n g u a g e . g o o g l e a p i s . c o m / v 1 b e t a / m o d e l s / g e m i n i - 1 . 5 - f l a s h : g e n e r a t e C o n t e n t ? k e y ={gemini_key}"
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": f"Ты ИИ ZettaNode. Отвечай глубоко и строго на русском языке. Запрос: {prompt if prompt else 'Что на фото? Опиши подробно.'}"},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": photo_base64
                            }
                        }
                    ]
                }]
            }
            
            res = requests.post(url, json=payload, timeout=30).json()
            response_text = res['candidates'][0]['content']['parts'][0]['text']
            
            await m.answer(response_text, parse_mode="Markdown", reply_markup=get_action_keyboard(l))
            return
            
        except Exception as e:
            print(f"Ошибка Gemini API: {e}")
            await m.answer(f"{TEXTS[l]['error']} (Ошибка зрения: {str(e)[:70]})")
            return
    # 3. Формированиеmessages строго по гайду Groq Vision
    if photo_base64:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": f"Ты ИИ ZettaNode. Отвечай только на русском языке. Вопрос по картинке: {prompt}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{photo_base64}"
                        }
                    }
                ]
            }
        ]
    else:
        user_history[uid].append({"role": "user", "content": prompt})
        if len(user_history[uid]) > 10:
            user_history[uid] = user_history[uid][-10:]
        messages = [{"role": "system", "content": TEXTS[l]['system']}] + user_history[uid]
    
    try:
        r = ai_client.chat.completions.create(
            model=current_model,
            messages=messages
        )
        
        response_text = r.choices.message.content
        last_ai_response[uid] = response_text
        
        if not photo_base64:
            user_history[uid].append({"role": "assistant", "content": response_text})
            
        await m.answer(response_text, parse_mode="Markdown", reply_markup=get_action_keyboard(l))
    except Exception as e:
        print(f"Ошибка Groq API: {e}")
        # ВАЖНО: выводим ПОЛНУЮ ошибку без обрезания, чтобы увидеть причину
        await m.answer(f"{TEXTS[l]['error']}\n\nПолный лог ошибки:\n{str(e)}")

async def main():
    print("Запуск мини веб-сервера для Render...")
    from aiohttp import web
    
    app = web.Application()
    
    # Добавляем ответ на проверку от Render
    async def handle_ping(request):
        return web.Response(text="OK", status=200)
    app.router.add_get('/', handle_ping)
    
    # Берем порт, который требует Render
    port = int(os.getenv("PORT", 10000))
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Запускаем на динамическом порту
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"ZettaNode веб-сервер запущен на порту {port}!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
