# Publishing `nrouter` to crates.io

## Once

```bash
cargo login          # paste the token from https://crates.io/settings/tokens
```

Scope the token to `publish-update` for the `nrouter` crate rather than using an
all-permissions token.

## Every release

```bash
cd sdks/rust

# 1. Version lives in Cargo.toml and nowhere else.
#    crates.io refuses to overwrite a version — bump, never re-push.
$EDITOR Cargo.toml               # version = "2.2.1"

# 2. Prove it green. A published version cannot be deleted.
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test                       # unit + integration + doc tests
python3 ../../conformance/check_conformance.py

# 3. Look at exactly what will ship.
cargo package --list
cargo package                    # builds the .crate the way crates.io will

# 4. Publish.
cargo publish
```

docs.rs builds the documentation automatically from the published crate within a
few minutes. A crate that compiles locally can still fail the docs.rs build —
check <https://docs.rs/nrouter> after publishing rather than assuming.

## Traps

- **`cargo publish` is permanent.** A version can be *yanked* (blocked from new
  resolutions) but never removed, and lockfiles already pinning it keep working.
  There is no staging step, which is why the gates above run first.
- **Everything not excluded is uploaded.** `cargo package --list` is the file
  list; read it. `target/` is skipped automatically, a stray `.env` is not.
- **Doc tests are real tests.** The examples in `src/lib.rs` are compiled by
  `cargo test`. They are `no_run` because they need a live key, so they are
  proven to COMPILE, not to succeed against the gateway — keep them `no_run` or
  they fail in CI without credentials.
- **`rust-version` is a promise, and it covers DEPENDENCIES too.** Declaring a
  floor your transitive graph does not meet fails in the consumer's build, not
  yours — `cargo build` on a modern toolchain says nothing about it. Check the
  real floor before every release, and treat raising it as breaking:

  ```bash
  cargo metadata --format-version 1 --locked \
    | python3 -c "import json,sys;print(max((p['rust_version'] for p in json.load(sys.stdin)['packages'] if p.get('rust_version')), key=lambda v:[int(x) for x in v.split('.')]))"
  cargo +<that-version> check --locked     # the only real proof
  ```
- **The `nrouter` crate name is already ours.** Do not publish under a variant
  name to work around an error — a squatted second name is worse than a fixed
  first one.

## Tagging

```bash
git tag -s sdk-rust-v2.2.1 -m "rust sdk 2.2.1"
git push origin sdk-rust-v2.2.1     # SSH remote; HTTPS git fails here
```
