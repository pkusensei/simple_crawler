use std::sync::Arc;

use futures::future;
use reqwest::Client;
use scraper::{Html, Selector};
use tokio::{
    fs::{self, OpenOptions},
    io::AsyncWriteExt,
};

use crate::{Error, SAVE_DIR};

const TEXT_ID: &str = "content";
const IMG_CLASS: &str = "imagecontent";
const LINK_TD_CLASS: &str = "ccss";

pub async fn process_index_page(client: Arc<Client>, url: &str) -> Result<(), Error> {
    let url = url.strip_suffix("index.htm").unwrap_or(url);
    let (body, links) = compose_index_page(&client, url).await?;

    if fs::metadata(SAVE_DIR).await.is_err() {
        fs::create_dir_all(SAVE_DIR).await?
    }

    let handle = tokio::spawn(async move { write_index_page(&body).await });
    process_pages(client, &links).await?;
    handle.await?;
    Ok(())
}

async fn compose_index_page(
    client: &Client,
    index_url: &str,
) -> Result<(String, Vec<String>), Error> {
    let text = crate::get_html_string(&client, index_url).await?;
    let doc = Html::parse_document(&text);
    let td_selector = Selector::parse(&format!("td[class=\"{}\"]", LINK_TD_CLASS)).or_else(
        |_| -> Result<_, Error> {
            Err(format!("Invalid td or class=\"{}\" attribute", LINK_TD_CLASS).into())
        },
    )?;

    let mut body = String::new();
    let mut links = vec![];
    let mut count = 0;
    for td in doc.select(&td_selector) {
        let inner = Html::parse_fragment(&td.inner_html());
        let a_selector = Selector::parse("a").or_else(|_| -> Result<_, Error> {
            Err(format!("Cannot find <a/> tag from {}", td.inner_html()).into())
        })?;

        if let Some(a_tag) = inner.select(&a_selector).next() {
            let page_link = a_tag.value().attr("href").ok_or_else(|| -> Error {
                format!("Cannot find href attribute from {}", td.inner_html()).into()
            })?;
            let title: String = a_tag.text().collect();
            body = format!("{}[{}](./{:03}.md)\n", body, title, count);
            links.push(format!("{}{}", index_url, page_link));
            count += 1;
        }
    }
    Ok((body, links))
}

async fn write_index_page(body: &str) {
    if let Ok(mut file) = OpenOptions::new()
        .write(true)
        .truncate(true)
        .create(true)
        .open(format!("{}/index.md", SAVE_DIR))
        .await
    {
        if let Ok(_) = file.write_all(body.as_bytes()).await {
            return;
        }
    }
    eprintln!("Failed writing file index.md\n")
}

async fn process_pages(client: Arc<Client>, urls: &[String]) -> Result<(), Error> {
    let mut pic_page_id = 0;
    let mut handles = vec![];

    for (count, url) in urls.iter().cloned().enumerate() {
        let text = crate::get_html_string(&client, &url).await?;
        let handle = if text.contains(IMG_CLASS) {
            let clnt_clone = client.clone();

            pic_page_id += 1;
            tokio::spawn(async move {
                process_pic_page(clnt_clone, text, pic_page_id - 1, count as u16, &url).await
            })
        } else {
            tokio::spawn(async move { process_text_page(text, &url, count as u16).await })
        };
        handles.push(handle);
    }
    future::join_all(handles)
        .await
        .into_iter()
        .collect::<Result<Vec<_>, _>>()
        .map_or_else(|e| Err(e.into()), |_| Ok(()))
}

async fn process_text_page(html_str: String, url: &str, page_id: u16) {
    let content = match get_page_text(html_str, url) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Error processing text on page {}:\n{}\n", url, e);
            return;
        }
    };
    let text = match page_id {
        0 => format!("{}\n[下一页]({:03}.md)", content, page_id + 1),
        _ => format!(
            "{}\n[上一页]({:03}.md)\n[下一页]({:03}.md)",
            content,
            page_id - 1,
            page_id + 1
        ),
    };
    if let Ok(mut file) = OpenOptions::new()
        .write(true)
        .truncate(true)
        .create(true)
        .open(format!("{}/{:03}.md", SAVE_DIR, page_id))
        .await
    {
        if let Ok(_) = file.write_all(text.as_bytes()).await {
            return;
        }
    }
    eprintln!("Error writing file {:03}.md\n", page_id)
}

fn get_page_text(html_str: String, url: &str) -> Result<String, Error> {
    let doc = Html::parse_document(&html_str);
    let selector =
        Selector::parse(&format!("div[id=\"{}\"]", TEXT_ID)).or_else(|_| -> Result<_, Error> {
            Err(format!("Invalid div or id=\"{}\" attribute", TEXT_ID).into())
        })?;
    let content = doc
        .select(&selector)
        .next()
        .ok_or_else(|| -> String { format!("No div with id=\"{}\" found from {}", TEXT_ID, url) })?
        .text()
        .collect();
    Ok(content)
}

async fn process_pic_page(
    client: Arc<Client>,
    html_str: String,
    pic_page_id: u16,
    page_id: u16,
    url: &str,
) {
    let num = match save_pics_on_page(client, html_str, pic_page_id).await {
        Ok(n) => n,
        Err(e) => {
            eprintln!(
                "Error saving pics from {} to {:03}.md:\n{}\n",
                url, page_id, e
            );
            return;
        }
    };

    let md_path = format!("{}/{:03}.md", SAVE_DIR, page_id);
    if let Ok(mut file) = OpenOptions::new()
        .write(true)
        .truncate(true)
        .create(true)
        .open(&md_path)
        .await
    {
        let text: String = (0..num)
            .map(|n| {
                format!(
                    "[{:03}.{:03}.jpg](./{:03}.{:03}.jpg)<br>\n",
                    pic_page_id, n, pic_page_id, n
                )
            })
            .collect();
        if let Ok(_) = file.write_all(text.as_bytes()).await {
            return;
        }
    }
    eprintln!("Error writing file {}\n", md_path);
}

async fn save_pics_on_page(
    client: Arc<Client>,
    html_str: String,
    pic_page_id: u16,
) -> Result<u16, Error> {
    let urls = get_pic_urls_on_page(html_str)?;
    let handles: Vec<_> = urls
        .into_iter()
        .enumerate()
        .map(|(idx, url)| {
            let clnt_clone = client.clone();
            tokio::spawn(
                async move { save_one_pic(&clnt_clone, &url, idx as u16, pic_page_id).await },
            )
        })
        .collect();
    let count = handles.len();
    future::join_all(handles)
        .await
        .into_iter()
        .collect::<Result<Vec<_>, _>>()
        .map_or_else(|e| Err(e.into()), |_| Ok(count as u16))
}

fn get_pic_urls_on_page(html_str: String) -> Result<Vec<String>, Error> {
    let doc = Html::parse_document(&html_str);
    let selector = Selector::parse(&format!("img[class=\"{}\"]", IMG_CLASS)).or_else(
        |_| -> Result<_, Error> {
            Err(format!("Invalid img or class=\"{}\" attribute", IMG_CLASS).into())
        },
    )?;
    let content: Vec<_> = doc
        .select(&selector)
        .map(|url| url.value().attr("src"))
        .filter_map(|u| u.map(String::from))
        .collect();

    Ok(content)
}

async fn save_one_pic(client: &Client, url: &str, img_idx: u16, pic_page_id: u16) {
    let save_path = format!("{}/{:03}.{:03}.jpg", SAVE_DIR, pic_page_id, img_idx);
    let url = url.strip_prefix("https://").unwrap_or(url);
    let bytes = match crate::get_pic_data(client, &url).await {
        Ok(b) => b,
        Err(e) => {
            eprintln!("Failed downloading {}:\n{}\n", url, e);
            return;
        }
    };
    if let Ok(mut file) = OpenOptions::new()
        .write(true)
        .truncate(true)
        .create(true)
        .open(&save_path)
        .await
    {
        if let Ok(_) = file.write_all(bytes.as_ref()).await {
            return;
        }
    }
    eprintln!("Error writing file {}\n", save_path)
}
