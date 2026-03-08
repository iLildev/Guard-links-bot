import re
import time
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# ====== إعدادات ======
TOKEN = "8085959978:AAG3EagJGYMgmgOhYrQAlpKEPwHw7VObYuU"
OWNER_ID = 8168600848

AGGRESSIVE_INVITE_DELETE = True

# قائمة المجموعات المسموح بها
WHITELIST_CHAT_IDS = {-1001234567890}

# TTL لذاكرة الكاش
CHAT_TYPE_CACHE_TTL = 60 * 60

# ====== أنماط الروابط ======
PUBLIC_USERNAME_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/@?([A-Za-z0-9_]{5,32})(\?[^ \n]*)?", re.I
)

INVITE_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+([A-Za-z0-9_-]+)|joinchat/([A-Za-z0-9_-]+))|tg://join\?invite=([A-Za-z0-9_-]+)",
    re.I
)

BOT_HINT_RE = re.compile(r"(?:/|@)([A-Za-z0-9_]{5,32}bot)\b", re.I)
DEEP_START_RE = re.compile(r"\?start=", re.I)

# ====== تهيئة البوت ======
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# ====== كاش نوع الشات ======
_chat_type_cache = {}
_cache_lock = asyncio.Lock()


async def get_cached_chat_type(username: str):
    username = username.lower().lstrip("@")
    now = time.time()

    async with _cache_lock:
        entry = _chat_type_cache.get(username)
        if entry and now - entry["ts"] < CHAT_TYPE_CACHE_TTL:
            return entry["data"]

    try:
        chat = await bot.get_chat(f"@{username}")
        ctype = getattr(chat, "type", None)
        is_bot = getattr(chat, "is_bot", False)

        result = {
            "type": ctype,
            "is_bot": is_bot
        }

    except Exception:
        result = {"type": None, "is_bot": False}

    async with _cache_lock:
        _chat_type_cache[username] = {"data": result, "ts": time.time()}

    return result


def extract_all_telegram_links(message: types.Message):

    texts = []

    if message.text:
        texts.append(message.text)

    if message.caption:
        texts.append(message.caption)

    entities_texts = []

    for ent in (message.entities or []) + (message.caption_entities or []):
        try:
            if ent.type == "text_link" and getattr(ent, "url", None):
                entities_texts.append(ent.url)
        except Exception:
            pass

    buttons = []

    if message.reply_markup and getattr(message.reply_markup, "inline_keyboard", None):
        for row in message.reply_markup.inline_keyboard:
            for btn in row:
                if getattr(btn, "url", None):
                    buttons.append(btn.url)

    return texts + entities_texts + buttons


# ====== الحماية ======
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def guard_message(message: types.Message):

    chat = message.chat

    if chat.id in WHITELIST_CHAT_IDS:
        return

    pieces = extract_all_telegram_links(message)

    if not pieces:
        return

    to_delete = False
    reasons = []

    for piece in pieces:

        if not piece:
            continue

        for m in PUBLIC_USERNAME_RE.finditer(piece):

            username = m.group(1)

            if not username:
                continue

            if username.lower().endswith("bot"):
                to_delete = True
                reasons.append(f"bot_hint:{username}")
                break

            if DEEP_START_RE.search(piece):
                to_delete = True
                reasons.append(f"bot_start:{username}")
                break

            info = await get_cached_chat_type(username)

            ctype = info.get("type")
            is_bot = info.get("is_bot")

            if is_bot:
                to_delete = True
                reasons.append(f"known_bot:{username}")
                break

            if ctype and ctype.lower() in ("group", "supergroup"):
                to_delete = True
                reasons.append(f"public_group:{username}")
                break

        if to_delete:
            break

        if INVITE_RE.search(piece):

            if AGGRESSIVE_INVITE_DELETE:
                to_delete = True
                reasons.append("invite_link")
                break

    if to_delete:
        try:
            await message.delete()
        except Exception:
            pass


# ====== أوامر المالك ======
@dp.message_handler(commands=["addchat"], chat_type="private")
async def add_chat(message: types.Message):

    if message.from_user.id != OWNER_ID:
        return

    try:
        chat_id = int(message.get_args())
        WHITELIST_CHAT_IDS.add(chat_id)

        await message.reply(f"✅ تمت إضافة الشات:\n{chat_id}")

    except:
        await message.reply("❌ الاستخدام:\n/addchat -1001234567890")


@dp.message_handler(commands=["removechat"], chat_type="private")
async def remove_chat(message: types.Message):

    if message.from_user.id != OWNER_ID:
        return

    try:
        chat_id = int(message.get_args())
        WHITELIST_CHAT_IDS.discard(chat_id)

        await message.reply(f"🗑 تمت إزالة الشات:\n{chat_id}")

    except:
        await message.reply("❌ الاستخدام:\n/removechat -1001234567890")


@dp.message_handler(commands=["listchats"], chat_type="private")
async def list_chats(message: types.Message):

    if message.from_user.id != OWNER_ID:
        return

    if not WHITELIST_CHAT_IDS:
        await message.reply("لا توجد مجموعات.")
        return

    text = "\n".join(str(x) for x in WHITELIST_CHAT_IDS)

    await message.reply(f"📋 المجموعات المسموحة:\n{text}")


if __name__ == "__main__":
    print("Link-Guard Bot Started")
    executor.start_polling(dp, skip_updates=True)