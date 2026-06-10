"""Step 1 of the smoke test: prove the SDK + auth work at all.

We bypass our orchestrator and call ``claude_agent_sdk.query`` directly
with the shortest possible prompt. Whatever messages come back, we print
the type and a brief repr so we can see the actual shape and refine our
``_extract_text`` helper if needed.
"""

from __future__ import annotations

import asyncio

from claude_agent_sdk import ClaudeAgentOptions, query


async def main() -> None:
    options = ClaudeAgentOptions(
        system_prompt="You are extremely concise. Reply with one short sentence.",
    )
    print("--- begin SDK stream ---")
    async for message in query(prompt="Reply with exactly: hello", options=options):
        cls = type(message).__name__
        # Print a short preview of the message so we can see its shape.
        preview = repr(message)
        if len(preview) > 400:
            preview = preview[:400] + "...(truncated)"
        print(f"[{cls}] {preview}")
    print("--- end SDK stream ---")


if __name__ == "__main__":
    asyncio.run(main())
