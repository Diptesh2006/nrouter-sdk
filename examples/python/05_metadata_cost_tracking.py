"""05. Metadata & Cost Tracking — Inspecting canonical x-nr-* response headers.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter

def main() -> None:
    with nRouter() as client:
        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": "Name three database normalization forms."}],
            max_tokens=200,
        )

        meta = client.last_response
        print("=== Complete nRouter Response Metadata ===")
        print(f"Request ID:         {meta.request_id}")
        print(f"Target Model:       {meta.model}")
        print(f"Cost Status:        {meta.cost_status}")
        print(f"Exact Cost (USD):   ${meta.cost:.6f}" if meta.cost is not None else "Exact Cost (USD):   None")
        print(f"Input Tokens:       {meta.input_tokens}")
        print(f"Output Tokens:      {meta.output_tokens}")
        print(f"Total Tokens:       {meta.total_tokens}")
        print(f"Cache Read Tokens:  {meta.cache_read_tokens}")
        print(f"Cache Write Tokens: {meta.cache_write_tokens}")
        print(f"Gateway Cache:      {meta.response_cache}")
        print(f"Gateway Cache Age:  {meta.response_cache_age}s" if meta.response_cache_age else "Gateway Cache Age:  N/A")
        print(f"Limit Source:       {meta.limit_source}")

if __name__ == "__main__":
    main()
