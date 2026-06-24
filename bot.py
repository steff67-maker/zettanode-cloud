import io, os, asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google import genai
from google.genai import types as genai_types
from PIL import Image

# 🛡️ Переменные окружения со скрытыми ключами
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")


bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = genai.Client()

# user_chats будет хранить объекты сессий чата от самого Google SDK
user_languages, user_chats, last_ai_response = {}, {}, {}

TEXTS = {
    'ru': {
        'welcome': "✨ Система ZettaNode запущена на бесплатном облаке!\n\nЗадай мне любой вопрос, пришли фото или .txt файл — я во всем разберусь!",
        'error': "Произошла ошибка, попробуй еще раз.",
        'clear_mem': "🧹 Память ZettaNode успешно очищена!",
        'simplify_btn': "👶 Упростить ответ",
        'clear_btn': "🧹 Стереть память",
        'simplified_title': "<b>Простыми словами:</b>\n\n",
        'system': "Ты — ZettaNode, продвинутый искусственный интеллект. Отвечай глубоко и экспертно на русском языке."
    },
    'en': {
        'welcome': "✨ ZettaNode system online on a free cloud server!\n\nAsk me anything, send an image or a .txt file!",
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

def get_or_create_chat(uid, lang):
    """Инициализирует или возвращает официальную сессию чата Gemini"""
    if uid not in user_chats or user_chats[uid] is None:
        user_chats[uid] = ai_client.chats.create(
            model="gemini-1.5-flash",
            config=genai_types.GenerateContentConfig(system_instruction=TEXTS[lang]['system'])
        )
    return user_chats[uid]

@dp.message(CommandStart())
async def start_cmd(m: types.Message):
    await m.answer("Choose language / Выберите язык:", reply_markup=get_lang_keyboard())

@dp.callback_query(F.data.startswith('set_lang_'))
async def process_language(c: types.CallbackQuery):
    l = c.data.split('_')[-1] 
    user_languages[c.from_user.id] = l
    # Сбрасываем старый чат при смене языка, чтобы создался новый с верным системным промптом
    user_chats[c.from_user.id] = None 
    
    await c.answer()
    await bot.send_message(c.from_user.id, TEXTS[l]['welcome'])

@dp.callback_query(F.data.startswith('action_'))
async def process_actions(c: types.CallbackQuery):
    uid = c.from_user.id
    act = c.data.split('_')[-1] 
    l = user_languages.get(uid, 'ru')
    
    await c.answer()
    
    if act == "clear":
        user_chats[uid], last_ai_response[uid] = None, ""
        await bot.send_message(uid, TEXTS[l]['clear_mem'])
    elif act == "simplify":
        txt = last_ai_response.get(uid, "")
        if not txt: 
            return
        await bot.send_chat_action(chat_id=uid, action="typing")
        try:
            r = ai_client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=f"Упрости этот текст для ребенка:\n\n{txt}",
                config=genai_types.GenerateContentConfig(system_instruction=TEXTS[l]['system'])
            )
            await bot.send_message(uid, f"{TEXTS[l]['simplified_title']}{r.text}", parse_mode="HTML")
        except:
            await bot.send_message(uid, TEXTS[l]['error'])

@dp.message()
async def handle_everything(m: types.Message):
    uid = m.from_user.id
    l = user_languages.get(uid, 'ru')
    
    await bot.send_chat_action(chat_id=m.chat.id, action="typing")

    contents = []
    prompt = m.caption if m.caption else m.text
    
    if m.photo:
        p = m.photo[-1]
        fi = await bot.get_file(p.file_id)
        fb = await bot.download_file(fi.file_path)
        contents.append(Image.open(io.BytesIO(fb.read())))
        if not prompt: 
            prompt = "Describe this image." if l == 'en' else "Что на фото?"
    elif m.document and m.document.mime_type == "text/plain":
        fi = await bot.get_file(m.document.file_id)
        fb = await bot.download_file(fi.file_path)
        prompt = f"{prompt if prompt else ''}\n\n[File]:\n{fb.read().decode('utf-8', errors='ignore')}"
        
    if not prompt: 
        return
        
    contents.append(prompt)
    
    try:
        # Получаем сессию чата для пользователя и отправляем сообщение
        chat = get_or_create_chat(uid, l)
        
        # Передаем массив данных (текст + опционально картинка) через официальный метод send_message
        r = chat.send_message(contents)
        
        last_ai_response[uid] = r.text
        await m.answer(r.text, parse_mode="Markdown", reply_markup=get_action_keyboard(l))
    except Exception as e:
        print(f"Ошибка Gemini API: {e}") # Выведет точную техническую ошибку в логи Render
        await m.answer(TEXTS[l]['error'])

async def main():
    print("Запуск мини веб-сервера для Render...")
    from aiohttp import web
    app = web.Application()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("ZettaNode готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
