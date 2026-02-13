// This module uses types re-exported from storage module
// It simulates the cas_client pattern that was failing

use crate::core::storage::SerializedObject;
use crate::core::storage::StorageFormat;

pub struct Client {
    format: StorageFormat,
}

impl Client {
    pub fn new() -> Self {
        Self {
            format: StorageFormat::new(1),
        }
    }

    pub fn serialize(&self, data: Vec<u8>) -> SerializedObject {
        SerializedObject::from_bytes(data)
    }
}
