# Helper to verify if webfakes background process can start cleanly in this environment.
webfakes_available <- function() {
  if (!requireNamespace("webfakes", quietly = TRUE)) {
    return(FALSE)
  }
  if (exists(".nrouter_webfakes_status", envir = .GlobalEnv)) {
    return(get(".nrouter_webfakes_status", envir = .GlobalEnv))
  }
  status <- tryCatch({
    app <- webfakes::new_app()
    process <- webfakes::new_app_process(app)
    url <- process$url()
    process$stop()
    TRUE
  }, error = function(e) {
    FALSE
  })
  assign(".nrouter_webfakes_status", status, envir = .GlobalEnv)
  status
}
