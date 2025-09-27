#!/usr/bin/env python3
# coding: utf-8

"""
Love Memories Bot — финальная версия

Инструкции:
- Вставь токен в API_TOKEN.
- pip install aiogram==3.12 apscheduler
- python love_memories_bot.py
- Добавь бота в группу и напиши /start в группе.
"""

import asyncio
import json
import os
import random
from datetime import datetime, date
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ====== НАСТРОЙКИ ======
API_TOKEN = "7557684954:AAH7SrZmP5pzn6DsF2VvENtSrlpLboAAgBs"  # <- вставь сюда токен
DATA_FILE = "data.json"
DAILY_SEND_HOUR = 9  # час отправки ежедневного сообщения (0-23)

# ====== ДЕФОЛТНЫЕ ДАННЫЕ ======
DEFAULTS = {
    "start_date": "2020-09-21",
    "meeting_date": "2025-12-18",
    "group_id": None,
    "places": [],
    "photos": [],  # list of {"file_id":..., "caption":..., "date": "..."}
    "wishes": [],
}

# ====== ПЕРСИСТЕНЦИЯ ======
def load_data() -> Dict[str, Any]:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("Ошибка чтения data.json:", e)
    # копия, чтобы не править DEFAULTS напрямую
    return dict(DEFAULTS)

def save_data(d: Dict[str, Any]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# попытка корректно распарсить даты
try:
    START_DATE = datetime.fromisoformat(data.get("start_date", DEFAULTS["start_date"])).date()
except Exception:
    START_DATE = datetime.fromisoformat(DEFAULTS["start_date"]).date()
try:
    MEETING_DATE = datetime.fromisoformat(data.get("meeting_date", DEFAULTS["meeting_date"])).date()
except Exception:
    MEETING_DATE = datetime.fromisoformat(DEFAULTS["meeting_date"]).date()

# ====== БОТ И Диспетчер ======
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ====== ВРЕМЕННОЕ СОСТОЯНИЕ (ожидание ввода) ======
# pending_actions[chat_id] = {"action": "await_add_place" / "await_del_photo" / ...}
pending_actions: Dict[int, Dict[str, Any]] = {}

# ====== КЛАВИАТУРА ======
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📍 Добавить место"), KeyboardButton(text="🗂 Список мест")],
        [KeyboardButton(text="🎲 Случайное место"), KeyboardButton(text="🗑 Удалить место")],
        [KeyboardButton(text="📷 Добавить фото"), KeyboardButton(text="🖼 Воспоминания")],
        [KeyboardButton(text="🗑 Удалить фото"), KeyboardButton(text="📝 Экспорт архива")],
        [KeyboardButton(text="🌟 Добавить желание"), KeyboardButton(text="📜 Список желаний")],
        [KeyboardButton(text="🎲 Случайное желание"), KeyboardButton(text="🗑 Удалить желание")],
        [KeyboardButton(text="🕰 Лента"), KeyboardButton(text="🎁 Сюрприз")],
        [KeyboardButton(text="💖 Инфо")]
    ],
    resize_keyboard=True
)

# ====== ХЭЛПЕРЫ ======
def days_together() -> int:
    return (date.today() - START_DATE).days

def days_until_meeting() -> int:
    return (MEETING_DATE - date.today()).days

def format_places() -> str:
    places = data.get("places", [])
    if not places:
        return "📍 Список мест пуст 🕊"
    return "📍 Список мест:\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(places))

def format_wishes() -> str:
    wishes = data.get("wishes", [])
    if not wishes:
        return "🌟 Список желаний пуст ✨"
    return "🌟 Список желаний:\n" + "\n".join(f"{i+1}. {w}" for i, w in enumerate(wishes))

def format_photos_list() -> str:
    photos = data.get("photos", [])
    if not photos:
        return "📷 Фото-воспоминаний пока нет 🕊"
    return "📷 Фото-воспоминания:\n" + "\n".join(f"{i+1}. {p.get('caption','Без подписи')} ({p.get('date')})" for i, p in enumerate(photos))

# ====== ОБРАБОТЧИК /start ======
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    chat_id = message.chat.id
    # запоминаем group_id только если сообщение в группе или супергруппе
    data["group_id"] = chat_id
    # сохраняем строки дат (для экспорта и восстановления)
    data["start_date"] = START_DATE.isoformat()
    data["meeting_date"] = MEETING_DATE.isoformat()
    save_data(data)
    await message.answer("💌 Love Memories Bot активирован! Я готов хранить ваши воспоминания и присылать романтичные напоминания.", reply_markup=main_kb)

# ====== ОБРАБОТЧИК ФОТО (должен быть раньше общего текстового хэндлера) ======
@dp.message(lambda m: m.photo is not None)
async def photo_catcher(message: types.Message):
    chat_id = message.chat.id
    # если ожидали фото (через кнопку "Добавить фото"), то это па
    pa = pending_actions.pop(chat_id, None)
    caption = message.caption or "Без подписи"
    file_id = message.photo[-1].file_id
    record = {"file_id": file_id, "caption": caption, "date": date.today().isoformat()}
    data.setdefault("photos", []).append(record)
    save_data(data)
    # ответ и возврат клавиатуры
    await message.answer("📷 Фото добавлено в воспоминания!", reply_markup=main_kb)

# ====== ОБЩИЙ ТЕКСТОВЫЙ ОБРАБОТЧИК ======
@dp.message()
async def text_handler(message: types.Message):
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # если есть ожидающее действие — в приоритете
    if chat_id in pending_actions:
        action = pending_actions.pop(chat_id)
        act = action.get("action")
        # добавление места
        if act == "await_add_place":
            place = text
            data.setdefault("places", []).append(place)
            save_data(data)
            await message.answer(f"✨ Добавлено место: {place}", reply_markup=main_kb)
            return
        # удаление места по номеру
        if act == "await_del_place":
            try:
                idx = int(text) - 1
                if 0 <= idx < len(data.get("places", [])):
                    removed = data["places"].pop(idx)
                    save_data(data)
                    await message.answer(f"🗑 Удалено место: {removed}", reply_markup=main_kb)
                else:
                    await message.answer("Неверный номер места. Операция отменена.", reply_markup=main_kb)
            except Exception:
                await message.answer("Нужно ввести корректный номер. Операция отменена.", reply_markup=main_kb)
            return
        # добавление желания
        if act == "await_add_wish":
            wish = text
            data.setdefault("wishes", []).append(wish)
            save_data(data)
            await message.answer(f"🌟 Добавлено желание: {wish}", reply_markup=main_kb)
            return
        # удаление желания
        if act == "await_del_wish":
            try:
                idx = int(text) - 1
                if 0 <= idx < len(data.get("wishes", [])):
                    removed = data["wishes"].pop(idx)
                    save_data(data)
                    await message.answer(f"🗑 Удалено желание: {removed}", reply_markup=main_kb)
                else:
                    await message.answer("Неверный номер. Операция отменена.", reply_markup=main_kb)
            except Exception:
                await message.answer("Нужно ввести число. Операция отменена.", reply_markup=main_kb)
            return
        # удаление фото
        if act == "await_del_photo":
            try:
                idx = int(text) - 1
                if 0 <= idx < len(data.get("photos", [])):
                    removed = data["photos"].pop(idx)
                    save_data(data)
                    await message.answer(f"🗑 Удалено фото: {removed.get('caption')}", reply_markup=main_kb)
                else:
                    await message.answer("Неверный номер фото. Операция отменена.", reply_markup=main_kb)
            except Exception:
                await message.answer("Нужно ввести число. Операция отменена.", reply_markup=main_kb)
            return

    # обработка нажатий кнопок / обычный текст
    if text == "📍 Добавить место":
        pending_actions[chat_id] = {"action": "await_add_place"}
        await message.answer("Напиши название места (например: Кафе на набережной):", reply_markup=types.ReplyKeyboardRemove())
        return

    if text == "🗂 Список мест":
        await message.answer(format_places(), reply_markup=main_kb)
        return

    if text == "🎲 Случайное место":
        if data.get("places"):
            await message.answer(f"🎲 {random.choice(data['places'])}", reply_markup=main_kb)
        else:
            await message.answer("Список мест пуст. Добавьте место первым.", reply_markup=main_kb)
        return

    if text == "🗑 Удалить место":
        if not data.get("places"):
            await message.answer("Список мест пуст 🕊", reply_markup=main_kb)
        else:
            await message.answer(format_places() + "\n\nНапиши номер места, чтобы удалить:", reply_markup=types.ReplyKeyboardRemove())
            pending_actions[chat_id] = {"action": "await_del_place"}
        return

    if text == "📷 Добавить фото":
        pending_actions[chat_id] = {"action": "await_add_photo"}
        await message.answer("Пришли фото (как обычное сообщение) и подпись — я сохраню его.", reply_markup=types.ReplyKeyboardRemove())
        return

    if text == "🖼 Воспоминания":
        photos = data.get("photos", [])
        if not photos:
            await message.answer("Воспоминаний с фото пока нет 🕊", reply_markup=main_kb)
        else:
            # отправим сначала подписи и фото
            for p in photos:
                try:
                    await message.answer_photo(p["file_id"], caption=p.get("caption", "Без подписи"))
                except Exception:
                    await message.answer(f"Фото: {p.get('caption','Без подписи')}")
            await message.answer("Вот все ваши фото-воспоминания.", reply_markup=main_kb)
        return

    if text == "🗑 Удалить фото":
        if not data.get("photos"):
            await message.answer("Фото-воспоминаний пока нет.", reply_markup=main_kb)
        else:
            await message.answer(format_photos_list() + "\n\nНапиши номер фото, чтобы удалить:", reply_markup=types.ReplyKeyboardRemove())
            pending_actions[chat_id] = {"action": "await_del_photo"}
        return

    if text == "📝 Экспорт архива":
        # формируем текст архива
        parts = []
        parts.append("--- Love Memories Archive ---")
        parts.append(f"Start date: {data.get('start_date', START_DATE.isoformat())}")
        parts.append(f"Meeting date: {data.get('meeting_date', MEETING_DATE.isoformat())}")
        parts.append("")
        parts.append(format_places())
        parts.append("")
        parts.append(format_wishes())
        parts.append("")
        parts.append(format_photos_list())
        txt = "\n\n".join(parts)
        fname = f"love_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(txt)
        try:
            await message.answer_document(types.InputFile(fname))
        except Exception as e:
            await message.answer("Ошибка отправки архива: " + str(e))
        finally:
            try:
                os.remove(fname)
            except Exception:
                pass
        return

    if text == "🌟 Добавить желание":
        pending_actions[chat_id] = {"action": "await_add_wish"}
        await message.answer("Напиши желание (коротко):", reply_markup=types.ReplyKeyboardRemove())
        return

    if text == "📜 Список желаний":
        await message.answer(format_wishes(), reply_markup=main_kb)
        return

    if text == "🎲 Случайное желание":
        if data.get("wishes"):
            await message.answer(f"🎲 {random.choice(data['wishes'])}", reply_markup=main_kb)
        else:
            await message.answer("Список желаний пуст ✨", reply_markup=main_kb)
        return

    if text == "🗑 Удалить желание":
        if not data.get("wishes"):
            await message.answer("Список желаний пуст ✨", reply_markup=main_kb)
        else:
            await message.answer(format_wishes() + "\n\nНапиши номер желания, чтобы удалить:", reply_markup=types.ReplyKeyboardRemove())
            pending_actions[chat_id] = {"action": "await_del_wish"}
        return

    if text == "🕰 Лента":
        choices = []
        if data.get("places"):
            choices.append(("place", random.choice(data["places"])))
        if data.get("photos"):
            choices.append(("photo", random.choice(data["photos"])))
        if data.get("wishes"):
            choices.append(("wish", random.choice(data["wishes"])))
        if not choices:
            await message.answer("Пока нет воспоминаний для ленты 🕊", reply_markup=main_kb)
        else:
            typ, val = random.choice(choices)
            if typ == "place":
                await message.answer(f"🕰 Вспоминаем место: {val}", reply_markup=main_kb)
            elif typ == "photo":
                try:
                    await message.answer_photo(val["file_id"], caption=f"🕰 Вспоминаем: {val.get('caption','Без подписи')}", reply_markup=main_kb)
                except Exception:
                    await message.answer(f"🕰 Вспоминаем: {val.get('caption','Без подписи')}", reply_markup=main_kb)
            else:
                await message.answer(f"🕰 Вспоминаем желание: {val}", reply_markup=main_kb)
        return

    if text == "🎁 Сюрприз":
        surprises = [
            "Напиши ей 3 причины, почему она тебе нравится 💬",
            "Отправь ей голосовое сообщение с комплиментом 🎙",
            "Запланируй короткую прогулку — 30 минут вместе 🌇",
            "Сделай ей комплимент прямо сейчас — пусть начнётся день с улыбки 😊",
            "Пришли фото, на котором вы оба счастливы 📸"
        ]
        await message.answer(random.choice(surprises), reply_markup=main_kb)
        return

    if text == "💖 Инфо":
        together = days_together()
        until = days_until_meeting()
        info_text = (
            f"💞 Вы вместе уже {together} дней!\n"
            f"⏳ До встречи осталось {until} дней.\n\n"
            "✨ Возможности бота:\n"
            "📍 Добавлять/удалять/просматривать места\n"
            "📷 Добавлять/удалять/просматривать фото-воспоминания\n"
            "🌟 Добавлять/удалять/просматривать желания\n"
            "🕰 Лента случайных воспоминаний\n"
            "🎁 Сюрприз (романтические задания)\n"
            "📝 Экспорт архива (.txt)\n"
            "💖 Ежедневные и праздничные сообщения"
        )
        await message.answer(info_text, reply_markup=main_kb)
        return

    # если не распознано — показываем клавиатуру
    await message.answer("Не понял. Используй кнопки внизу для управления ботом.", reply_markup=main_kb)


# ====== ЕЖЕДНЕВНЫЕ И ОСОБЫЕ СООБЩЕНИЯ ======
async def send_daily_and_special():
    group_id = data.get("group_id")
    if not group_id:
        return
    together = days_together()
    until = days_until_meeting()
    quotes = [
        "Я скучаю по тебе 💕",
        "Ты моё счастье 🌸",
        "Люблю тебя бесконечно 🤍",
        "Каждый день с тобой — подарок 🎁",
        "Ты мой самый важный человек 💫"
    ]
    today = date.today()
    special = None
    # годовщина (по дню и месяцу)
    if today.month == START_DATE.month and today.day == START_DATE.day:
        years = today.year - START_DATE.year
        special = f"🎉 Сегодня ваша годовщина — {years} {'год' if years==1 else 'лет'} вместе!"
    # встреча
    if today == MEETING_DATE:
        special = "💫 Сегодня ваша встреча! Наслаждайтесь моментом 💖"

    base = f"💖 Сегодня вы вместе уже {together} дней!\n⏳ До встречи осталось {until} дней.\n"
    if special:
        base += f"\n{special}\n"
    base += f"\n{random.choice(quotes)}"
    try:
        await bot.send_message(group_id, base)
    except Exception as e:
        print("Ошибка отправки ежедневного сообщения:", e)

def schedule_daily():
    # удаляем предыдущие задания и добавляем новое cron-задание
    try:
        scheduler.remove_all_jobs()
    except Exception:
        pass
    # отправка в hour:00 каждый день
    scheduler.add_job(lambda: asyncio.create_task(send_daily_and_special()), 'cron', hour=DAILY_SEND_HOUR, minute=0)
    scheduler.start()

# ====== ЗАПУСК ======
async def main():
    print("Love Memories Bot запускается...")
    data.setdefault("start_date", START_DATE.isoformat())
    data.setdefault("meeting_date", MEETING_DATE.isoformat())
    save_data(data)
    schedule_daily()

    if os.getenv("PORT"):  # Railway окружение
        from aiohttp import web

        async def handle(request):
            update = await request.json()
            await dp.feed_webhook_update(bot, update)
            return web.Response()

        app = web.Application()
        app.router.add_post(f"/{API_TOKEN}", handle)

        # устанавливаем webhook
        public_url = os.getenv("RAILWAY_STATIC_URL")
        webhook_url = f"{public_url}/{API_TOKEN}"

        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(webhook_url)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
        await site.start()

        print(f"Webhook запущен на {webhook_url}")
        while True:  # держим приложение живым
            await asyncio.sleep(3600)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Остановлен")



