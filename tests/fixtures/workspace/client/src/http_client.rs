use crate::interface::{Provider, Client};

pub struct HttpClient {
    base_url: String,
}

impl HttpClient {
    pub fn new() -> Self {
        Self {
            base_url: "http://localhost".to_string(),
        }
    }
}

impl Provider for HttpClient {
    fn get_url(&self) -> &str {
        &self.base_url
    }
}

impl Client for HttpClient {
    fn connect(&self) -> Result<(), String> {
        Ok(())
    }
}
