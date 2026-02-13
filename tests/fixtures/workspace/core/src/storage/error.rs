// Public submodule for errors

#[derive(Debug)]
pub enum StorageError {
    NotFound,
    InvalidFormat,
}
