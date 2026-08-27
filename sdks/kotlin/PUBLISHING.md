# Publishing `ai.nrouter:nrouter-sdk-kotlin` to Maven Central

Same registry and account as the Java SDK. If you have published that one, the
credentials here are already in place.

## Once, per machine

1. **Sonatype Central account** — <https://central.sonatype.com>. The namespace
   `ai.nrouter` must be verified against the `nrouter.ai` domain (a DNS TXT
   record Sonatype names during verification). This is done once for the whole
   org, not per artifact.
2. **A user token** — Central → *View Account* → *Generate User Token*. It
   returns a username/password pair; these are NOT your login.
3. **A GPG key**, because Central rejects unsigned artifacts:

   ```bash
   gpg --gen-key
   gpg --list-secret-keys --keyid-format=long        # note the key id
   gpg --keyserver keyserver.ubuntu.com --send-keys <KEY_ID>   # must be public
   gpg --armor --export-secret-keys <KEY_ID>         # the value for SIGNING_KEY
   ```

Store all four in the nRouter credential store, never in the repo:

```bash
export SONATYPE_USERNAME=...      # the token username
export SONATYPE_PASSWORD=...      # the token password
export SIGNING_KEY="$(gpg --armor --export-secret-keys <KEY_ID>)"
export SIGNING_PASSWORD=...       # the key's passphrase
```

`build.gradle.kts` reads exactly these four names. Signing is wired only when
`SIGNING_KEY` and `SIGNING_PASSWORD` are both present and is required only for a
`publish` task, so a plain `./gradlew build` never asks for a key.

## Every release

```bash
# 1. Version. gradle.properties is the only place it lives.
#    Central refuses to overwrite a released version — bump, never re-push.
$EDITOR gradle.properties          # version=2.1.1

# 2. Prove it green first. A published version cannot be withdrawn.
./gradlew build
python3 ../../conformance/check_conformance.py

# 3. Stage locally and LOOK at what you are about to publish.
./gradlew publishToMavenLocal
ls ~/.m2/repository/ai/nrouter/nrouter-sdk-kotlin/<version>/
#    Expect: .jar, -sources.jar, -javadoc.jar, .pom, .module
#    Central rejects a bundle missing sources or javadoc.

# 4. Publish.
./gradlew publish

# 5. Release the staged deployment at https://central.sonatype.com/publishing
#    `autoPublish` is deliberately false: the deployment waits for you to look
#    at it. Turning it on removes the last step where a wrong artifact can be
#    dropped instead of released.
```

Availability on `repo1.maven.org` lags the release by 10–30 minutes; the Central
UI shows *PUBLISHED* first.

## Tagging

```bash
git tag -s sdk-kotlin-v2.1.1 -m "kotlin sdk 2.1.1"
git push origin sdk-kotlin-v2.1.1     # SSH remote; HTTPS git fails here
```

## Traps

- **`ai.nrouter` must be verified before the first publish.** An unverified
  namespace fails at the deployment step, after the upload, with a message that
  reads like an auth problem.
- **A GPG key that was never sent to a keyserver fails validation**, and the
  error names the signature rather than the missing public key.
- **`developerConnection` is SSH on purpose.** It is the write path a release
  tag travels, and HTTPS git does not work from the nRouter workspace.
- **Do not publish from a dirty tree.** The jar is built from what is on disk,
  not from what is committed, so an uncommitted edit ships silently.
