# nRouter — R hello world
# install.packages("nrouter", repos = c(nroutergateway = "https://nroutergateway.r-universe.dev", CRAN = "https://cloud.r-project.org"))

library(nrouter)

# A concrete model id pins the request to that model; `nrouter/auto` lets
# nRouter choose, and `x-nr-model` names the model that answered.
model <- Sys.getenv("NROUTER_MODEL", "gpt-5.4-mini")
client <- nrouter_client()

response <- nrouter_chat_completions(client, list(
  model = model,
  messages = list(list(role = "user", content = "Hello, nRouter!"))
))

cat(response$body$choices[[1]]$message$content, "\n")
print(response$meta)
