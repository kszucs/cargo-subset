use crate::core::types::Item;
use lazy_static::lazy_static;

pub struct Config {
    pub name: String,
    pub items: Vec<Item>,
}

impl Config {
    pub fn new(name: String) -> Self {
        // Use macro_export macro from utils crate
        crate::log_info!("Creating new config");
        Self {
            name,
            items: Vec::new(),
        }
    }
}

// Test lazy_static usage
lazy_static! {
    pub static ref DEFAULT_CONFIG: Config = Config::new("default".to_string());
}
