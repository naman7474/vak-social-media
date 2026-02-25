import asyncio
from aiogram.types import Update
from vak_bot.bot.runtime import bot, dispatcher

payload = {
  "update_id": 123456789,
  "message": {
    "message_id": 1,
    "from": {"id": 896790499, "is_bot": False, "first_name": "TestUser"},
    "chat": {"id": 896790499, "type": "private"},
    "date": 1672531200,
    "text": "/ad https://www.instagram.com/reel/DUfU_jNkY0x/ VAK-002"
  }
}

async def main():
    update = Update.model_validate(payload)
    await dispatcher.feed_update(bot, update)
    print("Dispatched!")

if __name__ == "__main__":
    asyncio.run(main())
