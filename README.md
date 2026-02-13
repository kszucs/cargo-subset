# cargo-subset

Python CLI to explore Rust workspace module dependencies using `cargo metadata --format-version 1` and Tree-sitter.

# install

```console
$ uv venv
$ source .venv/bin/activate
$ uv pip install -e .
```

# usage

```console
$ uv run cargo-subset pack --workspace-path $HOME/Workspace/xet-core --crate data --module streaming --output-dir xet --name subxet
$ cd xet/subxet
$ cargo check
$ cargo test
```

