# Rust source distribution

The Rust SDK is a source preview and `Cargo.toml` declares `publish = false`.
Its workflow runs formatting, Clippy, tests, conformance, and `cargo package`,
but accepts no crates.io credential and cannot publish a release.

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
cargo package
python3 ../../conformance/check_conformance.py
```

Consumers use a path dependency from a checkout. A future crates.io launch is
an owner decision and must remove the manifest guard through a reviewed release
change; do not add a token to the verification workflow.
