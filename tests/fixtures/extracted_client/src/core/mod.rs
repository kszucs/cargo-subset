// Core library with various patterns to test
pub mod config;
pub mod types;
// pruned missing mod pub mod storage
// pruned missing mod pub mod storage_client
// pruned missing mod mod internal
// pruned missing mod mod unused

// Self-referential pub use (should be fixed)
pub use config::Config;
pub use types::{Item, Record};

// External crate re-exports (should be preserved)
pub use serde::{Deserialize, Serialize};

// Workspace crate usage
use crate::utils::helpers::format_string;

#[macro_export]
macro_rules! debug_log {
    ($($arg:tt)*) => {
        println!("[DEBUG] {}", format!($($arg)*))
    };
}

pub fn process() -> String {
    format_string("core")
}
