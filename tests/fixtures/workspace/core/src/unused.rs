// Completely unused module - declared but never imported or used
pub struct UnusedType {
    pub value: i32,
}

impl UnusedType {
    pub fn new(value: i32) -> Self {
        UnusedType { value }
    }

    pub fn get(&self) -> i32 {
        self.value
    }
}
