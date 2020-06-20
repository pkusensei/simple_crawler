"""
A simple text crawler to scrap light novels
20191212

Speed up with asyncio, aiofiles, and aiohttp
20191213

Ditch asyncio for trio
20200618
"""

import os
import trio
import asks
from bs4 import BeautifulSoup as soup


LINK = ""

# Number of pages to begin crawling
LAST_STORE: int = 0

SAVE_DIR: str = "save"


async def get_plain(link: str) -> str:
    resp = await asks.get(link)
    resp.encoding = "gbk"
    return resp.content


async def get_links(menu: str) -> (str, str):
    assert not menu.endswith("index.htm"), "Trim URL first!"

    plain = await get_plain(menu)
    s = soup(plain, "html.parser")
    for link in s.find_all("td", class_="ccss"):
        if link.a is not None:
            yield link.a.string, menu+link.a.get("href")


async def get_content(link: str) -> str:
    plain = await get_plain(link)
    s = soup(plain, "html.parser")
    content = str(s.find("div", id="content"))
    return content


async def write_content(fname: str, title: str, content: str, id: int = 0):
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
    bodies = []
    if not os.path.isdir(SAVE_DIR):
        os.mkdir(SAVE_DIR)

    count = 0
    async for title, link in get_links(menu):
        if "插图" in title:
            menu_body += "<br/><br/>\n"
            continue
        fname = f"{count:0>3}.html"
        menu_body += f'\t<a href="{fname}">{title}</a><br/>\n'
        if count < LAST_STORE:
            count += 1
            continue
        content = await get_content(link)
        bodies.append((fname, title, content, count))
        count += 1

    async with trio.open_nursery() as n:
        n.start_soon(write_menu, menu_body)
        for fname, title, content, count in bodies:
            n.start_soon(write_content, fname, title, content, count)


if __name__ == "__main__":
    assert len(LINK) > 0 and LINK.endswith('/')
    trio.run(main, LINK)
