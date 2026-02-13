use super::Item;

#[derive(Debug)]
pub struct NestedItem {
    pub parent: Item,
    pub depth: usize,
}
