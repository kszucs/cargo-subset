pub mod nested;

pub use nested::NestedItem;

#[derive(Debug, Clone)]
pub struct Item {
    pub id: u64,
    pub value: String,
}

#[derive(Debug)]
pub struct Record {
    pub timestamp: u64,
    pub data: String,
}
