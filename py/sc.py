"""
A simple text crawler to scrap light novels
20191212

Speed up with asyncio, aiofiles, and aiohttp
20191213

Ditch asyncio for trio
20200618
"""

import argparse
import os
from typing import AsyncIterator

import trio
from asks import Session
from bs4 import BeautifulSoup as soup

# Number of pages to begin crawling
LAST_STORE: int = 0

SAVE_DIR: str = "save"


session = None


async def get_plain_text(link: str) -> str:
    assert session is not None, "session is not initialized!"

    resp = await session.get(link)
    resp.encoding = "gbk"
    return resp.content


async def get_text_content(link: str) -> str:
    plain = await get_plain_text(link)
    doc = soup(plain, "html.parser")
    content = str(doc.find("div", id="content"))
    return content


async def write_text_content(fname: str, title: str, content: str, id: int = 0):
    async with await trio.open_file(f"{SAVE_DIR}/{fname}", "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines(f"<head>\n<title>{title}</title>\n</head>\n<body>\n")
        await f.writelines(f"<h3>{title}</h3>\n")
        await f.writelines(content)
        await f.writelines("\n<br><br>\n")

        if id > 0:
            previous = f"{id - 1:0>3}.html"
            await f.writelines(f'\t<a href="{previous}">上一页</a><br>\n')
        next = f"{id + 1:0>3}.html"
        await f.writelines(f'\t<a href="{next}">下一页</a><br>\n')

        await f.writelines("</body>\n</html>")
    assert f.closed


async def get_img_urls(link: str) -> AsyncIterator[str]:
    plain = await get_plain_text(link)
    s = soup(plain, "html.parser")
    for link in s.find_all("img", class_="imagecontent"):
        yield link.get("src")


async def write_pic_html(page_id: int, pic_page_id: int, img_count: int):
    async with await trio.open_file(f"{SAVE_DIR}/{page_id:0>3}.html", "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n<head>\n</head>\n<body>\n")

        for idx in range(img_count):
            await f.writelines(f"<img src=\"{pic_page_id:0>3}.{idx:0>3}.jpg\">\n")
        if page_id > 0:
            previous = f"{page_id - 1:0>3}.html"
            await f.writelines(f'\t<a href="{previous}">上一页</a><br>\n')
        next = f"{page_id + 1:0>3}.html"
        await f.writelines(f'\t<a href="{next}">下一页</a><br>\n')

        await f.writelines("</body>\n</html>")
    assert f.closed


async def save_pics(link: str, pic_page_id: int, page_id: int):
    assert session is not None, "session is not initialized!"

    img_count = 0
    async for url in get_img_urls(link):
        data = await session.get(url)
        async with await trio.open_file(f"{SAVE_DIR}/{pic_page_id:0>3}.{img_count:0>3}.jpg", "wb") as f:
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


async def process(menu_url: str):
    if not os.path.isdir(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    plain = await get_plain_text(menu_url)
    doc = soup(plain, "html.parser")

    menu_body = ""
    page_id = 0
    pic_page_id = 0

    async with trio.open_nursery() as n:
        for tag in doc.find_all("td"):
            if tag.get("class") == ["vcss"]:
                title = tag.string
                assert title is not None, "Cannot get title"
                menu_body += f"<br><br>\n\t<h3>{title}</h3>\n"
            elif tag.get("class") == ["ccss"]:
                if tag.a is not None:

                    title = tag.a.string
                    link = menu_url+tag.a.get("href")
                    fname = f"{page_id:0>3}.html"
                    menu_body += f'\t<a href="{fname}">{title}</a><br>\n'
                    page_id += 1
                    if "插图" in title:
                        n.start_soon(save_pics, link, pic_page_id, page_id)
                        pic_page_id += 1
                        continue
                    else:
                        content = await get_text_content(link)
                        n.start_soon(write_text_content, fname,
                                     title, content, page_id)
                        pass
        n.start_soon(write_menu, menu_body)


def main():
    global session

    parser = argparse.ArgumentParser()
    parser.add_argument("index", help="URL to index page")
    args = parser.parse_args()

    url: str = args.index
    if url.endswith("index.htm"):
        url = url[:-9]

    assert len(url) > 0 and url.endswith('/')
    session = Session()
    trio.run(process, url)


if __name__ == "__main__":
    main()
