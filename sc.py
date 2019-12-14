"""
A simple text crawler to scrap light novels
20191212

Speed up with asyncio, aiofiles, and aiohttp
20191213
"""

import asyncio
import aiofiles
import aiohttp
from bs4 import BeautifulSoup as soup


async def get_plain(link: str, session: aiohttp.ClientSession) -> str:
    resp = await session.get(url=link)
    resp.raise_for_status()
    plain_text = await resp.text("gbk")
    return plain_text


async def get_links(menu: str, session: aiohttp.ClientSession) -> str:
    assert not menu.endswith("index.htm"), "Trim URL first!"

    plain = await get_plain(menu, session)
    s = soup(plain, "html.parser")
    for link in s.find_all("td", class_="ccss"):
        if link.a is not None:
            yield menu+link.a.get("href")


async def get_content(link: str, session: aiohttp.ClientSession) -> (str, str):
    plain = await get_plain(link, session)
    s = soup(plain, "html.parser")
    title = s.find("div", id="title").string
    content = str(s.find("div", id="content"))
    return title, content


async def write_html(fname: str, title: str, content: str, id: int = 0):
    async with aiofiles.open(fname, "w", encoding="utf8") as f:
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


async def main(menu: str):
    async with aiofiles.open("menu.html", "w", encoding="utf8") as f, \
            aiohttp.ClientSession() as session:
        await f.writelines("<!DOCTYPE html>\n<html>\n")
        await f.writelines("<head>\n</head>\n")
        await f.writelines("<body>\n")

        count = 0
        tasks = []
        async for link in get_links(menu, session):
            title, content = await get_content(link, session)
            if "插图" in title:
                continue
            fname = "{:0>3}.html".format(count)
            await f.writelines("\t<a href=""{}"">{}</a><br/>\n".format(fname, title))
            tasks.append(write_html(fname, title, content, count))
            count += 1
            # break
        await asyncio.gather(*tasks)
        await f.writelines("</body>\n</html>")


if __name__ == "__main__":
    asyncio.run(main("https://www.wenku8.net/novel/1/1787/"))
