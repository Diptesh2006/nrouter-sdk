# Dart source distribution

The Dart / Flutter SDK is a source preview and `pubspec.yaml` declares
`publish_to: none`. Its workflow analyzes and tests the package, runs the shared
conformance gate, and verifies that the publication guard remains in place.

```bash
dart pub get
dart analyze --fatal-infos
dart test
python3 ../../conformance/check_conformance.py
```

Consumers use a path dependency from a checkout. A future pub.dev launch is an
owner decision and must remove the manifest guard through a reviewed release
change; do not add publication credentials to the verification workflow.
