"""Send a minimal request using Anthropic's Messages API."""

import os

from anthropic import Anthropic
from dotenv import load_dotenv


def main():
    load_dotenv()

    model = os.environ.get("ANTHROPIC_MODEL")
    if not model:
        raise SystemExit(
            "Set ANTHROPIC_MODEL to a model ID available to your account."
        )

    client = Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": "Say hello in one sentence."}],
    )

    for block in message.content:
        if block.type == "text":
            print(block.text)


if __name__ == "__main__":
    main()
