use lazy_static::lazy_static;

pub const PREFIX: &str = ">>>";
pub const MAX_SIZE: usize = 1024;

// Test the test_configurable_constants macro pattern
// This would normally use the macro, but we'll simulate it
lazy_static! {
    pub static ref BUFFER_SIZE: usize = 4096;
    pub static ref TIMEOUT_MS: u64 = 5000;
}
