import asyncio
import sqlite3
import os
from datetime import datetime, timedelta
import httpx
from cachetools import TTLCache
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = "7728656883:AAEme2lmHObvqMOoifogEYRiy3LTyk2W5bE"
FOOTBALL_DATA_TOKEN = "ec0171bdf2db4f6baf095fb95ce0deb0"
BSD_API_TOKEN = "658732b3608784390666f3db24627a802add0692"
RAPIDAPI_KEY = os.environ.get("582804ef23f7c43934b59be585002683")  # ключ для API-FOOTBALL (добавьте в переменные окружения)

if not RAPIDAPI_KEY:
    raise ValueError("❌ RAPIDAPI_KEY не задан! Добавьте его в переменные окружения.")

# ID лиг в football-data.org
LEAGUES = {
    "apl": {"id": "PL", "name": "АПЛ", "logo": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "laliga": {"id": "PD", "name": "Ла Лига", "logo": "🇪🇸"},
    "bundesliga": {"id": "BL1", "name": "Бундеслига", "logo": "🇩🇪"},
    "seriea": {"id": "SA", "name": "Серия А", "logo": "🇮🇹"},
    "ucl": {"id": "CL", "name": "Лига Чемпионов", "logo": "🏆"}
}

# Словарь перевода названий команд на русский (можно дополнять)
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

# Кэш для данных ЛЧ (обновляется раз в час)
ucl_cache = {}
last_ucl_update = None

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

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С BSD ==================
async def fetch_live_matches_bsd():
    url = "https://sports.bzzoiro.com/api/live/"
    headers = {"Authorization": f"Token {BSD_API_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                matches = []
                for match in data.get("results", []):
                    # получаем счёт
                    score_home = 0
                    score_away = 0
                    if "score" in match and isinstance(match["score"], dict):
                        score_home = match["score"].get("home", 0)
                        score_away = match["score"].get("away", 0)
                    elif "scores" in match and isinstance(match["scores"], dict):
                        score_home = match["scores"].get("home", 0)
                        score_away = match["scores"].get("away", 0)
                    else:
                        # считаем из инцидентов
                        incidents = match.get("incidents", [])
                        home_goals = sum(1 for inc in incidents if inc.get("type") == "goal" and inc.get("home"))
                        away_goals = sum(1 for inc in incidents if inc.get("type") == "goal" and inc.get("away"))
                        if home_goals > 0 or away_goals > 0:
                            score_home = home_goals
                            score_away = away_goals

                    # лига
                    league_data = match.get("league", {})
                    if isinstance(league_data, dict):
                        league_name = league_data.get("name", "Неизвестная лига")
                    else:
                        league_name = str(league_data)

                    # события
                    incidents = match.get("incidents", [])
                    processed_incidents = []
                    for inc in incidents:
                        processed_incidents.append({
                            "type": inc.get("type"),
                            "minute": inc.get("minute"),
                            "player": inc.get("player"),
                            "team": inc.get("team"),
                            "home": inc.get("home", False),
                            "away": inc.get("away", False),
                            "own_goal": inc.get("own_goal", False),
                            "penalty": inc.get("penalty", False)
                        })

                    matches.append({
                        "id": match["id"],
                        "home_team": translate_team(match["home_team"]),
                        "away_team": translate_team(match["away_team"]),
                        "score_home": score_home,
                        "score_away": score_away,
                        "status": match.get("status", "LIVE"),
                        "minute": match.get("minute", ""),
                        "league": league_name,
                        "incidents": processed_incidents
                    })
                return matches
            else:
                print(f"⚠️ BSD live error: {resp.status_code}")
                return []
    except Exception as e:
        print(f"❌ BSD live exception: {e}")
        return []

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С API-FOOTBALL (ЛЧ) ==================
async def fetch_ucl_matches_from_api():
    """Получает матчи Лиги чемпионов за текущий сезон (2025)."""
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    params = {
        "league": 2,  # Лига чемпионов
        "season": 2025,
        "next": 50  # следующие 50 матчей
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", [])
            else:
                print(f"⚠️ Ошибка API-FOOTBALL: {resp.status_code}")
                return []
    except Exception as e:
        print(f"❌ Ошибка запроса API-FOOTBALL: {e}")
        return []

def group_ucl_matches(matches):
    """Группирует матчи по раундам (1/8, 1/4, 1/2, финал)."""
    grouped = {
        "round_of_16": [],
        "quarterfinals": [],
        "semifinals": [],
        "final": []
    }
    for match in matches:
        round_name = match["league"]["round"]  # например "Round of 16"
        if "Round of 16" in round_name:
            grouped["round_of_16"].append(match)
        elif "Quarter-finals" in round_name:
            grouped["quarterfinals"].append(match)
        elif "Semi-finals" in round_name:
            grouped["semifinals"].append(match)
        elif "Final" in round_name:
            grouped["final"].append(match)
    return grouped

async def update_ucl_cache():
    global ucl_cache, last_ucl_update
    print("🔄 Обновление кэша Лиги чемпионов...")
    matches = await fetch_ucl_matches_from_api()
    if matches:
        ucl_cache = group_ucl_matches(matches)
        last_ucl_update = datetime.now()
        print(f"✅ Кэш ЛЧ обновлён, матчей: {sum(len(v) for v in ucl_cache.values())}")
    else:
        print("⚠️ Не удалось обновить кэш ЛЧ, используем статические данные")

# ================== ФОНОВАЯ ЗАДАЧА ДЛЯ ЛЧ ==================
async def ucl_updater():
    while True:
        await update_ucl_cache()
        await asyncio.sleep(3600)  # обновление раз в час

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

# ================== ДАННЫЕ ЛИГИ ЧЕМПИОНОВ (статический резерв) ==================
UCL_PLAYOFF_STATIC = {
    "round_of_16": {
        "name": "1/8 финала",
        "dates": "10–11 и 17–18 марта 2026",
        "matches": [
            {"home_first": "Галатасарай", "away_first": "Ливерпуль", 
             "home_second": "Ливерпуль", "away_second": "Галатасарай", 
             "first_score": "1:0", "second_score": "—"},
            {"home_first": "Аталанта", "away_first": "Бавария", 
             "home_second": "Бавария", "away_second": "Аталанта", 
             "first_score": "6:1", "second_score": "—"},
            {"home_first": "Атлетико Мадрид", "away_first": "Тоттенхэм", 
             "home_second": "Тоттенхэм", "away_second": "Атлетико Мадрид", 
             "first_score": "5:2", "second_score": "—"},
            {"home_first": "Ньюкасл", "away_first": "Барселона", 
             "home_second": "Барселона", "away_second": "Ньюкасл", 
             "first_score": "1:1", "second_score": "—"},
            {"home_first": "Байер", "away_first": "Арсенал", 
             "home_second": "Арсенал", "away_second": "Байер", 
             "first_score": "1:1", "second_score": "—"},
            {"home_first": "Буде-Глимт", "away_first": "Спортинг", 
             "home_second": "Спортинг", "away_second": "Буде-Глимт", 
             "first_score": "3:0", "second_score": "—"},
            {"home_first": "ПСЖ", "away_first": "Челси", 
             "home_second": "Челси", "away_second": "ПСЖ", 
             "first_score": "5:2", "second_score": "—"},
            {"home_first": "Реал Мадрид", "away_first": "Манчестер Сити", 
             "home_second": "Манчестер Сити", "away_second": "Реал Мадрид", 
             "first_score": "3:0", "second_score": "—"}
        ]
    },
    "quarterfinals": {
        "name": "1/4 финала",
        "dates": "1–2 и 8–9 апреля 2026",
        "matches": [{"info": "Жеребьёвка 1/4 финала пройдёт после завершения 1/8 финала"}]
    },
    "semifinals": {
        "name": "1/2 финала",
        "dates": "22–23 и 29–30 апреля 2026",
        "matches": [{"info": "Пары полуфиналистов определятся по итогам 1/4 финала"}]
    },
    "final": {
        "name": "ФИНАЛ",
        "date": "30 мая 2026, Будапешт",
        "match": {"info": "Финалисты станут известны позднее"}
    }
}

# ================== МЕНЮ ==================
def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="АПЛ",
                callback_data="league_apl",
                icon_custom_emoji_id="5440855216134043525"
            ),
            InlineKeyboardButton(
                text="Ла Лига",
                callback_data="league_laliga",
                icon_custom_emoji_id="5438475709762777893"
            )
        ],
        [
            InlineKeyboardButton(
                text="Бундеслига",
                callback_data="league_bundesliga",
                icon_custom_emoji_id="5433698383279706493"
            ),
            InlineKeyboardButton(
                text="Серия А",
                callback_data="league_seriea",
                icon_custom_emoji_id="5251500918486081233"
            )
        ],
        [
            InlineKeyboardButton(
                text="Лига Чемпионов",
                callback_data="league_ucl",
                icon_custom_emoji_id="5434052314354699255"
            )
        ],
        [
            InlineKeyboardButton(
                text="LIVE матчи",
                callback_data="live",
                icon_custom_emoji_id="5215667808767059302"
            )
        ],
        [
            InlineKeyboardButton(
                text="Голы и карточки LIVE",
                callback_data="goal_live",
                icon_custom_emoji_id="5215667808767059302"
            )
        ],
        [
            InlineKeyboardButton("⭐ Мои подписки", callback_data="my_subs")
        ]
    ])

def league_menu(league_key):
    league = LEAGUES[league_key]
    if league_key == "ucl":
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="🏆 Плей-офф 2025/26",
                    callback_data="ucl_playoff",
                    icon_custom_emoji_id="5434052314354699255"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Ближайшие матчи в течение 48ч",
                    callback_data=f"matches_{league_key}",
                    icon_custom_emoji_id="5274055917766202507"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Таблица",
                    callback_data=f"table_{league_key}",
                    icon_custom_emoji_id="5188147436450776140"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="back_to_main",
                    icon_custom_emoji_id="5258236805890710909"
                )
            ]
        ])
    else:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    text="Ближайшие матчи в течение 48ч",
                    callback_data=f"matches_{league_key}",
                    icon_custom_emoji_id="5274055917766202507"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Таблица",
                    callback_data=f"table_{league_key}",
                    icon_custom_emoji_id="5188147436450776140"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="back_to_main",
                    icon_custom_emoji_id="5258236805890710909"
                )
            ]
        ])

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update_user_stats(user.id, user.first_name, user.username)
    await update.message.reply_text(
        f"<tg-emoji emoji-id='5377799315202783755'>⚽</tg-emoji> <b>Футбольный бот PRO</b>\n\n<i>Выберите лигу:</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )

# ================== МАТЧИ ЗА 48 ЧАСОВ ==================
async def matches_next_48h(update, league_key):
    user = update.from_user
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
        loading_msg = await update.message.reply_text(f"⏳ Загружаю матчи {league['name']}...")
        matches = await fetch_matches(league["id"], date_from, date_to)

    if not matches:
        text = f"📅 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет матчей с {date_from} по {date_to}</i>"
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
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
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== ТАБЛИЦА ==================
async def show_table(update, league_key):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    league = LEAGUES[league_key]

    cache_key = f"standings_{league['id']}"
    cached_table = cache['standings'].get(cache_key)
    if cached_table is not None:
        table = cached_table
        loading_msg = None
    else:
        loading_msg = await update.message.reply_text(f"⏳ Загружаю таблицу {league['name']}...")
        table = await fetch_standings(league["id"])

    if not table:
        text = f"📊 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет данных таблицы</i>"
        if loading_msg:
            await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    pos_emojis = {
        1: "5188399349167589164",
        2: "5190499034124551179",
        3: "5190486368265995588",
        4: "5190448443704772486",
        5: "5188147436450776140",
        6: "5190822449456908974",
        7: "5190402324345952285",
        8: "5190579517516710767",
        9: "5188666655047188275",
    }

    text = f"{league['logo']} <b>ТАБЛИЦА {league['name']}</b>\n\n"
    for row in table[:10]:
        team = row["team"]["name"]
        pos = row["position"]
        pts = row["points"]
        played = row["playedGames"]
        won = row["won"]
        draw = row["draw"]
        lost = row["lost"]
        emoji = pos_emojis.get(pos, f"{pos}.")
        text += f"{emoji} {team}\n   {pts} очков | И:{played} В:{won} Н:{draw} П:{lost}\n\n"

    if loading_msg:
        await loading_msg.edit_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== LIVE МАТЧИ ==================
async def live_matches(update):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    matches = await fetch_live_matches_bsd()

    if not matches:
        await update.message.reply_text(
            "🔴 <b>LIVE матчи</b>\n\n<i>Сейчас нет матчей в прямом эфире</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return

    text = "🔴 <b>LIVE МАТЧИ</b>\n\n"
    for match in matches:
        league_name = match["league"]
        home = match["home_team"]
        away = match["away_team"]
        score_h = match["score_home"]
        score_a = match["score_away"]
        minute = match["minute"]
        status = match["status"]

        if status == "FINISHED":
            status_text = "✅ Завершён"
        else:
            status_text = f"⏱ {minute}'" if minute else ""

        text += f"⚽ <b>{home}</b> {score_h}–{score_a} <b>{away}</b>"
        if status_text:
            text += f"  {status_text}"
        text += f"\n   <i>{league_name}</i>\n\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== ГОЛЫ И КАРТОЧКИ LIVE (ПОДПИСКА) ==================
async def goal_live_menu(update):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    matches = await fetch_live_matches_bsd()
    if not matches:
        await update.message.reply_text(
            "🔔 <b>Голы и карточки LIVE</b>\n\n<i>Сейчас нет матчей в прямом эфире</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return

    text = "🔔 <b>Выберите матч для подписки на события:</b>\n\n"
    keyboard = []
    for match in matches:
        match_id = match["id"]
        home = match["home_team"]
        away = match["away_team"]
        league = match["league"]
        text += f"• {home} vs {away} ({league})\n"
        keyboard.append([InlineKeyboardButton(
            f"🔔 {home} – {away}",
            callback_data=f"goal_sub_{match_id}"
        )])
    keyboard.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_main",
        icon_custom_emoji_id="5258236805890710909"
    )])

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def goal_subscribe(update, match_id):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    try:
        cursor.execute("INSERT OR IGNORE INTO goal_subscriptions (user_id, match_id) VALUES (?, ?)", (user.id, match_id))
        conn.commit()
        await update.message.reply_text(
            f"✅ Вы подписались на события в этом матче!",
            reply_markup=main_menu()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка подписки: {e}")

async def goal_unsubscribe(update, match_id):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    cursor.execute("DELETE FROM goal_subscriptions WHERE user_id=? AND match_id=?", (user.id, match_id))
    conn.commit()
    await update.message.reply_text(
        f"❌ Вы отписались от событий в этом матче.",
        reply_markup=main_menu()
    )

# ================== ЛИГА ЧЕМПИОНОВ – ПЛЕЙ-ОФФ ==================
async def ucl_playoff(update):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    # Используем кэш, если он есть, иначе статический словарь
    data = ucl_cache if ucl_cache else UCL_PLAYOFF_STATIC

    text = "🏆 <b>ЛИГА ЧЕМПИОНОВ 2025/26 – ПЛЕЙ-ОФФ</b>\n\n"

    if "round_of_16" in data and data["round_of_16"]:
        # формат от API может отличаться, упростим для начала
        # покажем просто матчи, если есть
        for match in data["round_of_16"][:10]:  # ограничим
            home = match["teams"]["home"]["name"]
            away = match["teams"]["away"]["name"]
            score = f"{match['goals']['home']}:{match['goals']['away']}"
            date = match["fixture"]["date"][:10]
            text += f"⚽ {home} – {away}  {score}  ({date})\n"
    else:
        # статический вывод
        r16 = data["round_of_16"]
        text += f"<b>{r16['name']}</b>  ({r16['dates']})\n"
        for m in r16["matches"]:
            text += f"   {m['home_first']} – {m['away_first']}  {m['first_score']}  (1-й матч)\n"
            text += f"   {m['home_second']} – {m['away_second']}  {m['second_score']}  (2-й матч)\n\n"
        qf = data["quarterfinals"]
        text += f"<b>{qf['name']}</b> ({qf['dates']})\n"
        for m in qf["matches"]:
            text += f"   {m['info']}\n"
        text += "\n"
        sf = data["semifinals"]
        text += f"<b>{sf['name']}</b> ({sf['dates']})\n"
        for m in sf["matches"]:
            text += f"   {m['info']}\n"
        text += "\n"
        final = data["final"]
        text += f"<b>{final['name']}</b> ({final['date']})\n"
        text += f"   {final['match']['info']}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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

async def show_league_teams(update, league_key):
    user = update.from_user
    await update_user_stats(user.id, user.first_name, user.username)

    league = LEAGUES[league_key]
    await update.message.reply_text(f"⏳ Загружаю команды {league['name']}...")

    # здесь можно добавить получение команд из API, но для простоты пока заглушка
    teams = ["Реал Мадрид", "Барселона", "Манчестер Сити", "Ливерпуль", "Бавария"]  # пример
    if not teams:
        await update.message.reply_text(
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
    keyboard.append([InlineKeyboardButton(
        text="Назад",
        callback_data=f"league_{league_key}",
        icon_custom_emoji_id="5258236805890710909"
    )])

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def my_subscriptions(update, user_id):
    await update_user_stats(update.from_user.id, update.from_user.first_name, update.from_user.username)

    cursor.execute("SELECT team FROM subscriptions WHERE user_id=?", (user_id,))
    subs = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT match_id FROM goal_subscriptions WHERE user_id=?", (user_id,))
    goal_subs = [row[0] for row in cursor.fetchall()]

    if not subs and not goal_subs:
        await update.message.reply_text(
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
    keyboard.append([InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_main",
        icon_custom_emoji_id="5258236805890710909"
    )])

    await update.message.reply_text(
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

    if data == "ucl_playoff":
        await ucl_playoff(query)
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

# ================== ФОРМАТИРОВАНИЕ СООБЩЕНИЙ О СОБЫТИЯХ ==================
def format_incident_message(incident, home_team, away_team):
    inc_type = incident["type"]
    player = incident.get("player", "Неизвестно")
    minute = incident.get("minute", "")
    team = incident.get("team", "")
    team_ru = translate_team(team)

    if inc_type == "goal":
        if incident.get("own_goal"):
            return f"<tg-emoji emoji-id='5375159220280762629'>⚽</tg-emoji> АВТОГОЛ!\n{player} ({team_ru})\nМинута: {minute}"
        elif incident.get("penalty"):
            return f"<tg-emoji emoji-id='5375159220280762629'>⚽</tg-emoji> ПЕНАЛЬТИ ЗАБИТ!\n{player} ({team_ru})\nМинута: {minute}"
        else:
            return f"<tg-emoji emoji-id='5375159220280762629'>⚽</tg-emoji> ГОЛ!\n{player} ({team_ru})\nМинута: {minute}"
    elif inc_type == "yellow_card":
        return f"🟨 ЖЕЛТАЯ КАРТОЧКА\n{player} ({team_ru})\nМинута: {minute}"
    elif inc_type == "red_card":
        return f"🟥 КРАСНАЯ КАРТОЧКА\n{player} ({team_ru})\nМинута: {minute}"
    elif inc_type == "second_yellow":
        return f"🟨🟨 ВТОРАЯ ЖЕЛТАЯ -> КРАСНАЯ\n{player} ({team_ru})\nМинута: {minute}"
    else:
        return None

# ================== ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ МАТЧЕЙ ==================
last_incidents = {}
notified_start = set()

async def match_checker(app):
    print("🔄 Запущен проверщик матчей (BSD с детальными событиями)")
    while True:
        try:
            matches = await fetch_live_matches_bsd()
            for match in matches:
                fixture_id = match["id"]
                home = match["home_team"]
                away = match["away_team"]
                incidents = match["incidents"]

                for inc in incidents:
                    inc_key = f"{fixture_id}_{inc['minute']}_{inc['type']}_{inc.get('player', '')}"
                    if inc_key not in last_incidents:
                        cursor.execute("SELECT user_id FROM goal_subscriptions WHERE match_id=?", (fixture_id,))
                        users = cursor.fetchall()
                        if users:
                            message_text = format_incident_message(inc, home, away)
                            if message_text:
                                for (user_id,) in users:
                                    try:
                                        await app.bot.send_message(
                                            chat_id=user_id,
                                            text=message_text,
                                            parse_mode=ParseMode.HTML
                                        )
                                    except Exception as e:
                                        print(f"Ошибка отправки уведомления: {e}")
                        last_incidents[inc_key] = True

                if match["status"] == "LIVE" and fixture_id not in notified_start:
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

        except Exception as e:
            print(f"Ошибка в match_checker: {e}")

        await asyncio.sleep(30)

# ================== СТАТИСТИКА (ТОЛЬКО ДЛЯ ВЛАДЕЛЬЦА) ==================
OWNER_ID = 123456789  # ⚠️ ЗАМЕНИТЕ НА СВОЙ USER ID

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
    print("✅ football-data.org для таблиц и расписания")
    print("✅ BSD для live‑матчей и событий")
    print("✅ API-FOOTBALL для Лиги чемпионов (автообновление)")
    print("✅ Кастомные эмодзи и улучшенный дизайн")
    print("=" * 60)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))

    loop = asyncio.get_event_loop()
    loop.create_task(match_checker(app))
    loop.create_task(ucl_updater())  # фоновая задача для ЛЧ

    print("🚀 Бот запущен! Откройте Telegram и отправьте /start")
    app.run_polling()

if __name__ == "__main__":
    main()
