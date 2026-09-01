"""12. Multimodal Vision — Analyzing images with multimodal models.

Prerequisites:
    pip install nrouter-sdk
    export NROUTER_API_KEY="sk-nrouter-your-key-here"
"""

from nroutersdk import nRouter

def main() -> None:
    with nRouter() as client:
        response = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe the main colors in this image concisely:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
                            },
                        },
                    ],
                }
            ],
            max_tokens=200,
        )

        print(response.choices[0].message.content)

if __name__ == "__main__":
    main()
