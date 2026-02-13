pub mod helpers;
pub mod constants;

// Re-export commonly used items
pub use helpers::{format_string, parse_number};
pub use constants::MAX_SIZE;

#[macro_export]
macro_rules! log_info {
    ($msg:expr) => {
        println!("[INFO] {}", $msg)
    };
}
