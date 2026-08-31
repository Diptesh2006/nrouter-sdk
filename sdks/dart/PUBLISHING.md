# Publishing `nrouter` to pub.dev

## Once

Publishing is authorised by a Google account that must be a **uploader** on the
`nrouter` package (or a member of a verified publisher for `nrouter.ai`). Sign in
once:

```bash
dart pub login          # opens a browser; the token lands in ~/.config/dart
```

A verified publisher is worth doing: it puts `nrouter.ai` beside the package
name on pub.dev instead of a personal email. Set it up at
<https://pub.dev/create-publisher> — it needs the same DNS-verified domain
ownership as the Maven namespace.

## Every release

```bash
cd sdks/dart

# 1. Version lives in pubspec.yaml and nowhere else.
#    pub.dev refuses to overwrite a published version — bump, never re-push.
$EDITOR pubspec.yaml            # version: 2.2.1

# 2. Prove it green. A published version cannot be withdrawn, only retracted.
dart pub get
dart analyze                    # must be "No issues found!"
dart test
python3 ../../conformance/check_conformance.py

# 3. Dry run. This is the score you will be graded on, before it counts.
dart pub publish --dry-run

# 4. Publish.
dart pub publish
```

## The pub points score is part of the product

pub.dev grades every package and the score is on the listing page. The dry run
reports the same findings. What actually costs points here:

- **No `example/`** — an `example/` directory or an `Example` section in the
  README is worth points; the README section counts.
- **Undocumented public API** — dartdoc coverage is scored. Every public member
  in this package carries a doc comment; keep it that way when adding one.
- **`dart analyze` findings** — any lint at all costs points. `analysis_options.yaml`
  turns on `strict-casts` and `strict-raw-types` so the failure happens locally.
- **A pinned or over-tight dependency** — `http: ">=1.0.0 <2.0.0"` is deliberately
  a range. Pinning an exact version makes this package unusable alongside
  anything else that depends on `http`.

## Traps

- **`dart pub publish` is irreversible.** A version can be *retracted* (hidden
  from new resolutions) but never deleted, and existing consumers keep resolving
  it. The dry run is the only safety net; use it every time.
- **Everything not gitignored is uploaded.** Check the file list the dry run
  prints — a stray `.env`, a key, or a build artifact goes public with the
  package.
- **A Flutter-only dependency would break the plain-Dart and web builds.** This
  package depends on `http` alone for that reason; adding anything from
  `dart:io` or the Flutter SDK narrows where it can run, silently, until a web
  consumer reports it.
- **The `LICENSE` file must be present and recognised**, or the score drops and
  the listing shows "unknown license".

## Tagging

```bash
git tag -s sdk-dart-v2.2.1 -m "dart sdk 2.2.1"
git push origin sdk-dart-v2.2.1     # SSH remote; HTTPS git fails here
```
