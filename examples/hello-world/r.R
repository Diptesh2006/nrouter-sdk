# nRouter — R hello world
# install.packages(c("httr", "jsonlite"))
# No official OpenAI R SDK — call the OpenAI-compatible endpoint directly.

library(httr)
library(jsonlite)

nrouter_key <- Sys.getenv("NROUTER_API_KEY")

response <- POST(
  url = "https://api.nrouter.ai/v1/chat/completions",
  add_headers(Authorization = paste("Bearer", nrouter_key)),
  content_type_json(),
  body = toJSON(list(
    model = "claude-sonnet-4-20250514",
    messages = list(list(role = "user", content = "Hello, nRouter!"))
  ), auto_unbox = TRUE)
)

result <- content(response, as = "parsed", type = "application/json")
cat(result$choices[[1]]$message$content, "\n")
