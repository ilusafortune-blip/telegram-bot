import asyncio
import aiohttp
from datetime import datetime, timedelta
import logging
import sys
import os
import threading
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
# ==================== ПОДСЧЁТ ПОЛЬЗОВАТЕЛЕЙ ====================
import sqlite3
from datetime import date
from flask import Flask

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=date_format,
    handlers=[
        logging.FileHandler("bot_logs.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("NeverTimeBot")

# ==================== ТОКЕН БОТА ====================
# Берем токен из переменных окружения (для безопасности)
BOT_TOKEN = os.environ.get('BOT_TOKEN', "8618907106:AAHdsoH8lSkGS3f6g3Dp4giXoYVLfPAYdCE")

# ==================== СОЗДАНИЕ БОТА ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== НАСТРОЙКИ СЕРВЕРА ====================
CHAT_ID = os.environ.get('CHAT_ID', "ID_ЧАТА_ИЛИ_КАНАЛА")
SERVER_IP = "mc.nevertime.su"
SERVER_PORT = "19132"
SERVER_VERSION = "1.21.40+"
SERVER_DESCRIPTION = "Bedrock сервер с мини-играми и ивентами"
EVENT_INTERVAL = 35

# ==================== НАСТРОЙКИ ИВЕНТОВ ====================
FIRST_EVENT_TIME = "09:15:00"

# ==================== ЧАСОВОЙ ПОЯС ====================
try:
    MSK_TZ = ZoneInfo("Europe/Moscow")
    logger.info(f"✅ Часовой пояс загружен: Europe/Moscow")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки часового пояса: {e}")
    from datetime import timezone, timedelta
    MSK_TZ = timezone(timedelta(hours=3), name="MSK")
    logger.info(f"⚠️ Используется запасной вариант: UTC+3")

# ==================== ФУНКЦИИ ДЛЯ ПОДСЧЁТА ПОЛЬЗОВАТЕЛЕЙ ====================
def get_db_path():
    """Возвращает правильный путь для базы данных"""
    try:
        # Для Render.com используем /data, для локальной разработки текущую папку
        if os.path.exists('/data'):
            return '/data/users.db'
        else:
            return 'users.db'
    except:
        return 'users.db'

def init_users_db():
    """Инициализация базы данных пользователей"""
    try:
        db_path = get_db_path()
        print(f"📁 База данных будет в: {db_path}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_date TEXT
            )
        ''')
        conn.commit()
        conn.close()
        print(f"✅ База данных готова: {db_path}")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")

def add_user(user_id, username, first_name):
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today_str = date.today().isoformat()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            print(f"👤 Пользователь {user_id} уже есть")
        else:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, joined_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, today_str))
            conn.commit()
            print(f"✅ Новый пользователь! ID: {user_id}")
            
            cursor.execute('SELECT COUNT(*) FROM users')
            total = cursor.fetchone()[0]
            print(f"📊 Всего: {total}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def get_user_count():
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"❌ Ошибка счёта: {e}")
        return 0

def format_users_count(count):
    return f"{count:,}".replace(",", " ")

# ==================== ЛОГИРОВАНИЕ ПОЛЬЗОВАТЕЛЕЙ ====================
async def log_user_info(message: types.Message, command: str = None):
    user = message.from_user
    user_info = f"👤 Пользователь: {user.full_name} (ID: {user.id}, Username: @{user.username if user.username else 'нет'})"
    chat = message.chat
    chat_info = f"Чат: {chat.title if chat.title else 'личка'} (ID: {chat.id})"
    
    if command:
        logger.info(f"📨 Команда /{command} | {user_info} | {chat_info}")
    else:
        logger.info(f"💬 Сообщение | {user_info} | {chat_info}")
    
    add_user(user.id, user.username, user.first_name)

# ==================== ФУНКЦИИ ИВЕНТОВ ====================
def get_first_event_today():
    now_msk = datetime.now(MSK_TZ)
    hour, minute, second = map(int, FIRST_EVENT_TIME.split(':'))
    
    first_event = now_msk.replace(
        hour=hour, 
        minute=minute, 
        second=second, 
        microsecond=0
    )
    
    if first_event > now_msk:
        first_event = first_event - timedelta(days=1)
    
    return first_event

def get_next_event_time():
    now_msk = datetime.now(MSK_TZ)
    first_event = get_first_event_today()
    
    time_since_first = now_msk - first_event
    intervals_passed = time_since_first.total_seconds() // (EVENT_INTERVAL * 60)
    
    next_event = first_event + timedelta(minutes=EVENT_INTERVAL * (intervals_passed + 1))
    return next_event

def get_event_number():
    now_msk = datetime.now(MSK_TZ)
    first_event = get_first_event_today()
    time_since_first = now_msk - first_event
    intervals_passed = time_since_first.total_seconds() // (EVENT_INTERVAL * 60)
    return int(intervals_passed) + 1

def format_time_remaining():
    next_event = get_next_event_time()
    now_msk = datetime.now(MSK_TZ)
    
    time_left = next_event - now_msk
    total_seconds = int(time_left.total_seconds())
    
    if total_seconds < 0:
        next_event = get_next_event_time()
        time_left = next_event - now_msk
        total_seconds = int(time_left.total_seconds())
    
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    
    if minutes > 0:
        time_str = f"**{minutes}** мин **{seconds}** сек"
    else:
        time_str = f"**{seconds}** сек"
    
    return {
        "next_event": next_event,
        "time_str": time_str,
        "event_number": get_event_number(),
        "total_seconds": total_seconds
    }

# ==================== ФУНКЦИЯ ПОЛУЧЕНИЯ ОНЛАЙНА ====================
async def get_server_online():
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.mcsrvstat.us/bedrock/3/{SERVER_IP}"
            logger.info(f"📡 Запрос к API: {url}")
            
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data and data.get("online"):
                        players = data.get("players", {})
                        online = players.get("online", 0)
                        max_players = players.get("max", 6666)
                        
                        logger.info(f"✅ Получен реальный онлайн: {online}/{max_players}")
                        return online, max_players
                    else:
                        logger.warning(f"⚠️ Сервер офлайн или не отвечает")
                        return None, None
                else:
                    logger.error(f"❌ API вернул статус {response.status}")
                    return None, None
    except asyncio.TimeoutError:
        logger.error("⏱ Таймаут при запросе к API")
        return None, None
    except Exception as e:
        logger.error(f"❌ Ошибка получения онлайна: {e}")
        return None, None

# ==================== УВЕДОМЛЕНИЯ О СТАТУСЕ СЕРВЕРА ====================
last_server_status = None

async def check_server_status():
    global last_server_status
    
    logger.info("🔄 Запущена проверка статуса сервера")
    
    while True:
        try:
            online, max_players = await get_server_online()
            current_status = online is not None
            
            if last_server_status is not None and current_status != last_server_status:
                current_time = datetime.now(MSK_TZ).strftime('%H:%M:%S')
                
                if current_status:
                    await bot.send_message(
                        CHAT_ID,
                        f"🟢 **СЕРВЕР ЗАПУЩЕН!**\n\n"
                        f"🌍 **Сервер:** `{SERVER_IP}:{SERVER_PORT}`\n"
                        f"👥 **Сейчас играют:** {online}/{max_players}\n"
                        f"⏱ **Время:** {current_time} МСК\n\n"
                        f"🎮 **Заходите играть!**",
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Уведомление: сервер запущен, онлайн {online}")
                else:
                    await bot.send_message(
                        CHAT_ID,
                        f"🔴 **СЕРВЕР НЕ ДОСТУПЕН**\n\n"
                        f"🌍 **Сервер:** `{SERVER_IP}:{SERVER_PORT}`\n"
                        f"⏱ **Время:** {current_time} МСК\n\n"
                        f"⚠️ Возможно, ведутся техработы.\n"
                        f"Следите за новостями в канале: https://t.me/nevertime",
                        parse_mode="Markdown"
                    )
                    logger.info("✅ Уведомление: сервер выключен")
            
            last_server_status = current_status
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в проверке статуса сервера: {e}")
            await asyncio.sleep(60)

# ==================== УВЕДОМЛЕНИЯ ОБ ИВЕНТАХ ====================
async def check_event_notifications():
    logger.info("🔄 Запущена проверка уведомлений об ивентах")
    
    while True:
        try:
            data = format_time_remaining()
            time_until_event = data['total_seconds']
            
            if 0 < time_until_event <= 5:
                logger.info(f"🎯 Близится ивент #{data['event_number']} в {data['next_event'].strftime('%H:%M:%S')}")
                
                await bot.send_message(
                    CHAT_ID,
                    f"🎉 **ИВЕНТ НАЧИНАЕТСЯ!** 🎉\n\n"
                    f"❓ **Редкость:** неизвестно\n"
                    f"📜 **Описание:** Ивент\n"
                    f"🕒 **Время:** {data['next_event'].strftime('%H:%M:%S')} МСК\n"
                    f"⏱ **Длительность:** {EVENT_INTERVAL} минут\n"
                    f"🔢 **Ивент #:** {data['event_number']}\n\n"
                    f"🌍 **Сервер:** `{SERVER_IP}:{SERVER_PORT}`\n"
                    f"🏃‍♂️ **Заходите участвовать!**",
                    parse_mode="Markdown"
                )
                
                logger.info(f"✅ Отправлено уведомление об ивенте #{data['event_number']}")
                await asyncio.sleep(10)
                continue
            
            if time_until_event < 10:
                await asyncio.sleep(0.5)
            elif time_until_event < 30:
                await asyncio.sleep(1)
            elif time_until_event < 60:
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в проверке ивентов: {e}")
            await asyncio.sleep(10)

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await log_user_info(message, "start")
    
    user = message.from_user
    add_user(user.id, user.username, user.first_name)
    
    total_users = get_user_count()
    formatted_total = format_users_count(total_users)
    
    text = (
        "👋 Приветствую! Это бот **NeverTime** 🖤\n"
        f"📊 **{formatted_total} пользователей** используют этого бота\n\n"
        "Что умеет этот бот?\n\n"
        
        "**Команды:**\n"
        "/event — показывает время до ближайшего ивента\n"
        "/online — показывает реальный онлайн на сервере\n"
        "/info — информация о сервере\n"
        "/when — показывает час пик сервера, когда лучше всего зайти\n"
        "/stats — статистика бота (сколько пользователей)\n"
        "/ask — задать вопрос о Minecraft или NeverTime\n"
        "/question — задать вопрос администратору\n\n"
        
        "**Дополнительно:**\n"
        "🔔 Бот присылает уведомления, если сервер выключился или начались техработы.\n"
        "📊 Также каждый день публикуется статистика онлайна — сколько игроков было в пике.\n\n"
        
        "😊 Если вы нашли баг или хотите предложить идею — пишите в поддержку: @Havanu"
    )
    
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"✅ Ответ на /start отправлен пользователю {message.from_user.id}")

@dp.message(Command("event"))
async def cmd_event(message: types.Message):
    await log_user_info(message, "event")
    
    try:
        data = format_time_remaining()
        
        text = (
            f"🎮 **Данные ивента**\n\n"
            f"❓ **Редкость:** неизвестно\n"
            f"⏳ **До ивента:** `{data['time_str']}`\n"
            f"🕒 **Начало:** {data['next_event'].strftime('%H:%M:%S')} МСК\n"
            f"🔢 **Ивент #:** {data['event_number']}\n\n"
            f"📜 **Описание:** Ивент\n"
            f"🌍 **Сервер:** `{SERVER_IP}:{SERVER_PORT}`\n\n"
            f"✨ _Заходи, будет весело!_"
        )
        
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"✅ Ответ на /event отправлен пользователю {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /event для пользователя {message.from_user.id}: {e}")
        await message.answer("⚠️ Ошибка при получении данных об ивенте")

@dp.message(Command("online"))
async def cmd_online(message: types.Message):
    await log_user_info(message, "online")
    await bot.send_chat_action(message.chat.id, action="typing")
    
    try:
        online, max_players = await get_server_online()
        current_time = datetime.now(MSK_TZ).strftime('%H:%M:%S')
        
        if online is not None:
            load_percent = int((online / max_players) * 100) if max_players > 0 else 0
            
            if load_percent >= 80:
                status_emoji = "🔴"
                load_text = "Очень высокая"
            elif load_percent >= 50:
                status_emoji = "🟡"
                load_text = "Средняя"
            else:
                status_emoji = "🟢"
                load_text = "Низкая"
            
            bar_length = 10
            filled = int((online / max_players) * bar_length) if max_players > 0 else 0
            bar = "█" * filled + "░" * (bar_length - filled)
            
            text = (
                f"🟢 **РЕАЛЬНЫЙ ОНЛАЙН**\n\n"
                f"🌍 **Сервер:** `{SERVER_IP}:{SERVER_PORT}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 **Сейчас играют:** `{online}` из `{max_players}`\n"
                f"📊 **Загрузка:** {status_emoji} {load_text} ({load_percent}%)\n"
                f"`{bar}`\n\n"
                f"⏱ **Обновлено:** {current_time} МСК"
            )
        else:
            text = f"🔴 **Bedrock сервер не отвечает**\n\n⏱ **Обновлено:** {current_time} МСК"
        
        await message.answer(text, parse_mode="Markdown")
        logger.info(f"✅ Ответ на /online отправлен пользователю {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в /online: {e}")
        await message.answer("⚠️ Ошибка при получении данных")
        
@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    """Команда /info - информация о сервере"""
    await log_user_info(message, "info")
    
    text = (
        f"🖥 **ИНФОРМАЦИЯ О СЕРВЕРЕ**\n\n"
        f"🌍 **IP:** `{SERVER_IP}:{SERVER_PORT}`\n"
        f"📌 **Версия:** {SERVER_VERSION}\n"
        f"📝 **Описание:** {SERVER_DESCRIPTION}\n"
        f"🎮 **Ивенты:** Каждые {EVENT_INTERVAL} минут\n"
        f"🌎 **Регион:** Россия (МСК)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔹 **Особенности:**\n"
        f"• Регулярные ивенты\n"
        f"• Дружное комьюнити\n"
        f"• Анти-чит защита\n"
        f"• Bedrock геймплей\n"
        f"• Онлайн до 6666+ игроков\n\n"
        f"📢 **Наш канал:** https://t.me/nevertime"
    )
    
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"✅ Ответ на /info отправлен пользователю {message.from_user.id}")

@dp.message(Command("when"))
async def cmd_when(message: types.Message):
    """Команда /when - час пик сервера"""
    await log_user_info(message, "when")
    
    current_hour = datetime.now(MSK_TZ).hour
    
    if 20 <= current_hour < 23:
        load = "🔴 ВЫСОКАЯ"
        recommendation = "Сейчас самое активное время! 🎉"
        players_approx = "4000-6666+"
    elif 18 <= current_hour < 20:
        load = "🟡 СРЕДНЯЯ"
        recommendation = "Хорошее время для игры 👍"
        players_approx = "2500-4000"
    elif 23 <= current_hour < 1:
        load = "🟡 СРЕДНЯЯ"
        recommendation = "Ночной прайм-тайм 🌙"
        players_approx = "2000-3500"
    else:
        load = "🟢 НИЗКАЯ"
        recommendation = "Спокойное время, можно поиграть без лагов 😌"
        players_approx = "500-2000"
    
    text = (
        f"📊 **ЧАС ПИК СЕРВЕРА**\n\n"
        f"⏰ **Лучшее время для входа:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Пик активности:** 20:00 - 23:00 МСК (4000-6666+)\n"
        f"• **Вечернее время:** 18:00 - 20:00 МСК (2500-4000)\n"
        f"• **Ночное время:** 23:00 - 01:00 МСК (2000-3500)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        f"📈 **ТЕКУЩАЯ СИТУАЦИЯ:**\n"
        f"• Сейчас {current_hour}:00 МСК\n"
        f"• Загрузка: {load}\n"
        f"• Примерно игроков: {players_approx}\n"
        f"• {recommendation}\n\n"
        
        f"💡 **Совет:** Используй `/online` для точного онлайна!"
    )
    
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"✅ Ответ на /when отправлен пользователю {message.from_user.id}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Команда /stats - показывает статистику бота"""
    await log_user_info(message, "stats")
    
    total_users = get_user_count()
    formatted_total = format_users_count(total_users)
    
    user = message.from_user
    
    text = (
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 **Всего пользователей:** `{formatted_total}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **Ваш профиль:**\n"
        f"• ID: `{user.id}`\n"
        f"• Имя: {user.first_name}\n"
        f"{'• Username: @' + user.username if user.username else ''}\n\n"
        f"📈 **Сервер NeverTime:**\n"
        f"• IP: `{SERVER_IP}:{SERVER_PORT}`\n"
        f"• Ивенты: каждые {EVENT_INTERVAL} минут\n"
        f"• Версия: {SERVER_VERSION}"
    )
    
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"✅ Ответ на /stats отправлен пользователю {message.from_user.id}")

@dp.message(Command("ask"))
async def cmd_ask(message: types.Message):
    """Команда /ask - задать вопрос (с базой знаний)"""
    await log_user_info(message, "ask")
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "🤖 **MINECRAFT ПОМОЩНИК**\n\n"
            "Задай любой вопрос о Minecraft или NeverTime!\n\n"
            "**Примеры:**\n"
            "• `/ask как сделать алмазный меч?`\n"
            "• `/ask где найти незерит?`\n"
            "• `/ask правила NeverTime`\n"
            "• `/ask как приручить волка?`\n\n"
            "✨ _Я отвечу на любой вопрос!_"
        )
        return
    
    question = args[1].lower()
    
    # Показываем "печатает..."
    await bot.send_chat_action(message.chat.id, action="typing")
    
    # База знаний
    knowledge = {
        # NeverTime сервер
        "never": "🌟 **NeverTime**\nIP: mc.nevertime.su:19132\nВерсия: 1.21.40+\nИвенты: каждые 35 минут (первый в 9:15)\nОнлайн до 6666+ игроков\nАдмин: @Havanu",
        "nevertime": "🌟 **NeverTime**\nIP: mc.nevertime.su:19132\nВерсия: 1.21.40+\nИвенты: каждые 35 минут (первый в 9:15)\nОнлайн до 6666+ игроков\nАдмин: @Havanu",
        "сервер": "🌟 **NeverTime**\nIP: mc.nevertime.su:19132\nВерсия: 1.21.40+\nИвенты: каждые 35 минут (первый в 9:15)\nОнлайн до 6666+ игроков\nАдмин: @Havanu",
        
        # Алмазы
        "алмаз": "💎 **Алмазы** лучше всего искать на высоте Y -54. Копай железной или алмазной киркой! Часто рядом с лавой.",
        "алмазы": "💎 **Алмазы** лучше всего искать на высоте Y -54. Копай железной или алмазной киркой! Часто рядом с лавой.",
        
        # Незерит
        "незерит": "🔮 **Незерит** ищут в Незере на высоте Y 8-22. Копай древние обломки алмазной киркой. 4 обломка + 4 золота = 1 незерит.",
        
        # Инструменты
        "кирка": "⛏️ **Алмазная кирка**: 3 алмаза + 2 палки в верстаке. Нужна для добычи обсидиана и незерита.",
        "меч": "🗡️ **Алмазный меч**: 2 алмаза + 1 палка в верстаке. Самое мощное оружие!",
        "стол": "🪑 **Верстак**: 4 доски. Нужен для крафта сложных предметов.",
        "верстак": "🪑 **Верстак**: 4 доски. Нужен для крафта сложных предметов.",
        
        # Мобы
        "волк": "🐺 **Волк** приручается костями. Дай волку кость (ПКМ), пока не появится красный ошейник. Корми мясом для лечения.",
        "дракон": "🐉 **Дракон Края**: 1. Разрушь кристаллы на башнях 2. Стреляй из лука 3. Когда сядет - бей мечом. Получишь элитры!",
        
        # Ивенты
        "ивент": "🎉 **Ивенты на NeverTime** каждые 35 минут! Первый в 9:15 МСК. Участвуй и получай редкие награды! Используй /event для таймера.",
        "ивенты": "🎉 **Ивенты на NeverTime** каждые 35 минут! Первый в 9:15 МСК. Участвуй и получай редкие награды! Используй /event для таймера.",
        
        # Правила
        "правила": "📜 **Правила NeverTime**:\n1. Без читов\n2. Уважай других\n3. Не гриферить\n4. Не спамить\nНарушителей банят!",
        
        # Админ
        "админ": "👮 **Администратор**: @Havanu. Пиши по любым вопросам, багам и жалобам!",
        "поддержка": "👮 **Администратор**: @Havanu. Пиши по любым вопросам, багам и жалобам!",
        
        # Команды
        "команды": "📋 **Команды бота**:\n/start - привет\n/event - таймер ивента\n/online - онлайн\n/info - о сервере\n/when - час пик\n/stats - статистика\n/ask - задать вопрос\n/question - спросить админа",
    }
    
    # Ищем ответ
    answer = None
    for key, value in knowledge.items():
        if key in question:
            answer = value
            break
    
    if answer:
        await message.answer(answer)
    else:
        # Если не нашли - отправляем админу
        admin_id = 5469562319
        await bot.send_message(
            admin_id,
            f"📨 **Вопрос от {message.from_user.full_name}**\n"
            f"❓ {question}"
        )
        
        await message.answer(
            "❓ Я не знаю точного ответа. Я отправил вопрос администратору @Havanu, он скоро ответит!"
        )

# ==================== КОМАНДА /question ====================
@dp.message(Command("question"))
async def cmd_question(message: types.Message):
    """Команда /question - задать вопрос администратору"""
    await log_user_info(message, "question")
    
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "❓ **Как задать вопрос администратору?**\n\n"
            "Напиши: `/question твой вопрос`\n"
            "Пример: `/question как зарегистрироваться?`"
        )
        return
    
    question = args[1]
    user = message.from_user
    admin_id = 5469562319
    
    await message.answer("✅ Ваш вопрос отправлен администратору! Ожидайте ответа.")
    
    await bot.send_message(
        admin_id,
        f"📨 **Вопрос от {user.full_name}**\n"
        f"🆔 ID: `{user.id}`\n"
        f"📱 @{user.username if user.username else 'нет'}\n\n"
        f"❓ {question}\n\n"
        f"✏️ Ответь на это сообщение, чтобы отправить ответ пользователю."
    )

@dp.message()
async def forward_reply(message: types.Message):
    """Пересылает ответ админа пользователю"""
    admin_id = 5469562319
    
    # Проверяем, что сообщение от админа и это ответ на другое сообщение
    if message.from_user.id == admin_id and message.reply_to_message:
        original_text = message.reply_to_message.text
        
        # Ищем ID пользователя
        if "🆔 ID: `" in original_text:
            try:
                lines = original_text.split('\n')
                for line in lines:
                    if "🆔 ID: `" in line:
                        user_id_str = line.replace("🆔 ID: `", "").replace("`", "").strip()
                        user_id = int(user_id_str)
                        
                        # Отправляем ответ пользователю
                        await bot.send_message(
                            user_id,
                            f"📬 **Ответ от администратора:**\n\n{message.text}"
                        )
                        
                        await message.reply("✅ Ответ успешно отправлен пользователю!")
                        return
                        
            except Exception as e:
                await message.reply(f"❌ Ошибка при отправке: {e}")

# ==================== 24/7 РАБОТА ====================
app = Flask(__name__)

@app.route('/')
def home():
    total_users = get_user_count()
    formatted = format_users_count(total_users)
    return f"""
    <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                    background: rgba(255,255,255,0.1);
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                }}
                .number {{
                    font-size: 64px;
                    font-weight: bold;
                    margin: 20px 0;
                }}
                .label {{
                    font-size: 24px;
                    opacity: 0.9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 NeverTime Bot</h1>
                <div class="number">{formatted}</div>
                <div class="label">пользователей</div>
                <p style="margin-top: 30px;">✅ Бот работает 24/7 на GitHub + Render</p>
            </div>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ==================== ЗАПУСК БОТА ====================
async def main():
    """Главная функция запуска"""
    init_users_db()
    
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК БОТА NeverTime на GitHub + Render")
    logger.info("=" * 50)
    
    logger.info(f"🌍 Сервер: {SERVER_IP}:{SERVER_PORT}")
    logger.info(f"🎮 Ивенты: каждые {EVENT_INTERVAL} минут, первый в {FIRST_EVENT_TIME}")
    
    asyncio.create_task(check_event_notifications())
    asyncio.create_task(check_server_status())
    
    logger.info("✅ Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("✅ Flask сервер запущен для 24/7 работы")
    
    # Запускаем б
