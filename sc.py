"""
A simple text crawler to scrap light novels
20191212

Speed up with asyncio, aiofiles, and aiohttp
20191213

Ditch asyncio for trio
20200618
"""

import os
from typing import AsyncIterator

import trio
from asks import Session
from bs4 import BeautifulSoup as soup

# trim "index/htm" ending first
LINK = ""

# Number of pages to begin crawling
LAST_STORE: int = 0

SAVE_DIR: str = "save"


session = Session()


async def get_plain_text(link: str) -> str:
    resp = await session.get(link)
    resp.encoding = "gbk"
    return resp.content


async def get_page_links(menu: str) -> AsyncIterator[tuple[str, str]]:
    assert not menu.endswith("index.htm"), "Trim URL first!"
    assert menu.endswith('/')

    plain = await get_plain_text(menu)
    s = soup(plain, "html.parser")
    for link in s.find_all("td", class_="ccss"):
        if link.a is not None:
            yield link.a.string, menu+link.a.get("href")


async def get_text_content(link: str) -> str:
    plain = await get_plain_text(link)
    s = soup(plain, "html.parser")
    content = str(s.find("div", id="content"))
    return content


async def write_text_content(fname: str, title: str, content: str, id: int = 0):
    async with await trio.open_file(f"{SAVE_DIR}/{fname}", "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines(f"<head>\n<title>{title}</title>\n</head>\n")
        await f.writelines("<body>\n")
        await f.writelines(f"<h3>{title}</h3>\n")
        await f.writelines(content)
        await f.writelines("\n<br/><br/>\n")

        if id > 0:
            previous = f"{id - 1:0>3}.html"
            await f.writelines(f'\t<a href="{previous}">上一节</a><br/>\n')
        next = f"{id + 1:0>3}.html"
        await f.writelines(f'\t<a href="{next}">下一节</a> <br/>\n')

        await f.writelines("</body>\n</html>")
    assert f.closed


async def get_img_urls(link: str) -> AsyncIterator[str]:
    plain = await get_plain_text(link)
    s = soup(plain, "html.parser")
    for link in s.find_all("img", class_="imagecontent"):
        yield link.get("src")


async def write_pic_html(page_id: int, pic_page_id: int, img_count: int):
    async with await trio.open_file(f"{SAVE_DIR}/{page_id:0>3}.html", "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines("<head>\n</head>\n")
        await f.writelines("<body>\n")
        for idx in range(img_count):
            await f.writelines(f"<img src=\"{pic_page_id:0>2}.{idx:0>2}.jpg\">\n")
        await f.writelines("</body>\n</html>")


async def save_pics(link: str, pic_page_id: int, page_id: int):
    img_count = 0
    async for url in get_img_urls(link):
        data = await session.get(url)
        async with await trio.open_file(f"{SAVE_DIR}/{pic_page_id:0>2}.{img_count:0>2}.jpg", "wb") as f:
            img_count += 1
            await f.write(data.body)
        assert f.closed
    await write_pic_html(page_id, pic_page_id, img_count)


async def write_menu(body: str):
    async with await trio.open_file(f"{SAVE_DIR}/menu.html", "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines("<head>\n</head>\n")
        await f.writelines("<body>\n")
        await f.writelines(body)
        await f.writelines("</body>\n</html>")

    assert f.closed


async def main(menu: str):
    menu_body = ""
    if not os.path.isdir(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    page_id = 0
    pic_page_id = 0
    async with trio.open_nursery() as n:
        async for title, link in get_page_links(menu):
            if "插图" in title:
                n.start_soon(save_pics, link, pic_page_id, page_id)
                pic_page_id += 1
                continue
            fname = f"{page_id:0>3}.html"
            menu_body += f'\t<a href="{fname}">{title}</a><br/>\n'
            if page_id < LAST_STORE:
                page_id += 1
                continue
            content = await get_text_content(link)
            n.start_soon(write_text_content, fname, title, content, page_id)
            page_id += 1
        n.start_soon(write_menu, menu_body)


if __name__ == "__main__":
    trio.run(main, LINK)
