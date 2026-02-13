mod http_client;
pub mod interface;

// Bare relative import (should get super:: prefix when converting)
pub use http_client::HttpClient;
pub use interface::{Client, Provider};

// Workspace crate imports
use core::types::Item;
use core::Config;
use utils::helpers;

pub struct ApiClient {
    config: Config,
    http: HttpClient,
}

impl ApiClient {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            http: HttpClient::new(),
        }
    }

    pub fn process_item(&self, item: Item) -> String {
        helpers::format_string(&item.value)
    }
}
