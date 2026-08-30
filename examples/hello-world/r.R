# nRouter — R hello world
# remotes::install_github("nRouterAI/nrouter-sdk", subdir = "sdks/r")

library(nrouter)

# A Smart Router alias activates its strategy/fallback chain; a concrete model
# id pins the request to that model.
model <- Sys.getenv("NROUTER_MODEL", "claude-sonnet-4-5-20250929")
client <- nrouter_client()

response <- nrouter_chat_completions(client, list(
  model = model,
  messages = list(list(role = "user", content = "Hello, nRouter!"))
))

cat(response$body$choices[[1]]$message$content, "\n")
print(response$meta)
