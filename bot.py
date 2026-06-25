import io, os, asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from groq import Groq

# 🛡️ Берём токены из настроек сервера
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
ai_client = Groq(api_key=GROQ_API_KEY)

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
        if not txt: return
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

@dp.message()
async def handle_everything(m: types.Message):
    uid = m.from_user.id
    l = user_languages.get(uid, 'ru')
    
    if uid not in user_history: 
        user_history[uid] = []
        
    await bot.send_chat_action(chat_id=m.chat.id, action="typing")
    prompt = m.caption if m.caption else m.text
    
    if m.document and m.document.mime_type == "text/plain":
        fi = await bot.get_file(m.document.file_id)
        fb = await bot.download_file(fi.file_path)
        prompt = f"{prompt if prompt else ''}\n\n[File]:\n{fb.read().decode('utf-8', errors='ignore')}"
    elif m.photo:
        if not prompt: prompt = "Что на фото?" if l == 'ru' else "Describe the image."
        
    if not prompt: 
        return

    user_history[uid].append({"role": "user", "content": prompt})
    messages = [{"role": "system", "content": TEXTS[l]['system']}] + user_history[uid]
    
    try:
        r = ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages
        )
        
        response_text = r.choices[0].message.content
        last_ai_response[uid] = response_text
        user_history[uid].append({"role": "assistant", "content": response_text})
        
        if len(user_history[uid]) > 10: 
            user_history[uid] = user_history[uid][-10:]
            
        await m.answer(response_text, parse_mode="Markdown", reply_markup=get_action_keyboard(l))
    except Exception as e:
        print(f"Ошибка Groq API: {e}")
        await m.answer(TEXTS[l]['error'])

async def main():
    print("Запуск мини веб-сервера для Render...")
    from aiohttp import web
    app = web.Application()
    
    async def handle_ping(request):
        return web.Response(text="OK", status=200)
    app.router.add_get('/', handle_ping)
    
    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"ZettaNode готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
