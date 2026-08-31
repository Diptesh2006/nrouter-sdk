# Publishing the Go SDK

Go has no registry to push to. `proxy.golang.org` serves whatever a **git tag**
points at, so publishing is tagging — and a tag, once fetched by the module
proxy, is immutable in practice. Bump; never re-point.

## The tag shape is not optional

This module lives in a subdirectory of a multi-module repo, so Go requires the
tag to carry the subdirectory prefix:

```
sdks/go/v2.2.1        ✅  resolves github.com/nRouterAI/nrouter-sdk/sdks/go/v2@v2.2.1
v2.2.1                ❌  resolves the repo ROOT, which is not a Go module
```

Getting this wrong does not fail loudly — `go get` reports the module as
non-existent, which reads like a network problem.

## Every release

```bash
cd sdks/go

# 1. Prove it green. A tag the proxy has cached cannot be taken back.
gofmt -l .                        # expect NO output
go vet ./...
go test ./... -race -count=1
python3 ../../conformance/check_conformance.py

# 2. Confirm the module path matches the repo, or the proxy 404s.
grep '^module' go.mod             # github.com/nRouterAI/nrouter-sdk/sdks/go/v2

# 3. Tag from a clean main that is already pushed.
git -C ../.. status --short       # expect empty
VERSION="$(tr -d '[:space:]' < VERSION)"
git -C ../.. tag "sdks/go/v$VERSION"
git -C ../.. push origin "sdks/go/v$VERSION"

# 4. Prove the proxy actually serves it — this is the only real check.
#    Allow a minute; the proxy fetches lazily on first request.
curl -s https://proxy.golang.org/github.com/n!router!a!i/nrouter-sdk/sdks/go/v2/@v/list
```

Step 4's URL is case-encoded: the proxy lowercases paths and escapes each
uppercase letter as `!` + the lowercase letter, so `nRouterAI` becomes
`n!router!a!i`. A plain-case URL 404s and looks like an unpublished module.

## Minimum Go version

`go.mod` declares `go 1.21` and the SDK uses only the standard library, so
there is no transitive floor to measure. Derive it rather than trusting this
line if the dependency set ever changes:

```bash
go list -m -f '{{.GoVersion}}' all | sort -V | tail -1
```

Generics (`Response[T]`) are the actual floor and landed in 1.18; 1.21 is the
oldest release still receiving security fixes at the time of writing.

## Verify a published version

```bash
cd "$(mktemp -d)" && go mod init probe
go get github.com/nRouterAI/nrouter-sdk/sdks/go/v2@latest
```
