mod novel;

use std::sync::Arc;

use clap::Clap;
use reqwest::{Client, ClientBuilder};

type Error = Box<dyn std::error::Error>;

const SAVE_DIR: &str = "save";

#[tokio::main]
async fn main() -> Result<(), Error> {
    let args: Args = Args::parse();

    let client = Arc::new(ClientBuilder::new().build()?);
    novel::process_index_page(client, &args.url).await?;

    Ok(())
}

#[derive(Debug, Clap)]
struct Args {
    #[clap(parse(from_str), about = "URL to index page")]
    url: String,
}

async fn get_html_string(client: &Client, url: &str) -> Result<String, Error> {
    let text = client
        .get(url)
        .send()
        .await?
        .text_with_charset("GBK")
        .await?;
    Ok(text)
}

async fn get_pic_data(client: &Client, url: &str) -> Result<Vec<u8>, Error> {
    let res = client.get(url).send().await?;
    let bytes = res.bytes().await?;
    Ok(bytes.into_iter().collect())
}
