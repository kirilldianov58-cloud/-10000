import asyncio
import sqlite3
from datetime import datetime, timedelta
import httpx
from cachetools import TTLCache
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram

print(f"🔍 Версия python-telegram-bot: {telegram.__version__}")

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = "7728656883:AAERNHyCW90kEVSZlyAe61EDrSigb98l1qE"
FOOTBALL_DATA_TOKEN = "ec0171bdf2db4f6baf095fb95ce0deb0"

LEAGUES = {
    "apl": {"id": "PL", "name": "АПЛ", "logo": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "laliga": {"id": "PD", "name": "Ла Лига", "logo": "🇪🇸"},
    "bundesliga": {"id": "BL1", "name": "Бундеслига", "logo": "🇩🇪"},
    "seriea": {"id": "SA", "name": "Серия А", "logo": "🇮🇹"},
    "ucl": {"id": "CL", "name": "Лига Чемпионов", "logo": "🏆"}
}

# ================== ПРЕМИУМ-ЭМОДЗИ ==================
# Цифры 1-9
DIGIT_EMOJIS = {
    1: "5188399349167589164",
    2: "5190499034124551179",
    3: "5190486368265995588",
    4: "5190448443704772486",
    5: "5188147436450776140",
    6: "5190822449456908974",
    7: "5190402324345952285",
    8: "5190579517516710767",
    9: "5188666655047188275"
}

# Прочие эмодзи
BALL_EMOJI_ID = "5375159220280762629"          # ⚽ мяч
BELL_EMOJI_ID = "5458603043203327669"           # 🔔 колокольчик
STAR_EMOJI_ID = "5438496463044752972"           # ⭐ звезда
HOME_EMOJI_ID = "5416041192905265756"           # 🏠 домик
PLANE_EMOJI_ID = "5463424023734014980"          # ✈️ самолётик

# Эмодзи клубов
TEAM_EMOJIS = {
    "Галатасарай": "5253576384122466632",
    "Ливерпуль": "5255735051865306983",
    "Аталанта": "5253757747706474890",
    "Бавария": "5253864907140511757",
    "Атлетико Мадрид": "5253945124244699125",
    "Тоттенхэм": "5434120393881308031",
    "Ньюкасл": "5253963167402309495",
    "Барселона": "5253967084412482836",
    "Байер": "5253507797789719005",
    "Арсенал": "5253505916594042828",
    "Будё-Глимт": "5312480443247926681",
    "Спортинг": "5253541045131555470",
    "Реал Мадрид": "5249452120301642363",
    "Манчестер Сити": "5251315569172422538",
    "ПСЖ": "5253720231167148285",
    "Челси": "5253502927296803369",
}

# ================== ПЕРЕВОД КОМАНД ==================
TEAM_TRANSLATIONS = {
    "Real Madrid": "Реал Мадрид",
    "Elche": "Эльче",
    "West Ham United": "Вест Хэм",
    "Manchester City": "Манчестер Сити",
    "KVC Westerlo": "Вестерло",
    "Club Brugge KV": "Брюгге",
    "Kilmarnock": "Килмарнок",
    "Heart of Midlothian": "Хартс",
    "AFC Ajax": "Аякс",
    "Sparta Rotterdam": "Спарта Роттердам",
    "AS Monaco": "Монако",
    "Stade Brestois": "Брест",
    "Vitória": "Витория",
    "Atlético Mineiro": "Атлетико Минейро",
    "Galatasaray": "Галатасарай",
    "Liverpool": "Ливерпуль",
    "Atalanta": "Аталанта",
    "Bayern": "Бавария",
    "Atlético Madrid": "Атлетико Мадрид",
    "Tottenham": "Тоттенхэм",
    "Newcastle": "Ньюкасл",
    "Barcelona": "Барселона",
    "Bayer Leverkusen": "Байер",
    "Arsenal": "Арсенал",
    "Bodø/Glimt": "Будё-Глимт",
    "Sporting CP": "Спортинг",
    "PSG": "ПСЖ",
    "Chelsea": "Челси",
    "Manchester United": "Манчестер Юнайтед",
    "Internazionale": "Интер",
    "Juventus": "Ювентус",
    "Benfica": "Бенфика",
    "Borussia Dortmund": "Боруссия Д",
    "Club Brugge": "Брюгге",
    "Shakhtar Donetsk": "Шахтёр",
    "RB Leipzig": "РБ Лейпциг",
    "Porto": "Порту",
    "Ajax": "Аякс",
    "Rangers": "Рейнджерс",
    "Eintracht Frankfurt": "Айнтрахт",
    "Napoli": "Наполи",
    "Milan": "Милан",
    "Lazio": "Лацио",
    "Olympique Marseille": "Марсель",
    "Sporting Lisbon": "Спортинг",
}

def translate_team(name):
    return TEAM_TRANSLATIONS.get(name, name)

# ================== КЭШ ==================
cache = {
    'standings': TTLCache(maxsize=50, ttl=900),
    'matches': TTLCache(maxsize=100, ttl=300),
    'live': TTLCache(maxsize=20, ttl=30),
}

# ================== ЧАСОВЫЕ ПОЯСА ==================
UTC_TZ = pytz.UTC
MSK_TZ = pytz.timezone('Europe/Moscow')

# ================== БАЗА ДАННЫХ ==================
conn = sqlite3.connect("football_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER, team TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS goal_subscriptions (user_id INTEGER, match_id INTEGER, PRIMARY KEY (user_id, match_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS users ("
               "user_id INTEGER PRIMARY KEY, "
               "first_name TEXT, "
               "username TEXT, "
               "first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
               "last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
               "commands_count INTEGER DEFAULT 0)")
conn.commit()

# ================== ХРАНИЛИЩЕ ID ПОСЛЕДНИХ СООБЩЕНИЙ ==================
last_message_ids = {}

async def delete_previous_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет предыдущее сообщение бота в этом чате, если оно есть."""
    if chat_id in last_message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_message_ids[chat_id])
        except Exception as e:
            print(f"Ошибка при удалении сообщения {last_message_ids[chat_id]}: {e}")

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С API ==================
async def fetch_matches(competition_id, date_from, date_to):
    cache_key = f"matches_{competition_id}_{date_from}_{date_to}"
    if cache_key in cache['matches']:
        return cache['matches'][cache_key]

    url = "https://api.football-data.org/v4/matches"
    params = {
        "competitions": competition_id,
        "dateFrom": date_from,
        "dateTo": date_to
    }
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("matches", [])
                cache['matches'][cache_key] = matches
                return matches
            else:
                print(f"⚠️ Ошибка API матчей: {resp.status_code}")
                return []
    except Exception as e:
        print(f"❌ Ошибка запроса матчей: {e}")
        return []

async def fetch_standings(competition_id):
    cache_key = f"standings_{competition_id}"
    if cache_key in cache['standings']:
        print(f"📦 standings из кэша: {competition_id}")
        return cache['standings'][cache_key]

    url = f"https://api.football-data.org/v4/competitions/{competition_id}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    print(f"🔍 Запрос standings: {url}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            print(f"📡 Статус standings: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print("📦 Ответ API (первые 500 символов):", str(data)[:500])
                if "standings" in data and len(data["standings"]) > 0:
                    table = data["standings"][0]["table"]
                    cache['standings'][cache_key] = table
                    print(f"✅ Получено {len(table)} команд")
                    return table
                else:
                    print("⚠️ В ответе нет standings или они пусты")
                    return []
            else:
                print(f"⚠️ Ошибка standings: {resp.status_code}")
                print(f"📄 Текст ответа: {resp.text[:200]}")
                return []
    except Exception as e:
        import traceback
        print(f"❌ Исключение в standings: {e}")
        traceback.print_exc()
        return []

async def fetch_live_matches():
    cache_key = "live_matches"
    if cache_key in cache['live']:
        return cache['live'][cache_key]

    url = "https://api.football-data.org/v4/matches"
    params = {"status": "LIVE"}
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("matches", [])
                cache['live'][cache_key] = matches
                return matches
            else:
                print(f"⚠️ Ошибка API live: {resp.status_code}")
                return []
    except Exception as e:
        print(f"❌ Ошибка запроса live: {e}")
        return []

# ================== ВРЕМЯ ==================
def utc_to_msk(utc_time_str):
    try:
        if utc_time_str.endswith('Z'):
            utc_time_str = utc_time_str[:-1] + '+00:00'
        utc_dt = datetime.fromisoformat(utc_time_str)
        if utc_dt.tzinfo is None:
            utc_dt = UTC_TZ.localize(utc_dt)
        msk_dt = utc_dt.astimezone(MSK_TZ)
        return msk_dt
    except Exception as e:
        print(f"❌ Ошибка преобразования времени: {e}")
        return None

# ================== СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ ==================
async def update_user_stats(user_id, first_name=None, username=None):
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP, commands_count = commands_count + 1 WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("INSERT INTO users (user_id, first_name, username, commands_count) VALUES (?, ?, ?, 1)",
                       (user_id, first_name, username))
    conn.commit()

# ================== ДАННЫЕ ЛИГИ ЧЕМПИОНОВ 2025/26 (СТАТИЧЕСКИЕ) ==================
UCL_PLAYOFF = {
    "round_of_16": {
        "name": "1/8 финала",
        "first_leg_dates": "10–11 марта 2026",
        "second_leg_dates": "17–18 марта 2026",
        "matches": [
            {
                "home_first": "Галатасарай", "away_first": "Ливерпуль",
                "home_second": "Ливерпуль", "away_second": "Галатасарай",
                "first_score": "1:0", "second_score": "0:4",
                "agg": "1:4", "winner": "Ливерпуль"
            },
            {
                "home_first": "Аталанта", "away_first": "Бавария",
                "home_second": "Бавария", "away_second": "Аталанта",
                "first_score": "1:6", "second_score": "1:4",
                "agg": "2:10", "winner": "Бавария"
            },
            {
                "home_first": "Атлетико Мадрид", "away_first": "Тоттенхэм",
                "home_second": "Тоттенхэм", "away_second": "Атлетико Мадрид",
                "first_score": "5:2", "second_score": "2:3",
                "agg": "7:5", "winner": "Атлетико Мадрид"
            },
            {
                "home_first": "Ньюкасл", "away_first": "Барселона",
                "home_second": "Барселона", "away_second": "Ньюкасл",
                "first_score": "1:1", "second_score": "7:2",
                "agg": "3:8", "winner": "Барселона"
            },
            {
                "home_first": "Байер", "away_first": "Арсенал",
                "home_second": "Арсенал", "away_second": "Байер",
                "first_score": "1:1", "second_score": "2:0",
                "agg": "1:3", "winner": "Арсенал"
            },
            {
                "home_first": "Будё-Глимт", "away_first": "Спортинг",
                "home_second": "Спортинг", "away_second": "Будё-Глимт",
                "first_score": "3:0", "second_score": "5:0",
                "agg": "3:5", "winner": "Спортинг"
            },
            {
                "home_first": "Реал Мадрид", "away_first": "Манчестер Сити",
                "home_second": "Манчестер Сити", "away_second": "Реал Мадрид",
                "first_score": "3:0", "second_score": "2:1",
                "agg": "4:1", "winner": "Реал Мадрид"
            },
            {
                "home_first": "ПСЖ", "away_first": "Челси",
                "home_second": "Челси", "away_second": "ПСЖ",
                "first_score": "5:2", "second_score": "0:3",
                "agg": "5:5 (гв)", "winner": "ПСЖ"
            }
        ]
    },
    "quarterfinals": {
        "name": "1/4 финала",
        "dates": "7–8 апреля 2026",
        "time": "22:00 МСК",
        "matches": [
            {"date": "07.04.2026", "home": "Реал Мадрид", "away": "Бавария"},
            {"date": "07.04.2026", "home": "Спортинг", "away": "Арсенал"},
            {"date": "08.04.2026", "home": "Атлетико Мадрид", "away": "Барселона"},
            {"date": "08.04.2026", "home": "Ливерпуль", "away": "ПСЖ"}
        ]
    },
    "semifinals": {
        "name": "1/2 финала",
        "dates": "28–29 апреля и 5–6 мая 2026",
        "matches": [{"info": "Пары полуфиналистов определятся по итогам 1/4 финала"}]
    },
    "final": {
        "name": "ФИНАЛ",
        "date": "30 мая 2026, Будапешт (Пушкаш Арена)",
        "match": {"info": "Финалисты станут известны позднее"}
    }
}

# ================== МЕНЮ ==================
def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 АПЛ", callback_data="league_apl"),
            InlineKeyboardButton("🇪🇸 Ла Лига", callback_data="league_laliga")
        ],
        [
            InlineKeyboardButton("🇩🇪 Бундеслига", callback_data="league_bundesliga"),
            InlineKeyboardButton("🇮🇹 Серия А", callback_data="league_seriea")
        ],
        [
            InlineKeyboardButton("🏆 Лига Чемпионов", callback_data="league_ucl")
        ],
        [
            InlineKeyboardButton("🔴 LIVE матчи", callback_data="live")
        ],
        [
            InlineKeyboardButton("⚽ Голы и карточки LIVE", callback_data="goal_live")
        ],
        [
            InlineKeyboardButton("⭐ Мои подписки", callback_data="my_subs")
        ]
    ])

def league_menu(league_key):
    league = LEAGUES[league_key]
    buttons = [
        [InlineKeyboardButton("📅 Ближайшие матчи в течение 48ч", callback_data=f"matches_{league_key}")],
        [InlineKeyboardButton("📊 Таблица", callback_data=f"table_{league_key}")],
        [InlineKeyboardButton("➕ Подписаться на команду", callback_data=f"teams_{league_key}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    if league_key == "ucl":
        buttons.insert(0, [InlineKeyboardButton("🏆 Плей-офф 2025/26", callback_data="ucl_playoff")])
    return InlineKeyboardMarkup(buttons)

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.effective_chat.id
    await delete_previous_message(chat_id, context)

    photo_url = "https://i.postimg.cc/RVfDJvGC/START.jpg"
    caption = (
        f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji> '
        f'<b>Футбольный бот PRO</b>\n\n'
        f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji> LIVE-матчи\n'
        f'<tg-emoji emoji-id="{BELL_EMOJI_ID}">🔔</tg-emoji> Голы и карточки LIVE\n'
        f'<tg-emoji emoji-id="{STAR_EMOJI_ID}">⭐</tg-emoji> Подписки на команды\n\n'
        f'<i>👇 Выберите лигу в меню ниже:</i>'
    )

    sent = await update.message.reply_photo(
        photo=photo_url,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )
    last_message_ids[chat_id] = sent.message_id

# ================== МАТЧИ ЗА 48 ЧАСОВ ==================
async def matches_next_48h(update, league_key):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    league = LEAGUES[league_key]
    date_from = datetime.now().strftime("%Y-%m-%d")
    date_to = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d")

    cache_key = f"matches_{league['id']}_{date_from}_{date_to}"
    cached_matches = cache['matches'].get(cache_key)
    if cached_matches is not None:
        matches = cached_matches
        loading_msg = None
    else:
        loading_msg = await update.message.reply_text(f"⏳ Загружаю матчи {league['name']}...")
        matches = await fetch_matches(league["id"], date_from, date_to)

    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])

    if not matches:
        text = f"📅 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет матчей с {date_from} по {date_to}</i>"
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        else:
            sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
            last_message_ids[chat_id] = sent.message_id
        return

    text = f"{league['logo']} <b>МАТЧИ {league['name']}</b>\n"
    text += f"<i>{date_from} – {date_to} (МСК)</i>\n\n"

    for match in matches:
        msk_time = utc_to_msk(match["utcDate"])
        if msk_time:
            time_str = msk_time.strftime("%H:%M")
            date_str = msk_time.strftime("%d.%m")
        else:
            time_str = "??:??"
            date_str = "??.??"

        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        status = match["status"]

        if status == "FINISHED":
            score_h = match["score"]["fullTime"]["home"] or 0
            score_a = match["score"]["fullTime"]["away"] or 0
            text += f"✅ {date_str} {time_str}  <b>{home}</b> {score_h}-{score_a} <b>{away}</b>\n"
        elif status in ["IN_PLAY", "PAUSED"]:
            text += f"🔴 {date_str} {time_str}  <b>{home}</b> vs <b>{away}</b> (в игре)\n"
        else:
            text += f"⏳ {date_str} {time_str}  <b>{home}</b> vs <b>{away}</b>\n"

    if loading_msg:
        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    else:
        sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        last_message_ids[chat_id] = sent.message_id

# ================== ТАБЛИЦА (с премиум-цифрами) ==================
async def show_table(update, league_key):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    league = LEAGUES[league_key]

    cache_key = f"standings_{league['id']}"
    cached_table = cache['standings'].get(cache_key)
    if cached_table is not None:
        table = cached_table
        loading_msg = None
    else:
        loading_msg = await update.message.reply_text(f"⏳ Загружаю таблицу {league['name']}...")
        table = await fetch_standings(league["id"])

    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])

    if not table:
        text = f"📊 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет данных таблицы</i>"
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        else:
            sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
            last_message_ids[chat_id] = sent.message_id
        return

    text = f"{league['logo']} <b>ТАБЛИЦА {league['name']}</b>\n\n"
    for row in table[:9]:
        pos = row["position"]
        team = row["team"]["name"]
        pts = row["points"]
        played = row["playedGames"]
        won = row["won"]
        draw = row["draw"]
        lost = row["lost"]

        if pos in DIGIT_EMOJIS:
            pos_emoji = f'<tg-emoji emoji-id="{DIGIT_EMOJIS[pos]}">{pos}</tg-emoji>'
            text += f"{pos_emoji} <b>{team}</b>\n"
        else:
            text += f"<b>{pos}.</b> {team}\n"
        text += f"   {pts} очков | И:{played} В:{won} Н:{draw} П:{lost}\n\n"

    try:
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        else:
            sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
            last_message_ids[chat_id] = sent.message_id
    except Exception as e:
        print(f"❌ Ошибка при отправке таблицы с HTML: {e}")
        import re
        plain_text = re.sub(r'<[^>]+>', '', text)
        if loading_msg:
            await loading_msg.edit_text(plain_text, reply_markup=back_keyboard)
        else:
            sent = await update.message.reply_text(plain_text, reply_markup=back_keyboard)
            last_message_ids[chat_id] = sent.message_id

# ================== LIVE МАТЧИ ==================
async def live_matches(update):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    matches = await fetch_live_matches()

    if not matches:
        text = "🔴 <b>LIVE матчи</b>\n\n<i>Сейчас нет матчей в прямом эфире</i>"
        sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        return

    text = "🔴 <b>LIVE МАТЧИ</b>\n\n"
    for match in matches:
        league_name = match.get("competition", {}).get("name", "Неизвестная лига")
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        status = match["status"]
        score_h = match["score"]["fullTime"]["home"] or match["score"]["halfTime"]["home"] or 0
        score_a = match["score"]["fullTime"]["away"] or match["score"]["halfTime"]["away"] or 0
        minute = match.get("minute", "")
        if not minute and "IN_PLAY" in status:
            minute = "идет"
        elif status == "PAUSED":
            minute = "перерыв"
        else:
            minute = ""

        home_ru = translate_team(home)
        away_ru = translate_team(away)

        ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
        text += f"{ball_emoji} <b>{home_ru}</b> {score_h}–{score_a} <b>{away_ru}</b>"
        if minute:
            text += f"  ({minute})"
        text += f"\n   <i>{league_name}</i>\n\n"

    sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())
    last_message_ids[chat_id] = sent.message_id

# ================== ГОЛЫ И КАРТОЧКИ LIVE ==================
async def goal_live_menu(update):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    matches = await fetch_live_matches()
    if not matches:
        text = f'<tg-emoji emoji-id="{BELL_EMOJI_ID}">🔔</tg-emoji> <b>Голы и карточки LIVE</b>\n\n<i>Сейчас нет матчей в прямом эфире</i>'
        sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        return

    bell_emoji = f'<tg-emoji emoji-id="{BELL_EMOJI_ID}">🔔</tg-emoji>'
    text = f"{bell_emoji} <b>Выберите матч для подписки на события:</b>\n\n"
    keyboard = []
    for match in matches:
        match_id = match["id"]
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        league = match.get("competition", {}).get("name", "Неизвестная лига")
        home_ru = translate_team(home)
        away_ru = translate_team(away)
        text += f"• {home_ru} vs {away_ru} ({league})\n"
        keyboard.append([InlineKeyboardButton(
            f"🔔 {home_ru} – {away_ru}",
            callback_data=f"goal_sub_{match_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

    sent = await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    last_message_ids[chat_id] = sent.message_id

async def goal_subscribe(update, match_id):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    try:
        cursor.execute("INSERT OR IGNORE INTO goal_subscriptions (user_id, match_id) VALUES (?, ?)", (user.id, match_id))
        conn.commit()
        sent = await update.message.reply_text(
            f"✅ Вы подписались на события в этом матче!",
            reply_markup=main_menu()
        )
        last_message_ids[chat_id] = sent.message_id
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка подписки: {e}")

async def goal_unsubscribe(update, match_id):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    cursor.execute("DELETE FROM goal_subscriptions WHERE user_id=? AND match_id=?", (user.id, match_id))
    conn.commit()
    sent = await update.message.reply_text(
        f"❌ Вы отписались от событий в этом матче.",
        reply_markup=main_menu()
    )
    last_message_ids[chat_id] = sent.message_id

# ================== ЛИГА ЧЕМПИОНОВ (ОБНОВЛЁННАЯ) ==================
async def ucl_playoff(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)

    home_emoji = f'<tg-emoji emoji-id="{HOME_EMOJI_ID}">🏠</tg-emoji>'
    ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
    plane_emoji = f'<tg-emoji emoji-id="{PLANE_EMOJI_ID}">✈️</tg-emoji>'

    text = f"{ball_emoji} <b>ЛИГА ЧЕМПИОНОВ 2025/26 – ПЛЕЙ-ОФФ</b>\n\n"

    # 1/8 финала
    r16 = UCL_PLAYOFF["round_of_16"]
    text += f"<b>{r16['name']}</b> ({r16['first_leg_dates']} – {r16['second_leg_dates']})\n"
    for m in r16["matches"]:
        home_first_ru = translate_team(m['home_first'])
        away_first_ru = translate_team(m['away_first'])
        home_second_ru = translate_team(m['home_second'])
        away_second_ru = translate_team(m['away_second'])

        home_first_emoji = f'<tg-emoji emoji-id="{TEAM_EMOJIS.get(m["home_first"], BALL_EMOJI_ID)}">⚽</tg-emoji>'
        away_first_emoji = f'<tg-emoji emoji-id="{TEAM_EMOJIS.get(m["away_first"], BALL_EMOJI_ID)}">⚽</tg-emoji>'
        home_second_emoji = f'<tg-emoji emoji-id="{TEAM_EMOJIS.get(m["home_second"], BALL_EMOJI_ID)}">⚽</tg-emoji>'
        away_second_emoji = f'<tg-emoji emoji-id="{TEAM_EMOJIS.get(m["away_second"], BALL_EMOJI_ID)}">⚽</tg-emoji>'

        # Первый матч
        text += f"{home_emoji} {home_first_emoji} {home_first_ru} – {away_first_ru} {away_first_emoji} {plane_emoji}  {m['first_score']}\n"
        # Ответный матч
        text += f"   ответный: {home_emoji} {home_second_emoji} {home_second_ru} – {away_second_ru} {away_second_emoji} {plane_emoji}  {m['second_score']}\n"
        # Общий счёт
        text += f"   <b>Общий счёт:</b> {m['agg']} – {m['winner']} выходит в 1/4\n\n"

    # 1/4 финала
    qf = UCL_PLAYOFF["quarterfinals"]
    text += f"<b>{qf['name']}</b> ({qf['dates']}, {qf['time']})\n"
    for m in qf["matches"]:
        home_ru = translate_team(m["home"])
        away_ru = translate_team(m["away"])
        home_emoji_team = f'<tg-emoji emoji-id="{TEAM_EMOJIS.get(m["home"], BALL_EMOJI_ID)}">⚽</tg-emoji>'
        away_emoji_team = f'<tg-emoji emoji-id="{TEAM_EMOJIS.get(m["away"], BALL_EMOJI_ID)}">⚽</tg-emoji>'
        text += f"{m['date']}: {home_emoji} | {home_emoji_team} {home_ru} – {away_ru} {away_emoji_team} | {plane_emoji}\n"
    text += "\n"

    # 1/2 финала и финал
    sf = UCL_PLAYOFF["semifinals"]
    text += f"<b>{sf['name']}</b> ({sf['dates']})\n"
    for m in sf["matches"]:
        text += f"   {m['info']}\n"
    text += "\n"

    final = UCL_PLAYOFF["final"]
    text += f"<b>{final['name']}</b> ({final['date']})\n"
    text += f"   {final['match']['info']}\n"

    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])

    sent = await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    last_message_ids[chat_id] = sent.message_id

# ================== ПОДПИСКИ НА КОМАНДЫ (ДОБАВЛЕННАЯ ФУНКЦИЯ) ==================
async def show_league_teams(update, league_key):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    league = LEAGUES[league_key]
    await update.message.reply_text(f"⏳ Загружаю команды {league['name']}...")

    # Получаем таблицу (она уже в кэше)
    table = await fetch_standings(league["id"])
    if not table:
        sent = await update.message.reply_text(f"❌ Не удалось загрузить команды", reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        return

    # Извлекаем названия команд
    teams = [row["team"]["name"] for row in table]

    text = f"{league['logo']} <b>Команды {league['name']}</b>\n\n"
    keyboard = []
    for i in range(0, len(teams), 2):
        row = []
        row.append(InlineKeyboardButton(teams[i], callback_data=f"sub_team_{teams[i]}"))
        if i+1 < len(teams):
            row.append(InlineKeyboardButton(teams[i+1], callback_data=f"sub_team_{teams[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"league_{league_key}")])

    sent = await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    last_message_ids[chat_id] = sent.message_id

async def subscribe_team(user_id, team):
    cursor.execute("SELECT * FROM subscriptions WHERE user_id=? AND team=?", (user_id, team))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO subscriptions VALUES (?,?)", (user_id, team))
        conn.commit()
        return True
    return False

async def unsubscribe_team(user_id, team):
    cursor.execute("DELETE FROM subscriptions WHERE user_id=? AND team=?", (user_id, team))
    conn.commit()

async def my_subscriptions(update, user_id):
    await update_user_stats(update.from_user.id, update.from_user.first_name, update.from_user.username)
    chat_id = update.message.chat.id
    await delete_previous_message(chat_id, update.get_bot())

    cursor.execute("SELECT team FROM subscriptions WHERE user_id=?", (user_id,))
    subs = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT match_id FROM goal_subscriptions WHERE user_id=?", (user_id,))
    goal_subs = [row[0] for row in cursor.fetchall()]

    if not subs and not goal_subs:
        sent = await update.message.reply_text(
            "⭐ <b>У вас нет подписок</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        last_message_ids[chat_id] = sent.message_id
        return

    star_emoji = f'<tg-emoji emoji-id="{STAR_EMOJI_ID}">⭐</tg-emoji>'
    text = f"{star_emoji} <b>МОИ ПОДПИСКИ</b>\n\n"
    if subs:
        text += "<b>Команды:</b>\n"
        for team in subs:
            text += f"   {star_emoji} {team}\n"
        text += "\n"
    if goal_subs:
        bell_emoji = f'<tg-emoji emoji-id="{BELL_EMOJI_ID}">🔔</tg-emoji>'
        text += f"{bell_emoji} <b>Матчи (уведомления о событиях):</b>\n"
        for mid in goal_subs:
            text += f"   • ID матча: {mid}\n"
        text += "\n"

    keyboard = []
    if subs:
        for team in subs:
            keyboard.append([InlineKeyboardButton(f"❌ Отписаться от команды {team}", callback_data=f"unsub_team_{team}")])
    if goal_subs:
        for mid in goal_subs:
            keyboard.append([InlineKeyboardButton(f"❌ Отписаться от матча {mid}", callback_data=f"goal_unsub_{mid}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

    sent = await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    last_message_ids[chat_id] = sent.message_id

# ================== ОБРАБОТЧИК КНОПОК ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    await update_user_stats(query.from_user.id, query.from_user.first_name, query.from_user.username)

    if data == "back_to_main":
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await query.message.reply_text(
            "<b>Выберите лигу:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        last_message_ids[chat_id] = sent.message_id
        return

    if data.startswith("league_"):
        league_key = data.replace("league_", "")
        league = LEAGUES[league_key]
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await query.message.reply_text(
            f"{league['logo']} <b>{league['name']}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=league_menu(league_key)
        )
        last_message_ids[chat_id] = sent.message_id
        return

    if data.startswith("matches_"):
        league_key = data.replace("matches_", "")
        await matches_next_48h(query, league_key)
        return

    if data.startswith("table_"):
        league_key = data.replace("table_", "")
        await show_table(query, league_key)
        return

    if data.startswith("teams_"):
        league_key = data.replace("teams_", "")
        await show_league_teams(query, league_key)
        return

    if data == "ucl_playoff":
        await ucl_playoff(query, context)
        return

    if data == "live":
        await live_matches(query)
        return

    if data == "goal_live":
        await goal_live_menu(query)
        return

    if data.startswith("goal_sub_"):
        match_id = int(data.replace("goal_sub_", ""))
        await goal_subscribe(query, match_id)
        return

    if data.startswith("goal_unsub_"):
        match_id = int(data.replace("goal_unsub_", ""))
        await goal_unsubscribe(query, match_id)
        return

    if data == "my_subs":
        await my_subscriptions(query, user_id)
        return

    if data.startswith("sub_team_"):
        team = data.replace("sub_team_", "")
        if await subscribe_team(user_id, team):
            chat_id = query.message.chat.id
            await delete_previous_message(chat_id, context)
            sent = await query.message.reply_text(
                f"✅ <b>Подписка на команду {team} оформлена!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu()
            )
            last_message_ids[chat_id] = sent.message_id
        else:
            chat_id = query.message.chat.id
            await delete_previous_message(chat_id, context)
            sent = await query.message.reply_text(
                f"ℹ️ <b>Вы уже подписаны на {team}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu()
            )
            last_message_ids[chat_id] = sent.message_id
        return

    if data.startswith("unsub_team_"):
        team = data.replace("unsub_team_", "")
        await unsubscribe_team(user_id, team)
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await query.message.reply_text(
            f"❌ <b>Отписка от команды {team} выполнена</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        last_message_ids[chat_id] = sent.message_id
        return

# ================== ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ МАТЧЕЙ ==================
last_scores = {}
notified_start = set()

async def match_checker(app):
    print("🔄 Запущен проверщик матчей (football-data.org)")
    while True:
        try:
            matches = await fetch_live_matches()
            for match in matches:
                fixture_id = match["id"]
                home = match["homeTeam"]["name"]
                away = match["awayTeam"]["name"]
                status = match["status"]
                hs = match["score"]["fullTime"]["home"] or match["score"]["halfTime"]["home"] or 0
                aw = match["score"]["fullTime"]["away"] or match["score"]["halfTime"]["away"] or 0
                score = f"{hs}-{aw}"

                if status in ["IN_PLAY", "LIVE"] and fixture_id not in notified_start:
                    cursor.execute("SELECT user_id FROM goal_subscriptions WHERE match_id=?", (fixture_id,))
                    users = cursor.fetchall()
                    ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
                    for (user_id,) in users:
                        try:
                            await app.bot.send_message(
                                chat_id=user_id,
                                text=f"{ball_emoji} <b>Матч начался!</b>\n\n{home} vs {away}",
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            print(f"Ошибка отправки уведомления о старте: {e}")
                    notified_start.add(fixture_id)

                if fixture_id not in last_scores:
                    last_scores[fixture_id] = score

                if last_scores[fixture_id] != score:
                    cursor.execute("SELECT user_id FROM goal_subscriptions WHERE match_id=?", (fixture_id,))
                    users = cursor.fetchall()
                    ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
                    for (user_id,) in users:
                        try:
                            await app.bot.send_message(
                                chat_id=user_id,
                                text=f"{ball_emoji} <b>ГОЛ!</b>\n\n{home} {hs}-{aw} {away}",
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            print(f"Ошибка отправки уведомления о голе: {e}")
                    last_scores[fixture_id] = score

        except Exception as e:
            import traceback
            print(f"❌ Ошибка в match_checker: {e}")
            traceback.print_exc()

        await asyncio.sleep(30)

# ================== СТАТИСТИКА (ТОЛЬКО ДЛЯ ВЛАДЕЛЬЦА) ==================
OWNER_ID = 6298119477  # ⚠️ ЗАМЕНИТЕ НА СВОЙ USER ID

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = update.effective_chat.id
    await delete_previous_message(chat_id, context)

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE date(last_seen) = date('now')")
    today_active = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-7 days')")
    week_active = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE last_seen >= datetime('now', '-30 days')")
    month_active = cursor.fetchone()[0]

    cursor.execute("SELECT team, COUNT(*) as cnt FROM subscriptions GROUP BY team ORDER BY cnt DESC LIMIT 10")
    top_teams = cursor.fetchall()
    teams_text = "\n".join([f"{team}: {cnt}" for team, cnt in top_teams]) or "Нет данных"

    cursor.execute("SELECT user_id, first_name, username, commands_count FROM users ORDER BY commands_count DESC LIMIT 10")
    top_users = cursor.fetchall()
    users_text = "\n".join([f"{first or uid}: {cmds} команд" for uid, first, uname, cmds in top_users]) or "Нет данных"

    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📅 Активных сегодня: {today_active}\n"
        f"📆 Активных за неделю: {week_active}\n"
        f"🗓 Активных за месяц: {month_active}\n\n"
        f"⚽ <b>Топ команд по подпискам:</b>\n{teams_text}\n\n"
        f"🏆 <b>Топ активных пользователей:</b>\n{users_text}"
    )

    sent = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    last_message_ids[chat_id] = sent.message_id

# ================== ЗАПУСК ==================
def main():
    print("=" * 60)
    print("⚽ ФУТБОЛЬНЫЙ БОТ PRO (премиум-эмодзи + статическая ЛЧ)")
    print("=" * 60)
    print("✅ Таблицы и расписание: football-data.org")
    print("✅ Live-матчи и события: football-data.org")
    print("✅ Уведомления о голах (по изменению счёта)")
    print("=" * 60)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(match_checker(app))

    print("🚀 Бот запущен! Откройте Telegram и отправьте /start")
    app.run_polling()

if __name__ == "__main__":   
    main()
