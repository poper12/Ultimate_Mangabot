from typing import List, AsyncIterable
from urllib.parse import urlparse, urljoin, quote, unquote
from bs4 import BeautifulSoup
from bs4.element import PageElement
import logging
from bs4 import BeautifulSoup

from plugins.client import *



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class ManhuaFastClient(MangaClient):

    base_url = urlparse("https://manhuafast.net/")
    search_url = base_url.geturl()
    updates_url = base_url.geturl()

    pre_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:97.0) Gecko/20100101 Firefox/97.0'
    }

    def __init__(self, *args, name="ManhuaFast", **kwargs):
        super().__init__(*args, name=name, headers=self.pre_headers, **kwargs)

    def mangas_from_page(self, page: bytes) -> List[MangaCard]:
        try:
            bs = BeautifulSoup(page, "html.parser")
            cards = bs.find_all("div", {"class": "tab-thumb c-image-hover"})

            mangas = [card.findNext('a') for card in cards]
            names = [manga.get('title', 'No Title') for manga in mangas]
            urls = [manga.get("href") for manga in mangas]
            images = [manga.findNext("img").get("data-src", "") for manga in mangas]
            manga_list = [MangaCard(self, name, url, image) for name, url, image in zip(names, urls, images)]
            logger.info(f"Fetched {len(manga_list)} mangas from page.")
            return manga_list
        except Exception as e:
            logger.error(f"Error parsing mangas from page: {e}")
            return []

    async def chapters_from_page(self, page: str, manga_card: MangaCard = None) -> List[MangaChapter]:
        try:
            texts, links = await verify_links(link=page)
            if len(texts) != len(links):
                logger.warning(f"Mismatch between texts and links: {len(texts)} texts, {len(links)} links")
            chapters = [MangaChapter(self, text, link, manga_card, []) for text, link in zip(texts, links)]
            logger.info(f"Fetched {len(chapters)} chapters for {manga_card.name}")
            return chapters
        except Exception as e:
            logger.error(f"Error fetching chapters from page: {e}")
            return []

    async def updates_from_page(self) -> dict:
        try:
            page = await self.get_url(self.updates_url)
            bs = BeautifulSoup(page, "html.parser")
            manga_items = bs.find_all("div", {"class": "slider__content"})

            urls = {}
            for manga_item in manga_items:
                manga_url = urljoin(self.base_url.geturl(), manga_item.findNext("a").get("href"))
                chapter_url = urljoin(self.base_url.geturl(), manga_item.findNext("a").findNext("a").get("href"))

                if manga_url not in urls:
                    urls[manga_url] = chapter_url

            logger.info(f"Fetched {len(urls)} manga updates.")
            return urls
        except Exception as e:
            logger.error(f"Error fetching updates: {e}")
            return {}

    async def pictures_from_chapters(self, content: bytes, response=None) -> List[str]:
        try:
            bs = BeautifulSoup(content, "html.parser")
            cards = bs.findAll("div", {"class": "page-break no-gaps"})
            urls = [quote(containers.findNext("img").get("data-src").lstrip(), safe=':/%') for containers in cards]
            images_url = [unquote(url).replace(":///", "://") for url in urls]
            logger.info(f"Fetched {len(images_url)} images from chapter.")
            return images_url
        except Exception as e:
            logger.error(f"Error fetching images from chapter: {e}")
            return []

    async def search(self, query: str = "", page: int = 1) -> List[MangaCard]:
        try:
            query = quote(query)
            request_url = self.search_url + f'?s={query}&post_type=wp-manga&post_type=wp-manga' if query else self.search_url
            content = await self.get_url(request_url)
            return self.mangas_from_page(content)
        except Exception as e:
            logger.error(f"Error performing search: {e}")
            return []

    async def get_chapters(self, manga_card: MangaCard, page: int = 1) -> List[MangaChapter]:
        try:
            request_url = f'{manga_card.url}'
            texts, links = await verify_links(link=request_url)
            chapters = list(map(lambda x: MangaChapter(self, x[0], x[1], manga_card, []), zip(texts, links)))
            logger.info(f"Fetched chapters for {manga_card.name} - Page {page}")
            return chapters[(page - 1) * 20:page * 20]
        except Exception as e:
            logger.error(f"Error fetching chapters: {e}")
            return []

    async def iter_chapters(self, manga_url: str, manga_name: str) -> AsyncIterable[MangaChapter]:
        manga_card = MangaCard(self, manga_name, manga_url, '')
        try:
            page = f'{manga_card.url}'
            for chapter in await self.chapters_from_page(page, manga_card):
                yield chapter
        except Exception as e:
            logger.error(f"Error iterating chapters: {e}")

    async def contains_url(self, url: str) -> bool:
        return url.startswith(self.base_url.geturl())

    async def check_updated_urls(self, last_chapters: List[LastChapter]) -> (List[str], List[str]):
        try:
            updates = await self.updates_from_page()
            updated = []
            not_updated = []
            for lc in last_chapters:
                if lc.url in updates:
                    if updates[lc.url] != lc.chapter_url:
                        updated.append(lc.url)
                    else:
                        not_updated.append(lc.url)
            logger.info(f"Updated: {len(updated)} | Not Updated: {len(not_updated)}")
            return updated, not_updated
        except Exception as e:
            logger.error(f"Error checking updated URLs: {e}")
            return [], []
