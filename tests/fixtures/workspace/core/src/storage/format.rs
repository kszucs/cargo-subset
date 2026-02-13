// Private module with type definitions that are re-exported

#[derive(Debug, Clone)]
pub struct StorageFormat {
    pub version: u32,
    pub compression: bool,
}

impl StorageFormat {
    pub fn new(version: u32) -> Self {
        Self {
            version,
            compression: false,
        }
    }
}
