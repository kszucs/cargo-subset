# Test Fixture: Workspace Gold Standard

This fixture represents a realistic Rust workspace with multiple crates, designed to test all the problematic patterns that the cargo_subset packager needs to handle.

## Structure

```
workspace/
├── Cargo.toml              # Workspace manifest
├── core/                   # Core library crate
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs         # Self-referential pub uses, macro exports
│       ├── config.rs      # lazy_static! usage
│       ├── types.rs       # Nested module with pub use
│       │   └── nested.rs  # Nested submodule
│       └── internal.rs    # Private module with pub(crate)
├── utils/                  # Utilities crate
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs         # Macro exports, re-exports
│       ├── helpers.rs     # Helper functions
│       └── constants.rs   # Constants with lazy_static!
└── client/                 # Client crate (depends on core & utils)
    ├── Cargo.toml
    └── src/
        ├── lib.rs         # Bare relative imports, workspace crate usage
        ├── http_client.rs # Submodule
        └── interface.rs   # Trait definitions

```

## Problematic Patterns Included

### 1. Self-Referential Pub Uses
**Location**: `core/src/lib.rs`
```rust
pub use crate::config::Config;
pub use crate::types::{Item, Record};
```
These need to be rewritten to relative paths after the module is nested.

### 2. Lazy Static Usage
**Locations**:
- `core/src/config.rs`
- `utils/src/constants.rs`

```rust
lazy_static! {
    pub static ref DEFAULT_CONFIG: Config = ...;
}
```
Requires `use lazy_static::lazy_static;` import to be added.

### 3. Bare Relative Imports (Non-mod.rs files)
**Location**: `client/src/lib.rs` (if it were not lib.rs)
```rust
pub use http_client::HttpClient;
pub use interface::{Client, Provider};
```
For non-mod.rs files, sibling modules need `super::` prefix.

### 4. Workspace Crate Imports
**Location**: `client/src/lib.rs`
```rust
use core::types::Item;
use core::Config;
use utils::helpers;
```
These need to be rewritten to `crate::core::`, `crate::utils::` etc.

### 5. External Crate Re-exports
**Location**: `core/src/lib.rs`
```rust
pub use serde::{Deserialize, Serialize};
```
These must be preserved unchanged.

### 6. Macro Exports
**Locations**: `core/src/lib.rs`, `utils/src/lib.rs`
```rust
#[macro_export]
macro_rules! debug_log { ... }
```
These are exported at crate root level.

### 7. Nested Modules
**Location**: `core/src/types/nested.rs`
Module declarations and file discovery must handle nested directory structures.

### 8. Various Visibility Modifiers
- `pub mod` - public modules
- `mod` - private modules
- `pub(crate)` - crate-visible items

## Usage in Tests

The fixture is used in `test_integration.py` for:

1. **Structural Validation**: Verify all expected files exist
2. **Pattern Detection**: Confirm problematic patterns are present
3. **Transformation Testing**: Apply packager functions and validate results
4. **End-to-End Properties**: Test invariants that should hold after transformation

## Adding New Test Cases

To add new problematic patterns:

1. Add the pattern to an appropriate file in the fixture
2. Add a test in `test_integration.py` to verify it exists
3. Add a transformation test to verify it's handled correctly
4. Update this README

## Test Categories

- **TestWorkspaceFixture**: Verifies fixture structure and patterns exist
- **TestPackagerTransformations**: Tests individual transformation functions
- **TestIterModsOnFixture**: Tests module discovery on fixture files
- **TestExpandWithModFiles**: Tests recursive module expansion
- **TestEndToEndProperties**: Tests invariants after full transformation
