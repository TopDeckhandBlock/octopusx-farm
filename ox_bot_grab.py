import asyncio, re
from telethon import TelegramClient

SESSION = "C:/Users/User/tmp/digest_copy_0927"
API_ID = 23926822
API_HASH = "b18441a1ff607e10a989891a5462e627"


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("session not authorized")
        return
    me = await client.get_me()
    print("session:", me.username or me.id)

    bot = await client.get_entity("ProxyGrabReform_bot")
    for cmd in ("/proxy", "/proxy socks5", "/refresh"):
        await client.send_message(bot, cmd)
        await asyncio.sleep(4)
    msgs = await client.get_messages(bot, limit=8)
    found = set()
    for m in msgs:
        t = m.message or ""
        for line in t.splitlines():
            line = line.strip()
            m2 = re.match(r"((?:https?|socks5)://)?((?:\d{1,3}\.){3}\d{1,3}):(\d{2,5})", line)
            if m2:
                scheme = (m2.group(1) or "http://").rstrip("//")
                found.add(f"{scheme}://{m2.group(2)}:{m2.group(3)}")
    print("proxies found:", len(found))
    with open("C:/Users/User/tmp/ox_bot_proxies.txt", "w") as f:
        f.write("\n".join(sorted(found)))
    for p in sorted(found):
        print(p)
    await client.disconnect()


asyncio.run(main())