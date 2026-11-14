import sys

# Optional uvloop
if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
        print("✓ uvloop enabled")
    except ImportError:
        print("⚠ uvloop not installed, using default asyncio loop")

from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus
import asyncio
import os

import config
from ..logging import LOGGER

# Railway Variables me BOT_SESSION daaloge to bot har restart pe naya login nahi karega
BOT_SESSION = os.getenv("BOT_SESSION") or None


class SHUKLA(Client):
    def __init__(self):
        LOGGER(__name__).info("Starting Bot...")

        super().__init__(
            name="SHUKLAMUSIC",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            session_string=BOT_SESSION,
            in_memory=True,
            max_concurrent_transmissions=7,
        )

    async def start(self):
        # FloodWait aaye to crash mat ho, itna ruk ke khud dobara login karo
        while True:
            try:
                await super().start()
                break
            except errors.FloodWait as e:
                LOGGER(__name__).warning(f"FloodWait {e.value}s, sleeping...")
                await asyncio.sleep(e.value + 5)

        me = await self.get_me()

        self.id = me.id
        self.name = f"{me.first_name} {me.last_name or ''}".strip()
        self.username = me.username or "None"
        self.mention = me.mention

        # Pehli baar login ke baad session string OWNER ko DM me bhejo (Railway me BOT_SESSION me daalna)
        if not BOT_SESSION:
            try:
                session = await self.export_session_string()
                await self.send_message(
                    config.OWNER_ID,
                    "🔑 <b>BOT_SESSION</b>\nIsko Railway Variables me <code>BOT_SESSION</code> naam se daalo, "
                    "phir ye message delete kar do (kisi ko mat dena):\n\n"
                    f"<code>{session}</code>",
                )
            except Exception:
                pass

        try:
            await self.send_message(
                chat_id=config.LOGGER_ID,
                text=(
                    f"<u><b>» {self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b></u>\n\n"
                    f"ɪᴅ : <code>{self.id}</code>\n"
                    f"ɴᴀᴍᴇ : {self.name}\n"
                    f"ᴜsᴇʀɴᴀᴍᴇ : @{self.username}"
                ),
            )

        except (errors.ChannelInvalid, errors.PeerIdInvalid):
            LOGGER(__name__).error(
                "Bot cannot access LOGGER_ID. Add the bot to the log group/channel."
            )
            raise SystemExit(1)

        except Exception as ex:
            LOGGER(__name__).error(
                f"Failed to access LOGGER_ID: {type(ex).__name__}: {ex}"
            )
            raise SystemExit(1)

        try:
            member = await self.get_chat_member(
                config.LOGGER_ID,
                self.id
            )

            if member.status not in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER,
            ):
                LOGGER(__name__).error(
                    "Promote the bot as admin in LOGGER_ID."
                )
                raise SystemExit(1)

        except Exception as ex:
            LOGGER(__name__).error(
                f"Failed checking admin status: {type(ex).__name__}: {ex}"
            )
            raise SystemExit(1)

        LOGGER(__name__).info(
            f"Music Bot Started Successfully as {self.name}"
        )

    async def stop(self):
        LOGGER(__name__).info("Stopping Bot...")
        await super().stop()
            
