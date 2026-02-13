pub trait Provider {
    fn get_url(&self) -> &str;
}

pub trait Client {
    fn connect(&self) -> Result<(), String>;
}
