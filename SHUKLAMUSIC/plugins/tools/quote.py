# -----------------------------------------------
# 🔸 StrangerMusic Project
# 🔹 Developed & Maintained by: Shashank Shukla (https://github.com/itzshukla)
# 📅 Copyright © 2022 – All Rights Reserved
#
# 📖 License:
# This source code is open for educational and non-commercial use ONLY.
# You are required to retain this credit in all copies or substantial portions of this file.
# Commercial use, redistribution, or removal of this notice is strictly prohibited
# without prior written permission from the author.
#
# ❤️ Made with dedication and love by ItzShukla
import asyncio
import base64
from io import BytesIO

from httpx import AsyncClient, Timeout

from PIL import Image
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
from pyrogram.types import Message

from SHUKLAMUSIC import app
from SHUKLAMUSIC.utils.quotegen import render_quote

BOT_NAME = "Mahi"  # "Mahi Quote - Generating..." me yahi naam dikhega
STATUS_TEXT = f"🌸 <b>{BOT_NAME} Quote</b>\n✨ <b>Generating sticker...</b>"

SHOW_TITLE = False  # True karoge to admin/owner tag naam ke saamne dikhega
USE_API = True  # True: pehle Quotly API try hogi, fail ho to bot ka apna renderer
QUOTE_APIS = [
    "https://bot.lyo.su/quote/generate",
    "https://quoteampi.onrender.com/generate",
]
_http = AsyncClient(verify=False, timeout=Timeout(20))

_CE_CACHE = {}  # custom emoji id -> PIL image / None
_TITLE_CACHE = {}  # (chat_id, user_id) -> title


# -----------------------------------------------------------------
# Sender info (forward / anonymous admin / normal sab handle)
# -----------------------------------------------------------------
def _full_name(u):
    if not u:
        return ""
    first = getattr(u, "first_name", None) or ""
    last = getattr(u, "last_name", None)
    name = f"{first} {last}" if last else first
    name = name.strip()
    if not name and getattr(u, "is_deleted", False):
        return "Deleted Account"
    return name


def get_sender(m: Message) -> dict:
    s = {"id": 1, "name": "", "user": None, "obj": None, "photo": None, "fwd": False}

    def from_user(u):
        s.update(id=u.id, name=_full_name(u), user=u, obj=u, photo=getattr(u, "photo", None))

    def from_chat(c):
        s.update(id=c.id, name=getattr(c, "title", "") or "", obj=c, photo=getattr(c, "photo", None))

    fo = getattr(m, "forward_origin", None)  # naya kurigram
    if fo is not None:
        s["fwd"] = True
        u = getattr(fo, "sender_user", None)
        hidden = getattr(fo, "sender_user_name", None)
        ch = getattr(fo, "sender_chat", None) or getattr(fo, "chat", None)
        if u:
            from_user(u)
        elif hidden:
            s["name"] = hidden
        elif ch:
            from_chat(ch)
        return s

    if getattr(m, "forward_date", None):  # purana pyrogram
        s["fwd"] = True
        if getattr(m, "forward_sender_name", None):
            s["name"] = m.forward_sender_name
        elif getattr(m, "forward_from", None):
            from_user(m.forward_from)
        elif getattr(m, "forward_from_chat", None):
            from_chat(m.forward_from_chat)
        return s

    if m.sender_chat:
        from_chat(m.sender_chat)
    elif m.from_user:
        from_user(m.from_user)
    return s


def _media_label(m: Message) -> str:
    if m.sticker:
        return f"{m.sticker.emoji or '🖼'} Sticker"
    if m.photo:
        return "🖼 Photo"
    if m.video or m.video_note or m.animation:
        return "🎬 Video"
    if m.voice:
        return "🎤 Voice message"
    if m.audio:
        return "🎵 Audio"
    if m.document:
        return "📄 File"
    return "…"


def _text_of(m: Message) -> str:
    return str(m.text or m.caption or "")


def _entities(m: Message):
    out = []
    for e in m.entities or m.caption_entities or []:
        d = {"type": getattr(e.type, "name", "").lower(), "offset": e.offset, "length": e.length}
        cid = getattr(e, "custom_emoji_id", None)
        if cid:
            d["custom_emoji_id"] = str(cid)
        out.append(d)
    return out


def _custom_ranges(m: Message):
    ents = m.entities or m.caption_entities or []
    return [
        (e.offset, e.length, e.custom_emoji_id)
        for e in ents
        if getattr(e.type, "name", "") == "CUSTOM_EMOJI" and getattr(e, "custom_emoji_id", None)
    ]


_PALETTE = ["#ff8e86", "#ffa357", "#b18fff", "#85de85", "#4dd6d6", "#7ab5ff", "#ff8fc8"]


def name_color(s: dict) -> str:
    """Telegram ne user ko jo name color diya hai wahi (nahi mila to id%7)."""
    c = getattr(s.get("obj"), "color", None)
    idx = getattr(c, "color", None) if c is not None else None
    if not isinstance(idx, int) or not 0 <= idx < 7:
        idx = abs(int(s["id"])) % 7
    return _PALETTE[idx]


async def get_title(m: Message, s: dict) -> str:
    """Admin / owner / custom title (jaise PANDU) - sirf groups me."""
    if not SHOW_TITLE:
        return ""
    if s["fwd"]:
        return ""
    sc = m.sender_chat
    if sc and m.chat and sc.id == m.chat.id:  # anonymous admin
        return getattr(m, "author_signature", None) or "admin"
    if s["user"] is None or not m.chat:
        return ""
    if m.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return ""
    key = (m.chat.id, s["id"])
    if key in _TITLE_CACHE:
        return _TITLE_CACHE[key]
    title = ""
    try:
        mem = await app.get_chat_member(m.chat.id, s["id"])
        custom = getattr(mem, "custom_title", None)
        if mem.status == ChatMemberStatus.OWNER:
            title = custom or "owner"
        elif mem.status == ChatMemberStatus.ADMINISTRATOR:
            title = custom or "admin"
    except Exception:
        title = ""
    if len(_TITLE_CACHE) > 500:
        _TITLE_CACHE.clear()
    _TITLE_CACHE[key] = title
    return title


async def get_avatar(photo):
    if not photo:
        return None
    try:
        bio = await app.download_media(photo.big_file_id, in_memory=True)
        bio.seek(0)
        return Image.open(bio).convert("RGBA")
    except Exception:
        return None


async def load_custom_emojis(ids) -> dict:
    """Premium emoji ki image laata hai (animated ho to uska static thumbnail)."""
    need = [i for i in set(ids) if i not in _CE_CACHE]
    if need:
        try:
            stickers = await app.get_custom_emoji_stickers(need)
        except Exception:
            stickers = []
        for st in stickers:
            img = None
            try:
                animated = getattr(st, "is_animated", False) or getattr(st, "is_video", False)
                src = None
                if not animated:
                    src = st.file_id
                elif getattr(st, "thumbs", None):
                    src = st.thumbs[0].file_id
                if src:
                    bio = await app.download_media(src, in_memory=True)
                    bio.seek(0)
                    img = Image.open(bio).convert("RGBA")
            except Exception:
                img = None
            cid = getattr(st, "custom_emoji_id", None)
            if cid is not None:
                _CE_CACHE[cid] = img
        for i in need:
            _CE_CACHE.setdefault(i, None)
        if len(_CE_CACHE) > 300:
            for k in list(_CE_CACHE)[:100]:
                _CE_CACHE.pop(k, None)
    return {i: _CE_CACHE.get(i) for i in ids}


async def build_blocks(messages, is_reply):
    blocks, ce_ids = [], []
    for m in messages:
        s = get_sender(m)
        text = _text_of(m) or _media_label(m)
        if len(text) > 600:
            text = text[:600] + "…"
        custom = _custom_ranges(m)
        status_id = None
        emoji_status = getattr(s["user"], "emoji_status", None) if s["user"] else None
        if emoji_status and getattr(emoji_status, "custom_emoji_id", None):
            status_id = emoji_status.custom_emoji_id

        reply = None
        rm = m.reply_to_message
        if is_reply and rm and not getattr(rm, "empty", False):
            rs = get_sender(rm)
            reply = {"name": rs["name"], "text": _text_of(rm) or _media_label(rm)}

        blocks.append(
            {
                "id": s["id"],
                "name": s["name"],
                "title": await get_title(m, s),
                "text": text,
                "custom": [c for c in custom if c[0] < 600],
                "entities": _entities(m),
                "username": getattr(s["user"], "username", None) or "",
                "status_id": status_id,
                "color": name_color(s),
                "avatar": await get_avatar(s["photo"]),
                "reply": reply,
            }
        )
        ce_ids += [c[2] for c in custom]
        if status_id:
            ce_ids.append(status_id)
    return blocks, ce_ids


# -----------------------------------------------------------------
async def quote_via_api(blocks, ctx):
    msgs = []
    for b in blocks:
        frm = {"id": b["id"], "name": b["name"], "username": b["username"], "type": "private"}
        if b["title"]:
            frm["title"] = b["title"]
        if b["status_id"]:
            frm["emoji_status"] = str(b["status_id"])
        m = {
            "entities": b["entities"],
            "chatId": b["id"],
            "text": b["text"],
            "avatar": True,
            "from": frm,
            "replyMessage": {},
        }
        if b["reply"]:
            m["replyMessage"] = {"name": b["reply"]["name"], "text": b["reply"]["text"], "chatId": b["id"]}
        msgs.append(m)
    payload = {
        "type": "quote", "format": "webp", "backgroundColor": "#1b1429",
        "width": 512, "height": 768, "scale": 2, "messages": msgs,
    }
    last = "no api"
    for url in QUOTE_APIS:
        try:
            r = await _http.post(url, json=payload, timeout=Timeout(25))
            if r.is_error:
                last = f"{url} HTTP {r.status_code}"
                continue
            data = r.json()
            if data.get("ok"):
                raw = base64.b64decode(data["result"]["image"])
                im = Image.open(BytesIO(raw)).convert("RGBA")
                im.thumbnail((512, 512))
                out = BytesIO()
                im.save(out, "WEBP")
                return out.getvalue()
            last = f"{url} {str(data)[:100]}"
        except Exception as e:
            last = f"{url} {type(e).__name__}"
    raise RuntimeError(last)


async def send_quote(ctx: Message, messages, is_reply):
    status = None
    try:
        status = await ctx.reply_text(STATUS_TEXT, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    try:
        blocks, ce_ids = await build_blocks(messages, is_reply)
        imgs = await load_custom_emojis(ce_ids) if ce_ids else {}
        data = None
        if USE_API:
            try:
                data = await quote_via_api(blocks, ctx)
            except Exception:
                data = None  # API band -> neeche apna renderer
        if data is None:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, render_quote, blocks, imgs)
        sticker = BytesIO(data)
        sticker.name = "quote.webp"
        await ctx.reply_sticker(sticker)
    except Exception as e:
        await ctx.reply_text(f"⚠️ Quote error:\n{type(e).__name__}: {e}")
    finally:
        if status:
            try:
                await status.delete()
            except Exception:
                pass


def isArgInt(txt) -> list:
    try:
        return [True, int(txt)]
    except ValueError:
        return [False, 0]


async def _do_quote(client, ctx: Message):
    is_reply = ctx.command[0].endswith("r") or (
        len(ctx.command) > 1 and ctx.command[1].lower() == "r"
    )
    if len(ctx.command) > 1:
        check = isArgInt(ctx.command[1])
        if check[0]:
            count = check[1]
            if count < 2 or count > 10:
                return await ctx.reply_text("Invalid range (2 se 10 tak)")
            try:
                start = ctx.reply_to_message.id
                fetched = await client.get_messages(
                    chat_id=ctx.chat.id,
                    message_ids=list(range(start, start + count + 5)),
                    replies=-1,
                )
                # khali / bina text wale hata ke SIRF utne hi lo jitne maange
                messages = [
                    i for i in fetched if not i.empty and (i.text or i.caption)
                ][:count]
            except Exception as e:
                return await ctx.reply_text(f"⚠️ {type(e).__name__}: {e}")
            if not messages:
                return await ctx.reply_text("Quote karne layak text nahi mila.")
            return await send_quote(ctx, messages, is_reply)
    try:
        one = await client.get_messages(
            chat_id=ctx.chat.id, message_ids=ctx.reply_to_message.id, replies=-1
        )
    except Exception as e:
        return await ctx.reply_text(f"⚠️ {type(e).__name__}: {e}")
    await send_quote(ctx, [one], is_reply)


@app.on_message(filters.command(["q", "qr"]) & filters.reply)
async def quote_cmd(client, ctx: Message):
    await _do_quote(client, ctx)
