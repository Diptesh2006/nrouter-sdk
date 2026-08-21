# nrouter (R)

OpenAI-compatible SDK for the [nRouter](https://nrouter.ai) LLM gateway. No official
OpenAI SDK exists for R, so this package calls the HTTP API directly via `httr`.

## Install

```r
# install.packages("remotes")
remotes::install_github("nRouterAI/nrouter-ent-ai-hub", subdir = "nrouter-sdk/sdks/r")
```

## Usage

```r
library(nrouter)

response <- nrouter_chat(
  messages = list(list(role = "user", content = "Hello!")),
  model = "claude-sonnet-4-20250514"
) # reads NROUTER_API_KEY from env

cat(response$choices[[1]]$message$content)
```

## Basic only, for now

This is a minimal wrapper: one function, `nrouter_chat()`, doing API key
resolution/validation (`sk-nrouter-...`) and a plain HTTP POST to
`https://api.nrouter.ai/v1/chat/completions`. It doesn't yet have the typed errors,
automatic cost-header capture, or `credits`/`guardrails`/`prompts` namespaces that
[`sdks/python/`](../python/) has — see that package for the fuller pattern this one will
grow into.
