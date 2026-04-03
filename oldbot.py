import asyncio
import sqlite3
from datetime import datetime, timedelta
import httpx
from cachetools import TTLCache
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
import telegram

print(f"🔍 Версия python-telegram-bot: {telegram.__version__}")

# ================== НАСТРОЙКИ ==================
TELEGRAM_TOKEN = ""7728656883:AAERNHyCW90kEVSZlyAe61EDrSigb98l1qE""
FOOTBALL_DATA_TOKEN = "ec0171bdf2db4f6baf095fb95ce0deb0"
OWNER_ID = 6298119477  # ⚠️ ЗАМЕНИТЕ НА СВОЙ USER ID

LEAGUES = {
    "apl": {"id": "PL", "name": "АПЛ", "logo": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "laliga": {"id": "PD", "name": "Ла Лига", "logo": "🇪🇸"},
    "bundesliga": {"id": "BL1", "name": "Бундеслига", "logo": "🇩🇪"},
    "seriea": {"id": "SA", "name": "Серия А", "logo": "🇮🇹"},
    "ucl": {"id": "CL", "name": "Лига Чемпионов", "logo": "🏆"}
}

# ================== ПРЕМИУМ-ЭМОДЗИ ==================
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

BALL_EMOJI_ID = "5375159220280762629"
BELL_EMOJI_ID = "5458603043203327669"
STAR_EMOJI_ID = "5438496463044752972"
HOME_EMOJI_ID = "5416041192905265756"
PLANE_EMOJI_ID = "5463424023734014980"

# Новые премиум-эмодзи (ваши ID)
STATS_EMOJI_ID = "5231200819986047254"      # 📊
TROPHY_EMOJI_ID = "5253894142982895846"     # 🏆
STAR_POINTS_EMOJI_ID = "6136464120779638846" # ⭐️
CHECK_EMOJI_ID = "5206607081334906820"       # ✅
CHART_EMOJI_ID = "5244837092042750681"       # 📈
FIRE_EMOJI_ID = "5424972470023104089"        # 🔥
IDEA_EMOJI_ID = "5193127592764394874"        # 💡
WARNING_EMOJI_ID = "5447644880824181073"     # ⚠️
ID_EMOJI_ID = "5841276284155467413"          # 🆔
MATCH_EMOJI_ID = "5391249739729616880"       # 📋
CRYSTAL_EMOJI_ID = "5361837567463399422"     # 🔮
DRAW_EMOJI_ID = "5357080225463149588"        # 🤝 ничья
AWAY_EMOJI_ID = "5361600266225326825"        # ✈️ победа гостей

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

TEAM_TRANSLATIONS = {
    "Real Madrid": "Реал Мадрид", "Elche": "Эльче", "West Ham United": "Вест Хэм",
    "Manchester City": "Манчестер Сити", "KVC Westerlo": "Вестерло", "Club Brugge KV": "Брюгге",
    "Kilmarnock": "Килмарнок", "Heart of Midlothian": "Хартс", "AFC Ajax": "Аякс",
    "Sparta Rotterdam": "Спарта Роттердам", "AS Monaco": "Монако", "Stade Brestois": "Брест",
    "Vitória": "Витория", "Atlético Mineiro": "Атлетико Минейро", "Galatasaray": "Галатасарай",
    "Liverpool": "Ливерпуль", "Atalanta": "Аталанта", "Bayern": "Бавария",
    "Atlético Madrid": "Атлетико Мадрид", "Tottenham": "Тоттенхэм", "Newcastle": "Ньюкасл",
    "Barcelona": "Барселона", "Bayer Leverkusen": "Байер", "Arsenal": "Арсенал",
    "Bodø/Glimt": "Будё-Глимт", "Sporting CP": "Спортинг", "PSG": "ПСЖ", "Chelsea": "Челси",
    "Manchester United": "Манчестер Юнайтед", "Internazionale": "Интер", "Juventus": "Ювентус",
    "Benfica": "Бенфика", "Borussia Dortmund": "Боруссия Д", "Club Brugge": "Брюгге",
    "Shakhtar Donetsk": "Шахтёр", "RB Leipzig": "РБ Лейпциг", "Porto": "Порту", "Ajax": "Аякс",
    "Rangers": "Рейнджерс", "Eintracht Frankfurt": "Айнтрахт", "Napoli": "Наполи",
    "Milan": "Милан", "Lazio": "Лацио", "Olympique Marseille": "Марсель", "Sporting Lisbon": "Спортинг",
}

def translate_team(name):
    return TEAM_TRANSLATIONS.get(name, name)

# ================== КЭШ ==================
cache = {
    'standings': TTLCache(maxsize=50, ttl=900),
    'matches': TTLCache(maxsize=100, ttl=300),
    'live': TTLCache(maxsize=20, ttl=30),
}

UTC_TZ = pytz.UTC
MSK_TZ = pytz.timezone('Europe/Moscow')

def utc_to_msk(utc_time_str):
    try:
        if utc_time_str.endswith('Z'):
            utc_time_str = utc_time_str[:-1] + '+00:00'
        utc_dt = datetime.fromisoformat(utc_time_str)
        if utc_dt.tzinfo is None:
            utc_dt = UTC_TZ.localize(utc_dt)
        return utc_dt.astimezone(MSK_TZ)
    except Exception as e:
        print(f"Ошибка преобразования времени: {e}")
        return None

# ================== БАЗА ДАННЫХ ==================
conn = sqlite3.connect("football_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id INTEGER, team TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS goal_subscriptions (user_id INTEGER, match_id INTEGER, PRIMARY KEY (user_id, match_id))")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, display_name TEXT, first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, commands_count INTEGER DEFAULT 0)")

cursor.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT,
    match_name TEXT NOT NULL,
    match_time TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_predictions (
    user_id INTEGER,
    prediction_id INTEGER,
    prediction_result TEXT,
    is_correct BOOLEAN DEFAULT 0,
    points_earned INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, prediction_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER PRIMARY KEY,
    total_points INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    total_predictions INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    max_streak INTEGER DEFAULT 0,
    last_prediction_correct BOOLEAN DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS monthly_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    month_year TEXT,
    total_points INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    total_predictions INTEGER DEFAULT 0,
    rank INTEGER,
    UNIQUE(user_id, month_year)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS monthly_winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_year TEXT UNIQUE,
    winner_id INTEGER,
    winner_name TEXT,
    points INTEGER,
    announced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ================== ХРАНИЛИЩЕ ID ПОСЛЕДНИХ СООБЩЕНИЙ ==================
last_message_ids = {}

async def delete_previous_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    if chat_id in last_message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_message_ids[chat_id])
        except Exception as e:
            print(f"Ошибка удаления: {e}")

async def auto_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 10):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Ошибка автоудаления: {e}")

# ================== ФУНКЦИИ API ==================
async def fetch_matches(competition_id, date_from, date_to):
    cache_key = f"matches_{competition_id}_{date_from}_{date_to}"
    if cache_key in cache['matches']:
        return cache['matches'][cache_key]
    url = "https://api.football-data.org/v4/matches"
    params = {"competitions": competition_id, "dateFrom": date_from, "dateTo": date_to}
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("matches", [])
                cache['matches'][cache_key] = matches
                return matches
            return []
    except Exception as e:
        print(f"❌ Ошибка матчей: {e}")
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
            return []
    except Exception as e:
        print(f"❌ Ошибка standings: {e}")
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
            return []
    except Exception as e:
        print(f"❌ Ошибка live: {e}")
        return []

# ================== СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ ==================
async def update_user_stats(user_id, first_name=None, username=None):
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP, commands_count = commands_count + 1 WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("INSERT INTO users (user_id, first_name, username, commands_count) VALUES (?, ?, ?, 1)", (user_id, first_name, username))
    conn.commit()

# ================== БАЛЛЫ И СЕРИИ ==================
async def update_user_points(user_id, base_points, is_correct):
    cursor.execute("SELECT current_streak, total_points, correct_predictions, total_predictions, max_streak FROM user_stats WHERE user_id = ?", (user_id,))
    stats = cursor.fetchone()
    if not stats:
        if is_correct:
            cursor.execute("INSERT INTO user_stats (user_id, total_points, correct_predictions, total_predictions, current_streak, max_streak, last_prediction_correct) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (user_id, base_points, 1, 1, 1, 1, 1))
        else:
            cursor.execute("INSERT INTO user_stats (user_id, total_points, total_predictions, last_prediction_correct) VALUES (?, ?, ?, ?)",
                          (user_id, 0, 1, 0))
        conn.commit()
        return
    current_streak, total_points, correct, total, max_streak = stats
    total += 1
    if is_correct:
        new_streak = current_streak + 1
        bonus = 0
        if new_streak >= 12: bonus = 4
        elif new_streak >= 7: bonus = 2
        elif new_streak >= 3: bonus = 1
        points_to_add = base_points + bonus
        total_points += points_to_add
        correct += 1
        if new_streak > max_streak:
            max_streak = new_streak
        cursor.execute("UPDATE user_stats SET total_points = ?, correct_predictions = ?, total_predictions = ?, current_streak = ?, max_streak = ?, last_prediction_correct = 1 WHERE user_id = ?",
                      (total_points, correct, total, new_streak, max_streak, user_id))
    else:
        cursor.execute("UPDATE user_stats SET total_predictions = ?, current_streak = 0, last_prediction_correct = 0 WHERE user_id = ?",
                      (total, user_id))
    conn.commit()

# ================== МЕНЮ ==================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 АПЛ", callback_data="league_apl"), InlineKeyboardButton("🇪🇸 Ла Лига", callback_data="league_laliga")],
        [InlineKeyboardButton("🇩🇪 Бундеслига", callback_data="league_bundesliga"), InlineKeyboardButton("🇮🇹 Серия А", callback_data="league_seriea")],
        [InlineKeyboardButton("🏆 Лига Чемпионов", callback_data="league_ucl")],
        [InlineKeyboardButton("🔴 LIVE матчи", callback_data="live")],
        [InlineKeyboardButton("⚽ Голы и карточки LIVE", callback_data="goal_live")],
        [InlineKeyboardButton("⭐ Мои подписки", callback_data="my_subs")],
        [InlineKeyboardButton("🔮 Прогнозы", callback_data="predictions"), InlineKeyboardButton("🏆 Общий рейтинг", callback_data="leaderboard")],
        [InlineKeyboardButton("📅 Рейтинг за месяц", callback_data="monthly"), InlineKeyboardButton("🏆 История победителей", callback_data="winners")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton("📩 Предложение / реклама", callback_data="feedback")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
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
    try:
        await update.message.delete()
    except:
        pass
    photo_url = "https://i.postimg.cc/RVfDJvGC/START.jpg"
    caption = (f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji> <b>Футбольный бот PRO</b>\n\n'
               f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji> LIVE-матчи\n'
               f'<tg-emoji emoji-id="{BELL_EMOJI_ID}">🔔</tg-emoji> Голы и карточки LIVE\n'
               f'<tg-emoji emoji-id="{STAR_EMOJI_ID}">⭐</tg-emoji> Подписки на команды\n\n'
               f'<i>👇 Выберите лигу в меню ниже:</i>')
    sent = await update.message.reply_photo(photo=photo_url, caption=caption, parse_mode=ParseMode.HTML, reply_markup=main_menu())
    last_message_ids[chat_id] = sent.message_id
    asyncio.create_task(auto_delete_message(context, chat_id, sent.message_id, 60))

# ================== МАТЧИ 48 ЧАСОВ ==================
async def matches_next_48h(query: CallbackQuery, league_key: str, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    league = LEAGUES[league_key]
    now_msk = datetime.now(MSK_TZ)
    date_from = now_msk.strftime("%Y-%m-%d")
    date_to = (now_msk + timedelta(hours=48)).strftime("%Y-%m-%d")
    msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Загружаю матчи {league['name']}...")
    matches = await fetch_matches(league["id"], date_from, date_to)
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not matches:
        await msg.edit_text(f"📅 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет матчей</i>", parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        return
    time_from_str = now_msk.strftime("%d.%m.%Y %H:%M")
    time_to_str = (now_msk + timedelta(hours=48)).strftime("%d.%m.%Y %H:%M")
    text = f"{league['logo']} <b>МАТЧИ {league['name']}</b>\n<i>{time_from_str} – {time_to_str} (МСК)</i>\n\n"
    for match in matches:
        msk_time = utc_to_msk(match["utcDate"])
        if msk_time:
            time_str, date_str = msk_time.strftime("%H:%M"), msk_time.strftime("%d.%m")
        else:
            time_str = date_str = "??:??"
        home, away = match["homeTeam"]["name"], match["awayTeam"]["name"]
        status = match["status"]
        if status == "FINISHED":
            score_h, score_a = match["score"]["fullTime"]["home"] or 0, match["score"]["fullTime"]["away"] or 0
            text += f"✅ {date_str} {time_str}  <b>{home}</b> {score_h}-{score_a} <b>{away}</b>\n"
        elif status in ["IN_PLAY", "PAUSED"]:
            text += f"🔴 {date_str} {time_str}  <b>{home}</b> vs <b>{away}</b> (в игре)\n"
        else:
            text += f"⏳ {date_str} {time_str}  <b>{home}</b> vs <b>{away}</b>\n"
    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

# ================== ТАБЛИЦА ==================
async def show_table(query: CallbackQuery, league_key: str, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    league = LEAGUES[league_key]
    msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Загружаю таблицу {league['name']}...")
    table = await fetch_standings(league["id"])
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not table:
        await msg.edit_text(f"📊 <b>{league['logo']} {league['name']}</b>\n\n<i>Нет данных</i>", parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        return
    text = f"{league['logo']} <b>ТАБЛИЦА {league['name']}</b>\n\n"
    for row in table[:9]:
        pos, team, pts, played, won, draw, lost = row["position"], row["team"]["name"], row["points"], row["playedGames"], row["won"], row["draw"], row["lost"]
        if pos in DIGIT_EMOJIS:
            text += f'<tg-emoji emoji-id="{DIGIT_EMOJIS[pos]}">{pos}</tg-emoji> <b>{team}</b>\n'
        else:
            text += f"<b>{pos}.</b> {team}\n"
        text += f"   {pts} очков | И:{played} В:{won} Н:{draw} П:{lost}\n\n"
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    except:
        import re
        await msg.edit_text(re.sub(r'<[^>]+>', '', text), reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

# ================== LIVE МАТЧИ ==================
async def live_matches(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Загружаю LIVE матчи...")
    matches = await fetch_live_matches()
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not matches:
        await msg.edit_text("🔴 <b>LIVE матчи</b>\n\n<i>Сейчас нет матчей</i>", parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        return
    text = "🔴 <b>LIVE МАТЧИ</b>\n\n"
    for match in matches:
        league_name = match.get("competition", {}).get("name", "Неизвестная лига")
        home, away = match["homeTeam"]["name"], match["awayTeam"]["name"]
        status = match["status"]
        score_h = match["score"]["fullTime"]["home"] or match["score"]["halfTime"]["home"] or 0
        score_a = match["score"]["fullTime"]["away"] or match["score"]["halfTime"]["away"] or 0
        minute = match.get("minute", "")
        if not minute and "IN_PLAY" in status:
            minute = "идет"
        elif status == "PAUSED":
            minute = "перерыв"
        home_ru, away_ru = translate_team(home), translate_team(away)
        ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
        text += f"{ball_emoji} <b>{home_ru}</b> {score_h}–{score_a} <b>{away_ru}</b>"
        if minute:
            text += f"  ({minute})"
        text += f"\n   <i>{league_name}</i>\n\n"
    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

# ================== ПОДПИСКИ ==================
async def show_league_teams(query: CallbackQuery, league_key: str, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    await update_user_stats(user.id, user.first_name, user.username)
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    league = LEAGUES[league_key]
    msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Загружаю команды {league['name']}...")
    table = await fetch_standings(league["id"])
    if not table:
        await msg.edit_text(f"❌ Не удалось загрузить команды", reply_markup=main_menu())
        return
    teams = [row["team"]["name"] for row in table]
    text = f"{league['logo']} <b>Команды {league['name']}</b>\n\n"
    keyboard = []
    for i in range(0, len(teams), 2):
        row = [InlineKeyboardButton(teams[i], callback_data=f"sub_team_{teams[i]}")]
        if i+1 < len(teams):
            row.append(InlineKeyboardButton(teams[i+1], callback_data=f"sub_team_{teams[i+1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"league_{league_key}")])
    await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    try:
        await query.message.delete()
    except:
        pass

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

async def my_subscriptions(query: CallbackQuery, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    await update_user_stats(query.from_user.id, query.from_user.first_name, query.from_user.username)
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    cursor.execute("SELECT team FROM subscriptions WHERE user_id=?", (user_id,))
    subs = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT match_id FROM goal_subscriptions WHERE user_id=?", (user_id,))
    goal_subs = [row[0] for row in cursor.fetchall()]
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not subs and not goal_subs:
        await context.bot.send_message(chat_id=chat_id, text="⭐ <b>У вас нет подписок</b>", parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        return
    star_emoji = f'<tg-emoji emoji-id="{STAR_EMOJI_ID}">⭐</tg-emoji>'
    text = f"{star_emoji} <b>МОИ ПОДПИСКИ</b>\n\n"
    if subs:
        text += "<b>Команды:</b>\n" + "\n".join([f"   {star_emoji} {team}" for team in subs]) + "\n\n"
    if goal_subs:
        bell_emoji = f'<tg-emoji emoji-id="{BELL_EMOJI_ID}">🔔</tg-emoji>'
        text += f"{bell_emoji} <b>Матчи:</b>\n" + "\n".join([f"   • ID матча: {mid}" for mid in goal_subs]) + "\n\n"
    keyboard = [[InlineKeyboardButton(f"❌ Отписаться от команды {team}", callback_data=f"unsub_team_{team}")] for team in subs]
    keyboard += [[InlineKeyboardButton(f"❌ Отписаться от матча {mid}", callback_data=f"goal_unsub_{mid}")] for mid in goal_subs]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    try:
        await query.message.delete()
    except:
        pass

# ================== ПРОГНОЗЫ И РЕЙТИНГИ ==================
async def show_active_predictions(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    cursor.execute("SELECT id, match_name, match_time FROM predictions WHERE status = 'active' ORDER BY match_time ASC")
    predictions = cursor.fetchall()
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not predictions:
        await context.bot.send_message(chat_id=chat_id, text="🔮 Активных прогнозов пока нет", reply_markup=back_keyboard)
        try:
            await query.message.delete()
        except:
            pass
        return
    text = (f'<tg-emoji emoji-id="{CRYSTAL_EMOJI_ID}">🔮</tg-emoji> <b>ДОСТУПНЫЕ ПРОГНОЗЫ</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n\n')
    for pred_id, match_name, match_time in predictions:
        text += (f'<tg-emoji emoji-id="{ID_EMOJI_ID}">🆔</tg-emoji> ID: <code>{pred_id}</code>\n'
                 f'<tg-emoji emoji-id="{MATCH_EMOJI_ID}">📋</tg-emoji> {match_name}\n')
        if match_time:
            text += f'🕐 {match_time}\n'
        text += "\n"
    text += "💡 <b>Как сделать прогноз:</b>\n"
    text += "<code>/predict ID_матча home</code> — победа хозяев\n"
    text += "<code>/predict ID_матча draw</code> — ничья\n"
    text += "<code>/predict ID_матча away</code> — победа гостей\n"
    text += "Пример: <code>/predict 5 home</code>"
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

async def make_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    try:
        await message.delete()
    except:
        pass
    args = context.args
    if len(args) < 2:
        await message.reply_text("❌ Использование: /predict <prediction_id> <home/draw/away>")
        return
    prediction_id, user_choice = args[0], args[1].lower()
    if user_choice not in ['home', 'draw', 'away']:
        await message.reply_text("❌ Выберите: home, draw или away")
        return
    cursor.execute("SELECT status FROM predictions WHERE id = ?", (prediction_id,))
    pred = cursor.fetchone()
    if not pred:
        await message.reply_text("❌ Прогноз не найден")
        return
    if pred[0] != 'active':
        await message.reply_text("❌ Приём прогнозов закрыт")
        return
    cursor.execute("SELECT 1 FROM user_predictions WHERE user_id = ? AND prediction_id = ?", (user.id, prediction_id))
    if cursor.fetchone():
        await message.reply_text("❌ Вы уже сделали прогноз")
        return
    cursor.execute("INSERT INTO user_predictions (user_id, prediction_id, prediction_result) VALUES (?, ?, ?)", (user.id, prediction_id, user_choice))
    cursor.execute("UPDATE user_stats SET total_predictions = total_predictions + 1 WHERE user_id = ?", (user.id,))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO user_stats (user_id, total_predictions) VALUES (?, 1)", (user.id,))
    conn.commit()
    choice_text = {"home": "победу хозяев", "draw": "ничью", "away": "победу гостей"}
    sent = await message.reply_text(f"✅ Прогноз принят!\nВы выбрали: {choice_text[user_choice]}\nЖдите результата!")
    asyncio.create_task(auto_delete_message(context, message.chat_id, sent.message_id, 10))

async def show_leaderboard(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    cursor.execute("""
        SELECT COALESCE(u.display_name, u.first_name) as name, s.total_points, s.correct_predictions, s.total_predictions, s.current_streak, s.max_streak
        FROM user_stats s JOIN users u ON u.user_id = s.user_id
        ORDER BY s.total_points DESC LIMIT 10
    """)
    leaders = cursor.fetchall()
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not leaders:
        await context.bot.send_message(chat_id=chat_id, text="📊 Таблица лидеров пока пуста", reply_markup=back_keyboard)
        try:
            await query.message.delete()
        except:
            pass
        return
    text = (f'<tg-emoji emoji-id="{TROPHY_EMOJI_ID}">🏆</tg-emoji> <b>ТАБЛИЦА ЛИДЕРОВ</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n\n')
    for i, (name, points, correct, total, streak, max_streak) in enumerate(leaders, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        accuracy = (correct / total * 100) if total > 0 else 0
        text += (f"{medal} <b>{name}</b>\n"
                 f'   <tg-emoji emoji-id="{STAR_POINTS_EMOJI_ID}">⭐️</tg-emoji> {points} очков | <tg-emoji emoji-id="{CHECK_EMOJI_ID}">✅</tg-emoji> {correct}/{total} ({accuracy:.0f}%)\n'
                 f'   <tg-emoji emoji-id="{FIRE_EMOJI_ID}">🔥</tg-emoji> Серия: {streak} | <tg-emoji emoji-id="{TROPHY_EMOJI_ID}">🏆</tg-emoji> Рекорд: {max_streak}\n\n')
    text += (f'━━━━━━━━━━━━━━━━━━━━━━\n'
             f'<tg-emoji emoji-id="{IDEA_EMOJI_ID}">💡</tg-emoji> Бонусы за серию: 3+ → +1 | 7+ → +2 | 12+ → +4')
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

async def monthly_leaderboard(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    current_month = datetime.now(MSK_TZ).strftime("%Y-%m")
    cursor.execute("""
        SELECT COALESCE(u.display_name, u.first_name) as name, 
               COALESCE(SUM(up.points_earned), 0) as points,
               COUNT(CASE WHEN up.is_correct = 1 THEN 1 END) as correct, 
               COUNT(up.user_id) as total
        FROM users u 
        LEFT JOIN user_predictions up ON u.user_id = up.user_id
        LEFT JOIN predictions p ON up.prediction_id = p.id
        WHERE strftime('%Y-%m', p.closed_at) = ? OR p.closed_at IS NULL
        GROUP BY u.user_id 
        HAVING points > 0 
        ORDER BY points DESC 
        LIMIT 10
    """, (current_month,))
    leaders = cursor.fetchall()
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not leaders:
        await context.bot.send_message(chat_id=chat_id, text=f"📅 Ежемесячный рейтинг за {current_month} пока пуст", reply_markup=back_keyboard)
        try:
            await query.message.delete()
        except:
            pass
        return
    text = (f'<tg-emoji emoji-id="{STATS_EMOJI_ID}">📅</tg-emoji> <b>ЕЖЕМЕСЯЧНЫЙ РЕЙТИНГ</b> — {current_month}\n'
            f'<tg-emoji emoji-id="{TROPHY_EMOJI_ID}">🏆</tg-emoji> Победитель получит подарок!\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n\n')
    for i, (name, points, correct, total) in enumerate(leaders, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        accuracy = (correct / total * 100) if total > 0 else 0
        text += (f"{medal} <b>{name}</b>\n"
                 f'   <tg-emoji emoji-id="{STAR_POINTS_EMOJI_ID}">⭐️</tg-emoji> {points} очков | <tg-emoji emoji-id="{CHECK_EMOJI_ID}">✅</tg-emoji> {correct}/{total} ({accuracy:.0f}%)\n\n')
    text += (f'━━━━━━━━━━━━━━━━━━━━━━\n'
             f'<tg-emoji emoji-id="{IDEA_EMOJI_ID}">🎁</tg-emoji> Победитель месяца получает подарок!')
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

async def winners_history(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    cursor.execute("SELECT month_year, winner_name, points FROM monthly_winners ORDER BY month_year DESC LIMIT 6")
    winners = cursor.fetchall()
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not winners:
        await context.bot.send_message(chat_id=chat_id, text="🏆 История победителей пока пуста", reply_markup=back_keyboard)
        try:
            await query.message.delete()
        except:
            pass
        return
    text = (f'<tg-emoji emoji-id="{TROPHY_EMOJI_ID}">🏆</tg-emoji> <b>ИСТОРИЯ ПОБЕДИТЕЛЕЙ</b>\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n\n')
    for month, name, points in winners:
        text += f"📅 {month}\n   👑 <b>{name}</b> — {points} очков\n\n"
    text += f'<tg-emoji emoji-id="{IDEA_EMOJI_ID}">🎁</tg-emoji> Следующий победитель получит подарок!'
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

async def my_stats(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    user = query.from_user
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    cursor.execute("SELECT COALESCE(display_name, first_name) FROM users WHERE user_id = ?", (user.id,))
    result = cursor.fetchone()
    user_name = result[0] if result else user.first_name
    cursor.execute("SELECT total_points, correct_predictions, total_predictions, current_streak, max_streak FROM user_stats WHERE user_id = ?", (user.id,))
    stats = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) + 1 FROM user_stats WHERE total_points > (SELECT COALESCE(total_points, 0) FROM user_stats WHERE user_id = ?)", (user.id,))
    rank_result = cursor.fetchone()
    rank = rank_result[0] if rank_result else 1
    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
    if not stats:
        await context.bot.send_message(chat_id=chat_id,
            text=(f'<tg-emoji emoji-id="{STATS_EMOJI_ID}">📊</tg-emoji> <b>СТАТИСТИКА</b> — {user_name}\n\n'
                  f'Пока нет данных.\nСделайте первый прогноз: /predict'),
            parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        try:
            await query.message.delete()
        except:
            pass
        return
    total_points, correct, total, streak, max_streak = stats
    accuracy = (correct / total * 100) if total > 0 else 0
    next_bonus = ""
    if streak < 3: next_bonus = f"До бонуса +1 осталось {3 - streak} правильных"
    elif streak < 7: next_bonus = f"До бонуса +2 осталось {7 - streak} правильных"
    elif streak < 12: next_bonus = f"До бонуса +4 осталось {12 - streak} правильных"
    else: next_bonus = "Вы получаете максимальный бонус +4!"
    text = (f'<tg-emoji emoji-id="{STATS_EMOJI_ID}">📊</tg-emoji> <b>СТАТИСТИКА</b> — {user_name}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'<tg-emoji emoji-id="{TROPHY_EMOJI_ID}">🏆</tg-emoji> Место: <b>{rank}</b>\n'
            f'<tg-emoji emoji-id="{STAR_POINTS_EMOJI_ID}">⭐️</tg-emoji> Очков: <b>{total_points}</b>\n\n'
            f'<tg-emoji emoji-id="{CHECK_EMOJI_ID}">✅</tg-emoji> Правильных: <b>{correct}/{total}</b>\n'
            f'<tg-emoji emoji-id="{CHART_EMOJI_ID}">📈</tg-emoji> Точность: <b>{accuracy:.1f}%</b>\n\n'
            f'<tg-emoji emoji-id="{FIRE_EMOJI_ID}">🔥</tg-emoji> Текущая серия: <b>{streak}</b>\n'
            f'<tg-emoji emoji-id="{TROPHY_EMOJI_ID}">🏆</tg-emoji> Рекорд: <b>{max_streak}</b>\n\n'
            f'<tg-emoji emoji-id="{IDEA_EMOJI_ID}">💡</tg-emoji> <b>Следующий бонус:</b>\n{next_bonus}\n\n'
            f'<tg-emoji emoji-id="{WARNING_EMOJI_ID}">⚠️</tg-emoji> При ошибке серия сбрасывается, очки сохраняются!')
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    try:
        await query.message.delete()
    except:
        pass

async def set_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    try:
        await message.delete()
    except:
        pass
    args = context.args
    if not args:
        await message.reply_text("❌ Использование: /setnick <ник>\nПример: /setnick FanRealMadrid")
        return
    import re
    nickname = args[0][:20]
    if not re.match(r'^[a-zA-Z0-9_а-яА-Я]+$', nickname):
        await message.reply_text("❌ Ник может содержать только буквы, цифры и _")
        return
    cursor.execute("UPDATE users SET display_name = ? WHERE user_id = ?", (nickname, user.id))
    conn.commit()
    sent = await message.reply_text(f"✅ Ваш ник: {nickname}")
    asyncio.create_task(auto_delete_message(context, message.chat_id, sent.message_id, 10))

# ================== АДМИН-КОМАНДЫ ==================
async def admin_add_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    try:
        await update.message.delete()
    except:
        pass
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /addprediction <match_id> <название матча>\nПример: /addprediction 123 Реал Мадрид vs Барселона")
        return
    match_id = args[0]
    match_name = " ".join(args[1:])
    cursor.execute("INSERT INTO predictions (match_id, match_name) VALUES (?, ?)", (match_id, match_name))
    conn.commit()
    await update.message.reply_text(f"✅ Прогноз добавлен!\nID: {cursor.lastrowid}\nМатч: {match_name}")

async def admin_close_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    try:
        await update.message.delete()
    except:
        pass
    args = context.args
    if not args:
        cursor.execute("SELECT id, match_name FROM predictions WHERE status = 'active'")
        active = cursor.fetchall()
        if not active:
            await update.message.reply_text("Нет активных прогнозов")
            return
        text = "Активные прогнозы:\n" + "\n".join([f"ID: {p[0]} — {p[1]}" for p in active])
        text += "\n\n/closeprediction <ID>"
        await update.message.reply_text(text)
        return
    cursor.execute("UPDATE predictions SET status = 'closed', closed_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'active'", (args[0],))
    conn.commit()
    await update.message.reply_text(f"✅ Прогноз #{args[0]} закрыт" if cursor.rowcount > 0 else "❌ Не найден")

async def admin_finish_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    try:
        await update.message.delete()
    except:
        pass
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ /finishprediction <ID> <home/draw/away>\nПример: /finishprediction 5 home")
        return
    prediction_id, result = args[0], args[1].lower()
    if result not in ['home', 'draw', 'away']:
        await update.message.reply_text("❌ Результат должен быть: home, draw или away")
        return
    cursor.execute("SELECT match_name FROM predictions WHERE id = ? AND status = 'closed'", (prediction_id,))
    pred = cursor.fetchone()
    if not pred:
        await update.message.reply_text("❌ Прогноз не найден или не закрыт")
        return
    cursor.execute("SELECT user_id, prediction_result FROM user_predictions WHERE prediction_id = ?", (prediction_id,))
    predictions = cursor.fetchall()
    if not predictions:
        await update.message.reply_text("⚠️ На этот прогноз никто не сделал ставок")
        cursor.execute("UPDATE predictions SET status = 'finished' WHERE id = ?", (prediction_id,))
        conn.commit()
        return
    correct_users = []
    wrong_users = []
    for uid, pr in predictions:
        is_correct = 1 if pr == result else 0
        cursor.execute("UPDATE user_predictions SET is_correct = ?, points_earned = 1 WHERE user_id = ? AND prediction_id = ?", (is_correct, uid, prediction_id))
        if is_correct:
            correct_users.append(uid)
        else:
            wrong_users.append(uid)
    cursor.execute("UPDATE predictions SET status = 'finished' WHERE id = ?", (prediction_id,))
    conn.commit()
    for uid in correct_users:
        await update_user_points(uid, 1, True)
    for uid in wrong_users:
        await update_user_points(uid, 0, False)
    # Формируем результат с премиум-эмодзи
    if result == "home":
        result_emoji = f'<tg-emoji emoji-id="{HOME_EMOJI_ID}">🏠</tg-emoji>'
        result_text = f"{result_emoji} победа хозяев"
    elif result == "draw":
        result_emoji = f'<tg-emoji emoji-id="{DRAW_EMOJI_ID}">🤝</tg-emoji>'
        result_text = f"{result_emoji} ничья"
    else:
        result_emoji = f'<tg-emoji emoji-id="{AWAY_EMOJI_ID}">✈️</tg-emoji>'
        result_text = f"{result_emoji} победа гостей"
    # Отправляем уведомления участникам
    for uid, pr in predictions:
        is_correct = (pr == result)
        if is_correct:
            text = (f"✅ <b>Ваш прогноз оказался верным!</b>\n\n"
                    f"📋 Матч: {pred[0]}\n"
                    f"🏆 Результат: {result_text}\n"
                    f"⭐ Вы получили 1 балл + бонусы за серию.\n"
                    f"📊 Проверьте свою статистику: /mystats")
        else:
            text = (f"❌ <b>Ваш прогноз не оправдался.</b>\n\n"
                    f"📋 Матч: {pred[0]}\n"
                    f"🏆 Результат: {result_text}\n"
                    f"⚠️ Ваша серия прервана, но очки сохранены.\n"
                    f"📊 Статистика: /mystats")
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"Не удалось отправить уведомление {uid}: {e}")
    await update.message.reply_text(
        f"✅ Прогноз завершён!\n"
        f"📋 Матч: {pred[0]}\n"
        f"🏆 Результат: {result_text}\n"
        f"✅ Правильных: {len(correct_users)}/{len(predictions)}\n"
        f"📨 Уведомления отправлены всем участникам."
    )

async def admin_all_predictions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    try:
        await update.message.delete()
    except:
        pass
    cursor.execute("SELECT id, match_name, status, created_at FROM predictions ORDER BY created_at DESC")
    preds = cursor.fetchall()
    if not preds:
        await update.message.reply_text("Нет прогнозов")
        return
    text = "📊 ВСЕ ПРОГНОЗЫ\n\n"
    for p in preds:
        status_emoji = "🟢" if p[2] == "active" else "🟡" if p[2] == "closed" else "⚫"
        text += f"{status_emoji} ID:{p[0]} | {p[1]} | {p[2]}\n"
    await update.message.reply_text(text)

# ================== ОБРАТНАЯ СВЯЗЬ ==================
FEEDBACK_TEXT = 0

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await delete_previous_message(chat_id, context)
    sent = await context.bot.send_message(chat_id=chat_id, text="✍️ Напишите ваше предложение или рекламный запрос.\n\n(Чтобы отменить, отправьте /cancel)")
    last_message_ids[chat_id] = sent.message_id
    try:
        await query.message.delete()
    except:
        pass
    return FEEDBACK_TEXT

async def feedback_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    text = message.text.strip()
    if not text:
        await message.reply_text("Пожалуйста, напишите текст.")
        return FEEDBACK_TEXT
    admin_text = f"📩 <b>Новое сообщение от пользователя</b>\n👤 {user.full_name} (@{user.username or 'нет'})\n🆔 {user.id}\n\n✍️ {text}"
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=admin_text, parse_mode=ParseMode.HTML)
        await message.reply_text("✅ Спасибо! Сообщение отправлено администратору.", reply_markup=main_menu())
    except Exception as e:
        await message.reply_text("❌ Не удалось отправить.", reply_markup=main_menu())
        print(f"Ошибка обратной связи: {e}")
    try:
        await message.delete()
    except:
        pass
    return ConversationHandler.END

async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=main_menu())
    return ConversationHandler.END

# ================== РАССЫЛКА ==================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    text = update.message.text.replace("/broadcast", "").strip()
    if not text:
        await update.message.reply_text("❌ /broadcast <текст>")
        return
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    if not users:
        await update.message.reply_text("Нет пользователей")
        return
    sent, failed = 0, 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await update.message.reply_text(f"✅ Рассылка: отправлено {sent}, неудач {failed}")

# ================== СТАТИСТИКА ДЛЯ АДМИНА ==================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
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
    cursor.execute("SELECT COUNT(*) FROM user_predictions WHERE is_correct = 1")
    total_correct = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_predictions")
    total_predictions = cursor.fetchone()[0]
    accuracy = (total_correct / total_predictions * 100) if total_predictions > 0 else 0
    text = (f"📊 <b>РАСШИРЕННАЯ СТАТИСТИКА БОТА</b>\n\n"
            f"👥 <b>Пользователи:</b>\n   • Всего: {total_users}\n   • Активных сегодня: {today_active}\n"
            f"   • За неделю: {week_active}\n   • За месяц: {month_active}\n\n"
            f"⚽ <b>Прогнозы:</b>\n   • Всего: {total_predictions}\n   • Правильных: {total_correct}\n"
            f"   • Точность: {accuracy:.1f}%\n\n"
            f"🏆 <b>Топ команд по подпискам:</b>\n{teams_text}\n\n"
            f"🔥 <b>Топ активных пользователей:</b>\n{users_text}")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== ФОНОВАЯ ЗАДАЧА ==================
last_scores = {}
notified_start = set()

async def match_checker(app):
    print("🔄 Запущен проверщик матчей")
    while True:
        try:
            matches = await fetch_live_matches()
            for match in matches:
                fixture_id = match["id"]
                home, away = match["homeTeam"]["name"], match["awayTeam"]["name"]
                status = match["status"]
                hs = match["score"]["fullTime"]["home"] or match["score"]["halfTime"]["home"] or 0
                aw = match["score"]["fullTime"]["away"] or match["score"]["halfTime"]["away"] or 0
                score = f"{hs}-{aw}"
                if status in ["IN_PLAY", "LIVE"] and fixture_id not in notified_start:
                    ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
                    cursor.execute("SELECT user_id FROM goal_subscriptions WHERE match_id=?", (fixture_id,))
                    for (uid,) in cursor.fetchall():
                        try:
                            await app.bot.send_message(chat_id=uid, text=f"{ball_emoji} <b>Матч начался!</b>\n\n{home} vs {away}", parse_mode=ParseMode.HTML)
                        except: pass
                    cursor.execute("SELECT user_id FROM subscriptions WHERE team=?", (home,))
                    users_home = cursor.fetchall()
                    cursor.execute("SELECT user_id FROM subscriptions WHERE team=?", (away,))
                    users_away = cursor.fetchall()
                    for (uid,) in set(users_home + users_away):
                        try:
                            await app.bot.send_message(chat_id=uid, text=f"{ball_emoji} <b>Матч начался!</b>\n\n{home} vs {away}", parse_mode=ParseMode.HTML)
                        except: pass
                    notified_start.add(fixture_id)
                if fixture_id not in last_scores:
                    last_scores[fixture_id] = score
                elif last_scores[fixture_id] != score:
                    ball_emoji = f'<tg-emoji emoji-id="{BALL_EMOJI_ID}">⚽</tg-emoji>'
                    cursor.execute("SELECT user_id FROM goal_subscriptions WHERE match_id=?", (fixture_id,))
                    for (uid,) in cursor.fetchall():
                        try:
                            await app.bot.send_message(chat_id=uid, text=f"{ball_emoji} <b>ГОЛ!</b>\n\n{home} {hs}-{aw} {away}", parse_mode=ParseMode.HTML)
                        except: pass
                    cursor.execute("SELECT user_id FROM subscriptions WHERE team=?", (home,))
                    users_home = cursor.fetchall()
                    cursor.execute("SELECT user_id FROM subscriptions WHERE team=?", (away,))
                    users_away = cursor.fetchall()
                    for (uid,) in set(users_home + users_away):
                        try:
                            await app.bot.send_message(chat_id=uid, text=f"{ball_emoji} <b>ГОЛ!</b>\n\n{home} {hs}-{aw} {away}", parse_mode=ParseMode.HTML)
                        except: pass
                    last_scores[fixture_id] = score
        except Exception as e:
            print(f"Ошибка в match_checker: {e}")
        await asyncio.sleep(30)

# ================== ОБРАБОТЧИК КНОПОК ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    await update_user_stats(user_id, query.from_user.first_name, query.from_user.username)
    if data == "back_to_main":
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await context.bot.send_message(chat_id=chat_id, text="<b>Выберите лигу:</b>", parse_mode=ParseMode.HTML, reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return
    if data.startswith("league_"):
        league_key = data.replace("league_", "")
        league = LEAGUES[league_key]
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await context.bot.send_message(chat_id=chat_id, text=f"{league['logo']} <b>{league['name']}</b>", parse_mode=ParseMode.HTML, reply_markup=league_menu(league_key))
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return
    if data.startswith("matches_"):
        await matches_next_48h(query, data.replace("matches_", ""), context)
        return
    if data.startswith("table_"):
        await show_table(query, data.replace("table_", ""), context)
        return
    if data.startswith("teams_"):
        await show_league_teams(query, data.replace("teams_", ""), context)
        return
    if data == "ucl_playoff":
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await context.bot.send_message(chat_id=chat_id, text="🏆 Лига Чемпионов — данные обновляются...", reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return
    if data == "live":
        await live_matches(query, context)
        return
    if data == "goal_live":
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await context.bot.send_message(chat_id=chat_id, text="⚽ Функция в разработке", reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return
    if data == "my_subs":
        await my_subscriptions(query, user_id, context)
        return
    if data == "predictions":
        await show_active_predictions(query, context)
        return
    if data == "leaderboard":
        await show_leaderboard(query, context)
        return
    if data == "monthly":
        await monthly_leaderboard(query, context)
        return
    if data == "winners":
        await winners_history(query, context)
        return
    if data == "my_stats":
        await my_stats(query, context)
        return
    if data.startswith("sub_team_"):
        team = data.replace("sub_team_", "")
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        if await subscribe_team(user_id, team):
            sent = await context.bot.send_message(chat_id=chat_id, text=f"✅ Подписка на {team} оформлена!", reply_markup=main_menu())
        else:
            sent = await context.bot.send_message(chat_id=chat_id, text=f"ℹ️ Вы уже подписаны на {team}", reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return
    if data.startswith("unsub_team_"):
        await unsubscribe_team(user_id, data.replace("unsub_team_", ""))
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await context.bot.send_message(chat_id=chat_id, text=f"❌ Отписка выполнена", reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return
    if data.startswith("goal_unsub_"):
        match_id = int(data.replace("goal_unsub_", ""))
        cursor.execute("DELETE FROM goal_subscriptions WHERE user_id=? AND match_id=?", (user_id, match_id))
        conn.commit()
        chat_id = query.message.chat.id
        await delete_previous_message(chat_id, context)
        sent = await context.bot.send_message(chat_id=chat_id, text=f"❌ Отписка от матча выполнена", reply_markup=main_menu())
        last_message_ids[chat_id] = sent.message_id
        try:
            await query.message.delete()
        except:
            pass
        return

# ================== ЗАПУСК ==================
def main():
    print("=" * 60)
    print("⚽ ФУТБОЛЬНЫЙ БОТ PRO (с прогнозами, баллами, рейтингами)")
    print("=" * 60)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("setnick", set_nickname))
    app.add_handler(CommandHandler("predictions", show_active_predictions))
    app.add_handler(CommandHandler("predict", make_prediction))
    app.add_handler(CommandHandler("leaderboard", show_leaderboard))
    app.add_handler(CommandHandler("monthly", monthly_leaderboard))
    app.add_handler(CommandHandler("winners", winners_history))
    app.add_handler(CommandHandler("mystats", my_stats))
    app.add_handler(CommandHandler("addprediction", admin_add_prediction))
    app.add_handler(CommandHandler("closeprediction", admin_close_prediction))
    app.add_handler(CommandHandler("finishprediction", admin_finish_prediction))
    app.add_handler(CommandHandler("adminpreds", admin_all_predictions))
    feedback_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(feedback_start, pattern="^feedback$")],
        states={FEEDBACK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_text_received)]},
        fallbacks=[CommandHandler("cancel", cancel_feedback)],
    )
    app.add_handler(feedback_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(match_checker(app))
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":   
    main()
