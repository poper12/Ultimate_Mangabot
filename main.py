import asyncio as aio
from bot import *
#import os
#import shutil

async def async_main():
    db = DB()
    await db.connect()

def cleanning():
    try:
        if os.path.isdir("/app/Downloads"):
            shutil.rmtree("/app/Downloads")
            print(f"/app/Downloads has been deleted.")
    except:
        if os.path.isdir("Downloads"):
            shutil.rmtree("Downloads")
            print(f"Downloads has been deleted.")

if __name__ == '__main__':
    cleanning()
    loop = aio.get_event_loop_policy().get_event_loop()
    loop.run_until_complete(async_main())
    loop.create_task(manga_updater())
    for i in range(10):
        loop.create_task(chapter_creation(i + 1))
    bot.run()
