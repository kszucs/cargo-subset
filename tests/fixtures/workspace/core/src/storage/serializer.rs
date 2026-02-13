// Another private module with types

#[derive(Debug)]
pub struct SerializedObject {
    pub data: Vec<u8>,
}

impl SerializedObject {
    pub fn from_bytes(data: Vec<u8>) -> Self {
        Self { data }
    }
}
