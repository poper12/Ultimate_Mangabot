import enum
import shutil
from ast import arg
import asyncio
import re
import os
from dataclasses import dataclass
import datetime as dt
import json

import pyrogram.errors
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaDocument

from config import env_vars, dbname
from img2cbz.core import fld2cbz
from img2pdf.core import fld2pdf, fld2thumb
from img2pdf.comp import compressFK
from plugins import *
import os

from pyrogram import Client, filters
from typing import Dict, Tuple, List, TypedDict
from loguru import logger

from models.db import DB, ChapterFile, Subscription, LastChapter, MangaName, MangaOutput, UserInfo
from pagination import Pagination
from plugins.client import clean
from tools.aqueue import AQueue
from tools.flood import retry_on_flood

from asyncio import create_subprocess_exec
from os import execl
from sys import executable


OWNER_ID = 6321064549 # put owner id in number directly 
auth_users = [5560966839,5164955785,5543390445,6184704946,6120024125,1795061251,7107549259,1657517641,7684964982,7107549259,1587625628,5560966839,6796849176,6431789051,7898642709,55609668395869316614,2004259277,1203848102,1335306418,7113854910,8065503440,5164955785,5591954930,7142918767,5455664988,6844586745,1366609719,6321064549,7002247408,1394188404,5280269345,7136303059,5005411270,6723435719,6063343021,5469587702,5929480351,1720123638,1864972077,1016442910,6558061813,1895356693,1880221341,1788144071,6564942226,6907806722,5988817148,5164955785,7716045686,6975428639,1302933634,6321064549] # eg: [83528911,836289,9362891]
AUTH_USERS = auth_users + [OWNER_ID]
sb = [
	[InlineKeyboardButton('× Manga Campus ×', callback_data = "athumb:MC")],
        [InlineKeyboardButton("× Manga Weebs ×", callback_data = "athumb:MW")],
	[InlineKeyboardButton('× Manga Yugen ×', callback_data = "athumb:MY")],
        [InlineKeyboardButton("× Manga Mayhem ×", callback_data = "athumb:MM")],
	[InlineKeyboardButton('× Manhwa18cc ×', callback_data = "athumb:M18")],
	[InlineKeyboardButton('× Manhwa Worlds ×', callback_data = "athumb:MWd")],
]


mangas: Dict[str, MangaCard] = dict()
chapters: Dict[str, MangaChapter] = dict()
pdfs: Dict[str, str] = dict()
paginations: Dict[int, Pagination] = dict()
queries: Dict[str, Tuple[MangaClient, str]] = dict()
full_pages: Dict[str, List[str]] = dict()
favourites: Dict[str, MangaCard] = dict()
language_query: Dict[str, Tuple[str, str]] = dict()
users_in_channel: Dict[int, dt.datetime] = dict()
locks: Dict[int, asyncio.Lock] = dict()

plugin_dicts: Dict[str, Dict[str, MangaClient]] = {
    "🇬🇧 EN": {
        "MangaDex": MangaDexClient(),
	"ManhuaFast": ManhuaFastClient(),
	"ReaperScans": ReaperScansClient(),
        "Mgeko": MgekoClient(),
        "MagaKakalot": MangaKakalotClient(),
        "Manganelo": ManganeloClient(),
        "Manganato": ManganatoClient(),
        "MangaSee":  MangaSeeClient(),
        "MangaBuddy": MangaBuddyClient(),
        "AsuraScans": AsuraScansClient(),
        "NineManga": NineMangaClient(),        
        "LikeManga": LikeMangaClient(), 
        "FlameComics": FlameComicsClient(),
          },
    "🔞 18+": {
        "Manga18fx": Manga18fxClient(),
        "MangaDistrict": MangaDistrictClient(),
	"OmegaScan": OmegaScansClient(),
    }
}

cache_dir = "cache"
if os.path.exists(cache_dir):
    shutil.rmtree(cache_dir)
with open("tools/help_message.txt", "r") as f:
    help_msg = f.read()


class OutputOptions(enum.IntEnum):
    PDF = 1
    CBZ = 2

    def __and__(self, other):
        return self.value & other

    def __xor__(self, other):
        return self.value ^ other

    def __or__(self, other):
        return self.value | other


#disabled = ["[🇬🇧 EN] McReader", "[🇬🇧 EN] Manhuaplus", "[🇪🇸 ES] MangasIn", "[🇪🇸 ES] Likemanga"]
disabled = []

plugins = dict()
for lang, plugin_dict in plugin_dicts.items():
    for name, plugin in plugin_dict.items():
        identifier = f'[{lang}] {name}'
        if identifier in disabled:
            continue
        plugins[identifier] = plugin

# subsPaused = ["[🇪🇸 ES] TMO"]
subsPaused = disabled + []


def split_list(li):
    return [li[x: x + 2] for x in range(0, len(li), 2)]


def get_buttons_for_options(user_options: int):
    buttons = []
    for option in OutputOptions:
        checked = "✅" if option & user_options else "❌"
        text = f'{checked} {option.name}'
        buttons.append([InlineKeyboardButton(text, f"options_{option.value}")])
    return InlineKeyboardMarkup(buttons)


bot = Client('bot',
             api_id=int(env_vars.get('API_ID')),
             api_hash=env_vars.get('API_HASH'),
             bot_token=env_vars.get('BOT_TOKEN'),
             max_concurrent_transmissions=3)

pdf_queue = AQueue()

if dbname:
    DB(dbname)
else:
    DB()


@bot.on_message(filters=~(filters.private & filters.incoming))
async def on_chat_or_channel_message(client: Client, message: Message):
	# Donot Edit This Or Donot Add any thing
	pass

@bot.on_message()
async def on_private_message(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    channel = env_vars.get('CHANNEL') 
    if not channel:
        return message.continue_propagation()
    if in_channel_cached := users_in_channel.get(message.from_user.id):
        if dt.datetime.now() - in_channel_cached < dt.timedelta(days=1):
            return message.continue_propagation()
    try:
        if await client.get_chat_member(channel, message.from_user.id):
            users_in_channel[message.from_user.id] = dt.datetime.now()
            return message.continue_propagation()
    except pyrogram.errors.UsernameNotOccupied:
        logger.debug("Channel does not exist, therefore bot will continue to operate normally")
        return message.continue_propagation()
    except pyrogram.errors.ChatAdminRequired:
        logger.debug("Bot is not admin of the channel, therefore bot will continue to operate normally")
        return message.continue_propagation()
    except pyrogram.errors.UserNotParticipant:
        await message.reply("In order to use the bot you must join it's update channel.",
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton('Join!', url=f't.me/{channel}')]]
                            ))
    except pyrogram.ContinuePropagation:
        raise
    except pyrogram.StopPropagation:
        raise
    except BaseException as e:
        logger.exception(e)


@bot.on_message(filters=filters.command(['start']))
async def on_start(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    logger.info(f"User {message.from_user.id} started the bot")
    await message.reply("Welcome to the best manga pdf bot in telegram!!\n"
                        "\n"
                        "How to use? Just type the name of some manga you want to keep up to date.\n"
                        "\n"
                        "For example:\n"
                        "`One Piece`\n"
                        "\n"
                        "Check /help for more information.")
    logger.info(f"User {message.from_user.id} finished the start command")
    

@bot.on_message(filters=filters.command(['help']))
async def on_help(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    await message.reply(help_msg)


@bot.on_message(filters=filters.command(['queue']))
async def on_help(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    await message.reply(f'Queue size: {pdf_queue.qsize()}')

@bot.on_message(filters=(filters.command('on') & filters.private))
async def on_set_caption(client: Client, message: Message):
	if message.from_user.id not in AUTH_USERS:
	        return await message.reply("You can't use me buddy!!")
		
	db = DB()
	user_info = await db.get_user(str(message.from_user.id))
	try:
		cap = user_info.cap
		thumb = user_info.thumb
		b1 = user_info.b1
		b2 = user_info.b2
		text = f"""
 <b><blockquote expandable><i>For Manga Camps:
 Thumb : <code>{env_vars["TH1"]}</code>
 Banner: <code>{env_vars["B1"]}</code>
 For Weebs:
 Thumb: <code>{env_vars["TH2"]}</code>
 Bannar: <code>{env_vars["B2"]}</code>
 For Yugen:
 Thumb: <code>{env_vars["TH3"]}</code>
 Bannar: <code>{env_vars["B3"]}</code>
 For Mayhem:
 Thumb: <code>{env_vars["TH4"]}</code>
 Bannar: <code>{env_vars["B4"]}</code>
 For Manhwa18cc:
 Thumb: <code>{env_vars["TH5"]}</code>
 Bannar: <code>{env_vars["B5"]}</code>
 For Manhwa Worlds:
 Thumb: <code>{env_vars["TH6"]}</code>
 Bannar: <code>{env_vars["B6"]}</code></blockquote>
 
 To Views Photo: <code>/pto photoname.jpg</code>
 
 Your Currnet Settings:
 Caption: <code>{cap}</code>
 Thumb: <code>{thumb}</code>
 Banner: <code>{b1}</code>
 last: <code>{b2}</code>
 To Change Your Settings 👇👇</i></b>"""
	except Exception as e:
		print(f"on : {e}")
		text = f"""
 <b><blockquote expandable><i>For Manga Camps:
 Thumb : <code>{env_vars["TH1"]}</code>
 Banner: <code>{env_vars["B1"]}</code>
 For Weebs:
 Thumb: <code>{env_vars["TH2"]}</code>
 Bannar: <code>{env_vars["B2"]}</code>
 For Yugen:
 Thumb: <code>{env_vars["TH3"]}</code>
 Bannar: <code>{env_vars["B3"]}</code>
 For Mayhem:
 Thumb: <code>{env_vars["TH4"]}</code>
 Bannar: <code>{env_vars["B4"]}</code>
 For Manhwa18cc:
 Thumb: <code>{env_vars["TH5"]}</code>
 Bannar: <code>{env_vars["B5"]}</code>
 For Manhwa Worlds:
 Thumb: <code>{env_vars["TH6"]}</code>
 Bannar: <code>{env_vars["B6"]}</code></blockquote>
 
 
 To Views Photo: <code>/pto photoname.jpg</code>
 
 Your Currnet Settings:
 Caption: <code>None</code>
 Thumb: <code>None</code>
 Banner: <code>None</code>
 last: <code>None</code>
 To Change Your Settings 👇👇</i></b>"""
	return await message.reply(text, reply_markup=InlineKeyboardMarkup(sb))
	#cap = UserInfo(user_id=str(message.from_user.id), caption=caption)
        #await db.add(user_options)

@bot.on_message(filters=(filters.command(['pto', 'photo']) & filters.private))
async def on_photo(client: Client, message: Message):
	if message.from_user.id not in AUTH_USERS:
		return await message.reply("You can't use me buddy!!")
	try: 
		photo = message.text.split(" ")[1]
		if not photo.endswith(".jpg"):
			photo = photo + ".jpg"
		return await client.send_photo(chat_id=message.from_user.id, photo=photo, caption=f"<b>{photo}</b>")
	except Exception as e:
		return await message.reply(f" Errors Occures: {e}\n\n Correct Format: /pto thumb.jpg")

@bot.on_message(filters=(filters.command(['add', 'add_user']) & filters.private & filters.user(AUTH_USERS)))
async def add_user(client: Client, message: Message):
	try: 
		user_id = message.text.split(" ")[1]
		user_id = int(user_id)
		AUTH_USERS.append(user_id)
		return await client.send_message(chat_id=message.from_user.id, text=f"{user_id} added to admin list")
	except:
		return await message.reply(f"Could not add it")

@bot.on_message(filters=(filters.command(['remove', 'rm_user']) & filters.private & filters.user(AUTH_USERS)))
async def rm_user(client: Client, message: Message):
	try: 
		user_id = message.text.split(" ")[1]
		user_id = int(user_id)
		AUTH_USERS.remove(user_id)
		return await client.send_message(chat_id=message.from_user.id, text=f"{user_id} removed from admin list")
	except:
		return await message.reply(f"Could not remove it")
		

@bot.on_message(filters=filters.command(['refresh']))
async def on_refresh(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    text = message.reply_to_message.text or message.reply_to_message.caption
    if text:
        regex = re.compile(r'\[Read on telegraph]\((.*)\)')
        match = regex.search(text.markdown)
    else:
        match = None
    document = message.reply_to_message.document
    if not (message.reply_to_message and message.reply_to_message.outgoing and
            ((document and document.file_name[-4:].lower() in ['.pdf', '.cbz']) or match)):
        return await message.reply("This command only works when it replies to a manga file that bot sent to you")
    db = DB()
    if document:
        chapter = await db.get_chapter_file_by_id(document.file_unique_id)
    else:
        chapter = await db.get_chapter_file_by_id(match.group(1))
    if not chapter:
        return await message.reply("This file was already refreshed")
    await db.erase(chapter)
    return await message.reply("File refreshed successfully!")


@bot.on_message(filters=filters.command(['subs']))
async def on_subs(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    db = DB()

    filter_ = message.text.split(maxsplit=1)[1] if message.text.split(maxsplit=1)[1:] else ''
    filter_list = [filter_.strip() for filter_ in filter_.split(' ') if filter_.strip()]

    subs = await db.get_subs(str(message.from_user.id), filter_list)

    lines = []
    for sub in subs[:10]:
        lines.append(f'<a href="{sub.url}">{sub.name}</a>')
        lines.append(f'`/cancel {sub.url}`')
        lines.append('')

    if not lines:
        if filter_:
            return await message.reply("You have no subscriptions with that filter.")
        return await message.reply("You have no subscriptions yet.")

    text = "\n".join(lines)
    await message.reply(f'Your subscriptions:\n\n{text}\nTo see more subscriptions use `/subs filter`', disable_web_page_preview=True)


@bot.on_message(filters=filters.regex(r'^/cancel ([^ ]+)$'))
async def on_cancel_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    db = DB()
    sub = await db.get(Subscription, (message.matches[0].group(1), str(message.from_user.id)))
    if not sub:
        return await message.reply("You were not subscribed to that manga.")
    await db.erase(sub)
    return await message.reply("You will no longer receive updates for that manga.")


@bot.on_message(filters=filters.command(['options']))
async def on_options_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    db = DB()
    user_options = await db.get(MangaOutput, str(message.from_user.id))
    user_options = user_options.output if user_options else (1 << 30) - 1
    buttons = get_buttons_for_options(user_options)
    return await message.reply("Select the desired output format.", reply_markup=buttons)

@bot.on_message(filters.command(['rs', 'restart']) & filters.private & filters.user(AUTH_USERS))
async def on_rs(client: Client, message: Message):
    msg = await message.reply_text("...", quote=True)
    await (await create_subprocess_exec("python3", "update.py")).wait()
    execl(executable, executable, "-B", "main.py")

"""
@bot.on_message(filters=filters.regex(r'^/'))
async def on_unknown_command(client: Client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    await message.reply("Unknown command")
"""

@bot.on_message(filters=filters.text)
async def on_message(client, message: Message):
    if message.from_user.id not in AUTH_USERS:
        return await message.reply_text("You Can't Use Me Buddy' :(")
    language_query[f"lang_None_{hash(message.text)}"] = (None, message.text)
    for language in plugin_dicts.keys():
        language_query[f"lang_{language}_{hash(message.text)}"] = (language, message.text)
    await bot.send_message(message.chat.id, "Select search languages.", reply_markup=InlineKeyboardMarkup(
        split_list([InlineKeyboardButton(language, callback_data=f"lang_{language}_{hash(message.text)}")
                    for language in plugin_dicts.keys()])
    ))


async def options_click(client, callback: CallbackQuery):
    db = DB()
    user_options = await db.get(MangaOutput, str(callback.from_user.id))
    if not user_options:
        user_options = MangaOutput(user_id=str(callback.from_user.id), output=(2 << 30) - 1)
    option = int(callback.data.split('_')[-1])
    user_options.output ^= option
    buttons = get_buttons_for_options(user_options.output)
    await db.add(user_options)
    return await callback.message.edit_reply_markup(reply_markup=buttons)


async def language_click(client, callback: CallbackQuery):
    lang, query = language_query[callback.data]
    if not lang:
        return await callback.message.edit("Select search languages.", reply_markup=InlineKeyboardMarkup(
            split_list([InlineKeyboardButton(language, callback_data=f"lang_{language}_{hash(query)}")
                        for language in plugin_dicts.keys()])
        ))
    for identifier, manga_client in plugin_dicts[lang].items():
        queries[f"query_{lang}_{identifier}_{hash(query)}"] = (manga_client, query)
    await callback.message.edit(f"Language: {lang}\n\nSelect search plugin.", reply_markup=InlineKeyboardMarkup(
        split_list([InlineKeyboardButton(identifier, callback_data=f"query_{lang}_{identifier}_{hash(query)}")
                    for identifier in plugin_dicts[lang].keys() if f'[{lang}] {identifier}' not in disabled]) + [
            [InlineKeyboardButton("◀️ Back", callback_data=f"lang_None_{hash(query)}")]]
    ))



async def plugin_click(client, callback: CallbackQuery):
    manga_client, query = queries[callback.data]
    results = await manga_client.search(query)
    if not results:
        await bot.send_message(callback.from_user.id, "No manga found for given query.")
        return
    for result in results:
        mangas[result.unique()] = result
    await bot.send_message(callback.from_user.id,
                           "This is the result of your search",
                           reply_markup=InlineKeyboardMarkup([
                               [InlineKeyboardButton(result.name, callback_data=result.unique())] for result in results
                           ]))


async def manga_click(client, callback: CallbackQuery, pagination: Pagination = None):
    if pagination is None:
        pagination = Pagination()
        paginations[pagination.id] = pagination

    if pagination.manga is None:
        manga = mangas[callback.data]
        pagination.manga = manga

    results = await pagination.manga.client.get_chapters(pagination.manga, pagination.page)

    if not results:
        await callback.answer("Ups, no chapters there.", show_alert=True)
        return

    full_page_key = f'full_page_{hash("".join([result.unique() for result in results]))}'
    full_pages[full_page_key] = []
    for result in results:
        chapters[result.unique()] = result
        full_pages[full_page_key].append(result.unique())

    db = DB()
    subs = await db.get(Subscription, (pagination.manga.url, str(callback.from_user.id)))

    prev = [InlineKeyboardButton('<<', f'{pagination.id}_{pagination.page - 1}')]
    next_ = [InlineKeyboardButton('>>', f'{pagination.id}_{pagination.page + 1}')]
    prev_f = [InlineKeyboardButton('4x<<', f'{pagination.id}_{pagination.page - 4}')]
    next_f_ = [InlineKeyboardButton('>>4x', f'{pagination.id}_{pagination.page + 4}')]
    prev_t = [InlineKeyboardButton('10x<<', f'{pagination.id}_{pagination.page - 10}')]
    next_t_ = [InlineKeyboardButton('>>10x', f'{pagination.id}_{pagination.page + 10}')]
    
    footer = [prev_t + prev_f + prev + next_ + next_f_ + next_t_] if pagination.page > 1 else [next_ + next_f_ + next_t_]

    fav = [[InlineKeyboardButton(
        "Unsubscribe" if subs else "Subscribe",
        f"{'unfav' if subs else 'fav'}_{pagination.manga.unique()}"
    )]]
    favourites[f"fav_{pagination.manga.unique()}"] = pagination.manga
    favourites[f"unfav_{pagination.manga.unique()}"] = pagination.manga

    full_page = [[InlineKeyboardButton('Full Page', full_page_key)]]

    buttons = InlineKeyboardMarkup(fav + footer + [
        [InlineKeyboardButton(result.name, result.unique())] for result in results
    ] + full_page + footer)

    if pagination.message is None:
        try:
            message = await bot.send_photo(callback.from_user.id,
                                           pagination.manga.picture_url,
                                           f'{pagination.manga.name}\n'
                                           f'{pagination.manga.get_url()}', reply_markup=buttons)
            pagination.message = message
        except pyrogram.errors.BadRequest as e:
            file_name = f'pictures/{pagination.manga.unique()}.jpg'
            await pagination.manga.client.get_cover(pagination.manga, cache=True, file_name=file_name)
            message = await bot.send_photo(callback.from_user.id,
                                           f'./cache/{pagination.manga.client.name}/{file_name}',
                                           f'{pagination.manga.name}\n'
                                           f'{pagination.manga.get_url()}', reply_markup=buttons)
            pagination.message = message
    else:
        await bot.edit_message_reply_markup(
            callback.from_user.id,
            pagination.message.id,
            reply_markup=buttons
        )

users_lock = asyncio.Lock()


async def get_user_lock(chat_id: int):
    async with users_lock:
        lock = locks.get(chat_id)
        if not lock:
            locks[chat_id] = asyncio.Lock()
        return locks[chat_id]


async def chapter_click(client, data, chat_id):
    await pdf_queue.put(chapters[data], int(chat_id))
    logger.debug(f"Put chapter {chapters[data].name} to queue for user {chat_id} - queue size: {pdf_queue.qsize()}")


async def send_manga_chapter(client: Client, chapter, chat_id):
	db = DB()

	user_info = await db.get(UserInfo, str(chat_id))
	options = await db.get(MangaOutput, str(chat_id))
	options = options.output if options else (1 << 30) - 1
	
	error_caption = '\n'.join([
		f'{chapter.manga.name} - {chapter.name}',
		f'{chapter.get_url()}'
	])
	
	pictures_folder = await chapter.client.download_pictures(chapter)
	
	if not pictures_folder:
		return await client.send_message(chat_id,
						 f'Errors At Downlowder Picture From Chapters' +
						 f'{error_caption}')
	
	if not chapter.pictures:
		return await client.send_message(chat_id,
						 f'There was an error parsing this chapter or chapter is missing' +
						 f', please check the chapter at the web\n\n{error_caption}')
	
	if user_info.thumb:
		thumb_path = f"{user_info.thumb}"
	elif not user_info.thumb:
		thumb_path = "TH3.jpg"
	
	if user_info.cap:
		try:
			try: chap_num = re.search(r"Vol (\d+(?:\.\d+)?) Chapter (\d+(?:\.\d+)?)", chapter.name).group(2)
			except: chap_num = re.search(r"(\d+(?:\.\d+)?)", chapter.name).group(1)
			chap_name = clean(chapter.manga.name, 29)
			ch_name = user_info.cap
			chap_num = str(chap_num)
			chap_num = re.sub(r'(\d+)', lambda x: f"{int(x.group()):03}", chap_num, count=1)
			ch_name = ch_name.replace("{chap_num}", str(chap_num))
			ch_name = ch_name.replace("{chap_name}", str(chap_name))
		except Exception as e:
			print(e)
	else:
		ch_name = clean(f'{chapter.name} - {clean(chapter.manga.name, 25)}', 45)
	
	success_caption = f'<blockquote><b>{ch_name}</b></blockquote>'
	media_docs = []
	files_to_remove = []
	
	b1 = user_info.b1
	b2 = user_info.b2
	if options & OutputOptions.PDF:
		try:
			pdf = await asyncio.get_running_loop().run_in_executor(None, fld2pdf, pictures_folder, ch_name, b1, b2)
			
			if str(chapter.url).startswith("https://asuracomic.net"):
				pdf = compressFK(pdf, ch_name)
			elif str(chapter.url).startswith("https://reaperscans.com"):
				pdf = compressFK(pdf, ch_name)
			elif str(chapter.url).startswith("https://mangabuddy.com"):
				pdf = compressFK(pdf, ch_name)
			
			files_to_remove.append(pdf)
		except Exception as e:
			logger.exception(f'Error creating pdf for {chapter.name} - {chapter.manga.name}\n{e}')
			return await client.send_message(chat_id, f'There was an error making the pdf for this chapter. '
							 f'Forward this message to the bot group to report the '
							 f'error.\n\n{error_caption}')
		media_docs.append(InputMediaDocument(pdf, thumb=thumb_path))
		
	if options & OutputOptions.CBZ:
		try:
			cbz = await asyncio.get_running_loop().run_in_executor(None, fld2cbz, pictures_folder, ch_name, b1, b2)
			files_to_remove.append(cbz)
		except Exception as e:
			logger.exception(f'Error creating cbz for {chapter.name} - {chapter.manga.name}\n{e}')
			return await client.send_message(chat_id, f'There was an error making the cbz for this chapter. '
								 f'Forward this message to the bot group to report the '
								 f'error.\n\n{error_caption}')
		media_docs.append(InputMediaDocument(cbz, thumb=thumb_path))
	
	if len(media_docs) == 0:
		messages: list[Message] = await retry_on_flood(client.send_message)(chat_id, success_caption)
	else:
		media_docs[-1].caption = success_caption
		messages: list[Message] = await retry_on_flood(client.send_media_group)(chat_id, media_docs)
	
	for file in files_to_remove:
		os.remove(file)
	
	for msg in messages:
		if msg:
			if ((user_info.thumb) == (env_vars["TH1"])):
				# Manga Campus
				await msg.copy(-1002432294589)
			elif ((user_info.thumb) == (env_vars["TH2"])):
				#Manga Weebs
				await msg.copy(-1002231355848)
			elif ((user_info.thumb) == (env_vars["TH3"])):
				await msg.copy(-1002310388934)
			elif ((user_info.thumb) == (env_vars["TH6"])):
				await msg.copy(-1002443524328)
			else:
				await msg.copy(-1002109661325)
			await asyncio.sleep(10)


async def pagination_click(client: Client, callback: CallbackQuery):
    pagination_id, page = map(int, callback.data.split('_'))
    pagination = paginations[pagination_id]
    pagination.page = page
    await manga_click(client, callback, pagination)


async def full_page_click(client: Client, callback: CallbackQuery):
    chapters_data = full_pages[callback.data]
    for chapter_data in reversed(chapters_data):
        try:
            await chapter_click(client, chapter_data, callback.from_user.id)
        except Exception as e:
            logger.exception(e)


async def favourite_click(client: Client, callback: CallbackQuery):
    action, data = callback.data.split('_')
    fav = action == 'fav'
    manga = favourites[callback.data]
    db = DB()
    subs = await db.get(Subscription, (manga.url, str(callback.from_user.id)))
    if not subs and fav:
        await db.add(Subscription(url=manga.url, user_id=str(callback.from_user.id)))
    if subs and not fav:
        await db.erase(subs)
    if subs and fav:
        await callback.answer("You are already subscribed", show_alert=True)
    if not subs and not fav:
        await callback.answer("You are not subscribed", show_alert=True)
    reply_markup = callback.message.reply_markup
    keyboard = reply_markup.inline_keyboard
    keyboard[0] = [InlineKeyboardButton(
        "Unsubscribe" if fav else "Subscribe",
        f"{'unfav' if fav else 'fav'}_{data}"
    )]
    await bot.edit_message_reply_markup(callback.from_user.id, callback.message.id,
                                        InlineKeyboardMarkup(keyboard))
    db_manga = await db.get(MangaName, manga.url)
    if not db_manga:
        await db.add(MangaName(url=manga.url, name=manga.name))


def is_pagination_data(callback: CallbackQuery):
    data = callback.data
    match = re.match(r'\d+_\d+', data)
    if not match:
        return False
    pagination_id = int(data.split('_')[0])
    if pagination_id not in paginations:
        return False
    pagination = paginations[pagination_id]
    if not pagination.message:
        return False
    if pagination.message.chat.id != callback.from_user.id:
        return False
    if pagination.message.id != callback.message.id:
        return False
    return True


@bot.on_callback_query()
async def on_callback_query(client, callback: CallbackQuery):
	if callback.data in queries:
		await plugin_click(client, callback)
	elif callback.data in mangas:
		await manga_click(client, callback)
	elif callback.data in chapters:
		await chapter_click(client, callback.data, callback.from_user.id)
	elif callback.data in full_pages:
		await full_page_click(client, callback)
	elif callback.data in favourites:
		await favourite_click(client, callback)
	elif is_pagination_data(callback):
		await pagination_click(client, callback)
	elif callback.data in language_query:
		await language_click(client, callback)
	elif callback.data.startswith('options'):
		await options_click(client, callback)
	elif callback.data.startswith("athumb"):
		info = callback.data.split(":")[1]
		try:
			if info == "MC":
				thumb = env_vars["TH1"]
				cap = env_vars["F1"]
				b1 = env_vars["B1"][0]
				b2 = env_vars["B1"][1]
			elif info == "MW":
				thumb = env_vars["TH2"]
				cap = env_vars["F2"]
				b1 = env_vars["B2"][0]
				b2 = env_vars["B2"][1]
			elif info == "MY":
				thumb = env_vars["TH3"]
				cap = env_vars["F3"]
				b1 = env_vars["B3"][0]
				b2 = env_vars["B3"][1]
			elif info == "MM":
				thumb = env_vars["TH4"]
				cap = env_vars["F4"]
				b1 = env_vars["B4"][0]
				b2 = env_vars["B4"][1]
			elif info == "M18":
				thumb = env_vars["TH5"]
				cap = env_vars["F5"]
				b1 = env_vars["B5"][0]
				b2 = env_vars["B5"][1]
			elif info == "MWd":
				thumb = env_vars["TH6"]
				cap = env_vars["F6"]
				b1 = env_vars["B6"][0]
				b2 = env_vars["B6"][1]
			#user_options = UserInfo(user_id=str(callback.from_user.id), thumb=thumb, cap=cap, b1=b1, b2=b2)
			await DB().add_users(user_id=str(callback.from_user.id), thumb=thumb, cap=cap, b1=b1, b2=b2)
			return await callback.message.edit_text(text=f"Doned.")
		except Exception as e:
			return await callback.message.edit_text(text=f"Errors: <code>{e}</code>")
		
	else:
		await bot.answer_callback_query(callback.id, 'This is an old button, please redo the search', show_alert=True)
		return
	try: await callback.answer()
	except BaseException as e: logger.warning(e)


async def remove_subscriptions(sub: str):
    db = DB()

    await db.erase_subs(sub)


async def update_mangas():
    logger.debug("Updating mangas")
    db = DB()
    subscriptions = await db.get_all(Subscription)
    last_chapters = await db.get_all(LastChapter)
    manga_names = await db.get_all(MangaName)

    subs_dictionary = dict()
    chapters_dictionary = dict()
    url_client_dictionary = dict()
    client_url_dictionary = {client: set() for client in plugins.values()}
    manga_dict = dict()

    for subscription in subscriptions:
        if subscription.url not in subs_dictionary:
            subs_dictionary[subscription.url] = []
        subs_dictionary[subscription.url].append(subscription.user_id)

    for last_chapter in last_chapters:
        chapters_dictionary[last_chapter.url] = last_chapter

    for manga in manga_names:
        manga_dict[manga.url] = manga

    for url in subs_dictionary:
        for ident, client in plugins.items():
            if ident in subsPaused:
                continue
            if await client.contains_url(url):
                url_client_dictionary[url] = client
                client_url_dictionary[client].add(url)

    for client, urls in client_url_dictionary.items():
        logger.debug(f'Updating {client.name}')
        logger.debug(f'Urls:\t{list(urls)}')
        new_urls = [url for url in urls if not chapters_dictionary.get(url)]
        logger.debug(f'New Urls:\t{new_urls}')
        to_check = [chapters_dictionary[url] for url in urls if chapters_dictionary.get(url)]
        if len(to_check) == 0:
            continue
        try:
            updated, not_updated = await client.check_updated_urls(to_check)
        except BaseException as e:
            logger.exception(f"Error while checking updates for site: {client.name}, err: {e}")
            updated = []
            not_updated = list(urls)
        for url in not_updated:
            del url_client_dictionary[url]
        logger.debug(f'Updated:\t{list(updated)}')
        logger.debug(f'Not Updated:\t{list(not_updated)}')

    updated = dict()

    for url, client in url_client_dictionary.items():
        try:
            if url not in manga_dict:
                continue
            manga_name = manga_dict[url].name
            if url not in chapters_dictionary:
                agen = client.iter_chapters(url, manga_name)
                last_chapter = await anext(agen)
                await db.add(LastChapter(url=url, chapter_url=last_chapter.url))
                await asyncio.sleep(10)
            else:
                last_chapter = chapters_dictionary[url]
                new_chapters: List[MangaChapter] = []
                counter = 0
                async for chapter in client.iter_chapters(url, manga_name):
                    if chapter.url == last_chapter.chapter_url:
                        break
                    new_chapters.append(chapter)
                    counter += 1
                    if counter == 20:
                        break
                if new_chapters:
                    last_chapter.chapter_url = new_chapters[0].url
                    await db.add(last_chapter)
                    updated[url] = list(reversed(new_chapters))
                    for chapter in new_chapters:
                        if chapter.unique() not in chapters:
                            chapters[chapter.unique()] = chapter
                await asyncio.sleep(1)
        except BaseException as e:
            logger.exception(f'An exception occurred getting new chapters for url {url}: {e}')

    blocked = set()
    for url, chapter_list in updated.items():
        for chapter in chapter_list:
            logger.debug(f'Updating {chapter.manga.name} - {chapter.name}')
            for sub in subs_dictionary[url]:
                if sub in blocked:
                    continue
                try:
                    await pdf_queue.put(chapter, int(sub))
                    logger.debug(f"Put chapter {chapter} to queue for user {sub} - queue size: {pdf_queue.qsize()}")
                except pyrogram.errors.UserIsBlocked:
                    logger.info(f'User {sub} blocked the bot')
                    await remove_subscriptions(sub)
                    blocked.add(sub)
                except BaseException as e:
                    logger.exception(f'An exception occurred sending new chapter: {e}')


async def manga_updater():
    minutes = 5
    while True:
        wait_time = minutes * 60
        try:
            start = dt.datetime.now()
            await update_mangas()
            elapsed = dt.datetime.now() - start
            wait_time = max((dt.timedelta(seconds=wait_time) - elapsed).total_seconds(), 0)
            logger.debug(f'Time elapsed updating mangas: {elapsed}, waiting for {wait_time}')
        except BaseException as e:
            logger.exception(f'An exception occurred during chapters update: {e}')
        if wait_time:
            await asyncio.sleep(wait_time)

async def chapter_creation(worker_id: int = 0):
    """
    This function will always run in the background
    It will be listening for a channel which notifies whether there is a new request in the request queue
    :return:
    """
    logger.debug(f"Worker {worker_id}: Starting worker")
    while True:
        chapter, chat_id = await pdf_queue.get(worker_id)
        logger.debug(f"Worker {worker_id}: Got chapter '{chapter.name}' from queue for user '{chat_id}'")
        try:
            await send_manga_chapter(bot, chapter, chat_id)
        except:
            logger.exception(f"Error sending chapter {chapter.name} to user {chat_id}")
        finally:
            pdf_queue.release(chat_id)
