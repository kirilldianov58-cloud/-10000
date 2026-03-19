import asyncio
import sqlite3
from datetime import datetime, timedelta
import httpx
from cachetools import TTLCache
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = "7728656883:AAERNHyCW90kEVSZlyAe61EDrSigb98l1qE"
FOOTBALL_DATA_TOKEN = "ec0171bdf2db4f6ba9f95fb95ce0deb0"

# ID лиг в football-data.org
LEAGUES = {
    "apl": {"id": "PL", "name": "АПЛ", "logo": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "laliga": {"id": "PD", "name": "Ла Лига", "logo": "🇪🇸"},
    "bundesliga": {"id": "BL1", "name": "Бундеслига", "logo": "🇩🇪"},
    "seriea": {"id": "SA", "name": "Серия А", "logo": "🇮🇹"},
    "ucl": {"id": "CL", "name": "Лига Чемпионов", "logo": "🏆"}  # только для меню
}

# Premium эмодзи (ID)
EMOJI = {
    "football": "5377799315202783755",      # для приветствия
    "goal": "5375159220280762629",          # для уведомлений о голах
    "cup": "5434052314354699255",           # для Лиги чемпионов
    "pos1": "5188399349167589164",
    "pos2": "5190499034124551179",
    "pos3": "5190486368265995588",
    "pos4": "5190448443704772486",
    "pos5": "5188147436450776140",
    "pos6": "5190822449456908974",
    "pos7": "5190402324345952285",
    "pos8": "5190579517516710767",
    "pos9": "5188666655047188275",
}

# Словарь перевода названий команд на русский
TEAM_TRANSLATIONS = {
    "Real Madrid": "Реал Мадрид",
    "Elche": "Эльче",
    "West Ham United": "Вест Хэм Юнайтед",
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
    "Bayern Munich": "Бавария",
    "Atlético Madrid": "Атлетико Мадрид",
    "Tottenham": "Тоттенхэм",
    "Newcastle": "Ньюкасл",
    "Barcelona": "Барселона",
    "Bayer Leverkusen": "Байер",
    "Arsenal": "Арсенал",
    "Bodø/Glimt": "Буде-Глимт",
    "Sporting CP": "Спортинг",
    "Paris Saint-Germain": "ПСЖ",
    "Chelsea": "Челси",
}

def translate_team(name):
    return TEAM_TRANSLATIONS.get(name, name)

# Кэш для таблиц и расписания
cache = {
    'standings': TTLCache(maxsize=50, ttl=900),
    'matches': TTLCache(maxsize=100, ttl=300),
    'live': TTLCache(maxsize=20, ttl=30),
}

# Часовые пояса
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

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С FOOTBALL-DATA.ORG ==================
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
        return cache['standings'][cache_key]

    url = f"https://api.football-data.org/v4/competitions/{competition_id}/standings"
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if "standings" in data and len(data["standings"]) > 0:
                    table = data["standings"][0]["table"]
                    cache['standings'][cache_key] = table
                    return table
            print(f"⚠️ Ошибка таблицы: {resp.status_code}")
            return []
    except Exception as e:
        print(f"❌ Ошибка standings: {e}")
        return []

async def fetch_live_matches_fd():
    cache_key = "live_matches_fd"
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
                return []
    except Exception as e:
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

# ================== ДАННЫЕ ЛИГИ ЧЕМПИОНОВ (статические) ==================
UCL_PAST = [
    {"round": "1/8 финала", "date": "10.03.2026", "home": "Реал Мадрид", "away": "Манчестер Сити", "score": "3:0"},
    {"round": "1/8 финала", "date": "10.03.2026", "home": "ПСЖ", "away": "Челси", "score": "5:2"},
    {"round": "1/8 финала", "date": "11.03.2026", "home": "Бавария", "away": "Аталанта", "score": "6:1"},
    # ... добавьте остальные завершённые матчи
]

UCL_UPCOMING = [
    {"round": "1/4 финала", "date": "01.04.2026", "home": "Реал Мадрид", "away": "ПСЖ"},
    {"round": "1/4 финала", "date": "02.04.2026", "home": "Бавария", "away": "Арсенал"},
    # ... добавьте предстоящие
]

# ================== МЕНЮ (ТОЛЬКО ОБЫЧНЫЕ ЭМОДЗИ В КНОПКАХ) ==================
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
            InlineKeyboardButton("🔔 Голы и карточки LIVE", callback_data="goal_live")
        ],
        [
            InlineKeyboardButton("⭐ Мои подписки", callback_data="my_subs")
        ]
    ])

def league_menu(league_key):
    league = LEAGUES[league_key]
    if league_key == "ucl":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Прошедшие матчи", callback_data="ucl_past")],
            [InlineKeyboardButton("⏳ Предстоящие матчи", callback_data="ucl_upcoming")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 Ближайшие матчи (48ч)", callback_data=f"matches_{league_key}")],
            [InlineKeyboardButton("📊 Таблица", callback_data=f"table_{league_key}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ])

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update_user_stats(user.id, user.first_name, user.username)
    await update.message.reply_text(
        f"<tg-emoji emoji-id='{EMOJI['football']}'>⚽</tg-emoji> <b>Футбольный бот PRO</b>\n\n<i>Выберите лигу:</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )

# ================== МАТЧИ ЗА 48 ЧАСОВ ==================
async def matches_next_48h(query, league_key):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    league = LEAGUES[league_key]
    date_from = datetime.now().strftime("%Y-%m-%d")
    date_to = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d")

    cache_key = f"matches_{league['id']}_{date_from}_{date_to}"
    cached_matches = cache['matches'].get(cache_key)
    if cached_matches is not None:
        matches = cached_matches
        loading_msg = None
    else:
        loading_msg = await query.message.reply_text("⏳ Загружаю матчи...")
        matches = await fetch_matches(league["id"], date_from, date_to)

    if not matches:
        text = f"📅 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет матчей с {date_from} по {date_to}</i>"
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
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
        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

# ================== ТАБЛИЦА ==================
async def show_table(query, league_key):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    league = LEAGUES[league_key]

    cache_key = f"standings_{league['id']}"
    cached_table = cache['standings'].get(cache_key)
    if cached_table is not None:
        table = cached_table
        loading_msg = None
    else:
        loading_msg = await query.message.reply_text("⏳ Загружаю таблицу...")
        table = await fetch_standings(league["id"])

    if not table:
        text = f"📊 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет данных таблицы</i>"
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return

    text = f"{league['logo']} <b>ТАБЛИЦА {league['name']}</b>\n\n"
    for row in table[:10]:
        team = row["team"]["name"]
        pos = row["position"]
        pts = row["points"]
        played = row["playedGames"]
        won = row["won"]
        draw = row["draw"]
        lost = row["lost"]

        # Вставляем premium эмодзи для позиции
        pos_emoji_id = EMOJI.get(f"pos{pos}")
        if pos_emoji_id:
            pos_str = f"<tg-emoji emoji-id='{pos_emoji_id}'>#{pos}</tg-emoji>"
        else:
            pos_str = f"{pos}."

        text += f"{pos_str} {team}\n   {pts} очков | И:{played} В:{won} Н:{draw} П:{lost}\n\n"

    if loading_msg:
        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

# ================== LIVE МАТЧИ ==================
async def live_matches(query):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    loading_msg = await query.message.reply_text("⏳ Загружаю live‑матчи...")
    matches = await fetch_live_matches_fd()

    if not matches:
        text = "🔴 <b>LIVE матчи</b>\n\n<i>Сейчас нет матчей в прямом эфире</i>"
        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu())
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

        text += f"⚽ <b>{home_ru}</b> {score_h}–{score_a} <b>{away_ru}</b>"
        if minute:
            text += f"  ({minute})"
        text += f"\n   <i>{league_name}</i>\n\n"

    await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)

# ================== ГОЛЫ И КАРТОЧКИ LIVE ==================
async def goal_live_menu(query):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    matches = await fetch_live_matches_fd()
    if not matches:
        await query.edit_message_text(
            "🔔 <b>Голы и карточки LIVE</b>\n\n<i>Сейчас нет матчей в прямом эфире</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return

    text = "🔔 <b>Выберите матч для подписки на события:</b>\n\n"
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

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def goal_subscribe(query, match_id):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    try:
        cursor.execute("INSERT OR IGNORE INTO goal_subscriptions (user_id, match_id) VALUES (?, ?)", (user.id, match_id))
        conn.commit()
        await query.edit_message_text(
            f"✅ Вы подписались на события в этом матче!",
            reply_markup=main_menu()
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка подписки: {e}")

async def goal_unsubscribe(query, match_id):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    cursor.execute("DELETE FROM goal_subscriptions WHERE user_id=? AND match_id=?", (user.id, match_id))
    conn.commit()
    await query.edit_message_text(
        f"❌ Вы отписались от событий в этом матче.",
        reply_markup=main_menu()
    )

# ================== ЛИГА ЧЕМПИОНОВ – ПРОШЕДШИЕ И ПРЕДСТОЯЩИЕ ==================
async def ucl_past(query):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    text = f"<tg-emoji emoji-id='{EMOJI['cup']}'>🏆</tg-emoji> <b>ЛИГА ЧЕМПИОНОВ 2025/26 – ПРОШЕДШИЕ МАТЧИ</b>\n\n"
    for match in UCL_PAST:
        text += f"{match['date']}  {match['home']} – {match['away']}  {match['score']}  ({match['round']})\n"

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=league_menu("ucl"))

async def ucl_upcoming(query):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    text = f"<tg-emoji emoji-id='{EMOJI['cup']}'>🏆</tg-emoji> <b>ЛИГА ЧЕМПИОНОВ 2025/26 – ПРЕДСТОЯЩИЕ МАТЧИ</b>\n\n"
    for match in UCL_UPCOMING:
        text += f"{match['date']}  {match['home']} – {match['away']}  ({match['round']})\n"

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=league_menu("ucl"))

# ================== ПОДПИСКИ НА КОМАНДЫ ==================
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

async def show_league_teams(query, league_key):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    league = LEAGUES[league_key]
    loading_msg = await query.message.reply_text("⏳ Загружаю команды...")

    # Здесь можно будет потом добавить получение команд из API, пока пример
    teams = ["Реал Мадрид", "Барселона", "Манчестер Сити", "Ливерпуль", "Бавария"]
    if not teams:
        await loading_msg.edit_text(
            f"❌ Не удалось загрузить команды {league['name']}",
            reply_markup=main_menu()
        )
        return

    text = f"{league['logo']} <b>Команды {league['name']}</b>\n\n"
    keyboard = []
    for i in range(0, len(teams), 2):
        row = []
        team1 = teams[i]
        row.append(InlineKeyboardButton(team1, callback_data=f"sub_team_{team1}"))
        if i+1 < len(teams):
            team2 = teams[i+1]
            row.append(InlineKeyboardButton(team2, callback_data=f"sub_team_{team2}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"league_{league_key}")])

    await loading_msg.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def my_subscriptions(query, user_id):
    await update_user_stats(query.from_user.id, query.from_user.first_name, query.from_user.username)

    cursor.execute("SELECT team FROM subscriptions WHERE user_id=?", (user_id,))
    subs = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT match_id FROM goal_subscriptions WHERE user_id=?", (user_id,))
    goal_subs = [row[0] for row in cursor.fetchall()]

    if not subs and not goal_subs:
        await query.edit_message_text(
            "⭐ <b>У вас нет подписок</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return

    text = "⭐ <b>МОИ ПОДПИСКИ</b>\n\n"
    if subs:
        text += "<b>Команды:</b>\n"
        for team in subs:
            text += f"• {team}\n"
        text += "\n"
    if goal_subs:
        text += "<b>Матчи (уведомления о событиях):</b>\n"
        for mid in goal_subs:
            text += f"• ID матча: {mid}\n"
        text += "\n"

    keyboard = []
    if subs:
        for team in subs:
            keyboard.append([InlineKeyboardButton(f"❌ Отписаться от команды {team}", callback_data=f"unsub_team_{team}")])
    if goal_subs:
        for mid in goal_subs:
            keyboard.append([InlineKeyboardButton(f"❌ Отписаться от матча {mid}", callback_data=f"goal_unsub_{mid}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================== ОБРАБОТЧИК КНОПОК ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    await update_user_stats(query.from_user.id, query.from_user.first_name, query.from_user.username)

    if data == "back_to_main":
        await query.edit_message_text(
            "<b>Выберите лигу:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return

    if data.startswith("league_"):
        league_key = data.replace("league_", "")
        league = LEAGUES[league_key]
        await query.edit_message_text(
            f"{league['logo']} <b>{league['name']}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=league_menu(league_key)
        )
        return

    if data.startswith("matches_"):
        league_key = data.replace("matches_", "")
        await matches_next_48h(query, league_key)
        return

    if data.startswith("table_"):
        league_key = data.replace("table_", "")
        await show_table(query, league_key)
        return

    if data == "ucl_past":
        await ucl_past(query)
        return

    if data == "ucl_upcoming":
        await ucl_upcoming(query)
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

    if data.startswith("teams_"):
        league_key = data.replace("teams_", "")
        await show_league_teams(query, league_key)
        return

    if data == "my_subs":
        await my_subscriptions(query, user_id)
        return

    if data.startswith("sub_team_"):
        team = data.replace("sub_team_", "")
        if await subscribe_team(user_id, team):
            await query.edit_message_text(
                f"✅ <b>Подписка на команду {team} оформлена!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu()
            )
        else:
            await query.edit_message_text(
                f"ℹ️ <b>Вы уже подписаны на {team}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu()
            )
        return

    if data.startswith("unsub_team_"):
        team = data.replace("unsub_team_", "")
        await unsubscribe_team(user_id, team)
        await query.edit_message_text(
            f"❌ <b>Отписка от команды {team} выполнена</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return

# ================== ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ МАТЧЕЙ ==================
last_scores = {}
notified_start = set()

async def match_checker(app):
    print("🔄 Запущен проверщик матчей (football-data.org)")
    while True:
        try:
            matches = await fetch_live_matches_fd()
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
                    for (user_id,) in users:
                        try:
                            await app.bot.send_message(
                                chat_id=user_id,
                                text=f"🏁 <b>Матч начался!</b>\n\n{home} vs {away}",
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
                    for (user_id,) in users:
                        try:
                            await app.bot.send_message(
                                chat_id=user_id,
                                text=f"<tg-emoji emoji-id='{EMOJI['goal']}'>⚽</tg-emoji> <b>ГОЛ!</b>\n\n{home} {hs}-{aw} {away}",
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            print(f"Ошибка отправки уведомления о голе: {e}")
                    last_scores[fixture_id] = score

        except Exception as e:
            print(f"Ошибка в match_checker: {e}")

        await asyncio.sleep(30)

# ================== СТАТИСТИКА (ТОЛЬКО ДЛЯ ВЛАДЕЛЬЦА) ==================
OWNER_ID =  6298119477 # ⚠️ ЗАМЕНИТЕ НА СВОЙ USER ID

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return

    await update_user_stats(user.id, user.first_name, user.username)

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

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== ЗАПУСК ==================
def main():
    print("=" * 60)
    print("⚽ ФУТБОЛЬНЫЙ БОТ PRO (финальная версия)")
    print("=" * 60)
    print("✅ football-data.org: live‑матчи, таблицы, расписание")
    print("✅ Лига чемпионов: статические списки (обновляйте вручную)")
    print("✅ Premium эмодзи в тексте")
    print("✅ Автоудаление: каждое нажатие редактирует сообщение")
    print("=" * 60)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    loop = asyncio.get_event_loop()
    loop.create_task(match_checker(app))

    print("🚀 Бот запущен! Откройте Telegram и отправьте /start")
    app.run_polling()

if __name__ == "__main__":
    main()
