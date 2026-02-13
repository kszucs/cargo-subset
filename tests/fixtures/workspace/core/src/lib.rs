// Core library with various patterns to test
pub mod config;
pub mod types;
pub mod storage;
pub mod storage_client;
mod internal;
mod unused;

// Self-referential pub use (should be fixed)
pub use crate::config::Config;
pub use crate::types::{Item, Record};

// External crate re-exports (should be preserved)
pub use serde::{Deserialize, Serialize};

// Workspace crate usage
use utils::helpers::format_string;

#[macro_export]
macro_rules! debug_log {
    ($($arg:tt)*) => {
        println!("[DEBUG] {}", format!($($arg)*))
    };
}

pub fn process() -> String {
    format_string("core")
}
