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


async def write_html(fname: str, title: str, content: str, id: int = 0):
    async with await trio.open_file("{}/{}".format(SAVE_DIR, fname), "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines("<head>\n<title>{}</title>\n</head>\n".format(title))
        await f.writelines("<body>\n")
        await f.writelines("<h3>{}</h3>\n".format(title))
        await f.writelines(content)

        if id > 0:
            previous = "{:0>3}.html".format(id - 1)
            await f.writelines("\t<a href=""{}"">上一节</a><br/>\n".format(previous))
        next = "{:0>3}.html".format(id + 1)
        await f.writelines("\t<a href=""{}"">下一节</a><br/>\n".format(next))

        await f.writelines("</body>\n</html>")
    assert f.closed


async def main(menu: str):
    bodies = []
    if not os.path.isdir(SAVE_DIR):
        os.mkdir(SAVE_DIR)
        
    async with await trio.open_file("{}/{}".format(SAVE_DIR, "menu.html"), "w", encoding="utf8") as f:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines("<head>\n</head>\n")
        await f.writelines("<body>\n")

        count = 0
        async for title, link in get_links(menu):
            if "插图" in title:
                await f.writelines("<br/><br/>\n")
                continue
            fname = "{:0>3}.html".format(count)
            await f.writelines("\t<a href=""{}"">{}</a><br/>\n".format(fname, title))
            if count < LAST_STORE:
                count += 1
                continue
            content = await get_content(link)
            bodies.append((fname, title, content, count))
            count += 1
            # break
        await f.writelines("</body>\n</html>")

    assert f.closed
    async with trio.open_nursery() as n:
        for fname, title, content, count in bodies:
            n.start_soon(write_html, fname, title, content, count)


if __name__ == "__main__":
    assert len(LINK) > 0
    trio.run(main, LINK)
