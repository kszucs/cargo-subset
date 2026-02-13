// This simulates the cas_object pattern:
// - Private submodules with actual type definitions
// - Public re-exports to expose those types

mod format;
mod serializer;

pub mod error;

// Re-export types from private modules
pub use format::*;
pub use serializer::*;
