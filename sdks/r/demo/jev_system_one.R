# TypeSafe Jev System One uses the normal chat-completions request shape.
library(nrouter)

if (Sys.getenv("NROUTER_API_KEY") == "") {
  stop("Set NROUTER_API_KEY before running.")
}

client <- nrouter_client()
response <- nrouter_chat_completions(client, list(
  model = "typesafe/jev",
  temperature = 0,
  max_tokens = 128,
  messages = list(
    list(role = "system", content = "Classify the incident. Return JSON only with priority, queue, and summary."),
    list(role = "user", content = "Production payment requests return HTTP 500 in two regions.")
  )
))

cat("Decision:", response$body$choices[[1]]$message$content, "\n")
cat("Request ID:", response$meta$request_id, "\n")
cat("Served model:", response$meta$model, "\n")
if (nrouter_is_priced(response$meta)) {
  cat("Exact cost: $", response$meta$cost, "\n", sep = "")
} else {
  cat("Cost status:", response$meta$cost_status, "\n")
}
