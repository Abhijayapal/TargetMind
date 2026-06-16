import chainlit as cl
from code import orchestrator, run_with_retry   # reuse existing agents

@cl.on_chat_start
async def on_chat_start():
    await cl.Message(
        content=(
            " **Welcome to Target Mind!**\n\n"
            "I can answer biomedical questions about **genes/proteins**, **diseases**, and **drugs** "
            "using the [Open Targets](https://www.opentargets.org/) platform.\n\n"
        )
    ).send()


# ── Message Handler ───────────────────────────────────────────────────────────
@cl.on_message
async def on_message(message: cl.Message):
    user_input = message.content.strip()
    if not user_input:
        return

    async with cl.Step(name="🧬 Target Mind is thinking…", type="run") as step:
        step.input = user_input

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: run_with_retry(orchestrator, user_input, max_retries=3, delay=1.0),
        )

        if response and response.content:
            step.output = response.content
        else:
            step.output = "No response returned."

    if response and response.content:
        await cl.Message(content=response.content).send()
    else:
        await cl.Message(
            content=(
                "⚠️ Sorry, I couldn't get a response from Open Targets. "
                "Please try rephrasing your query."
            )
        ).send()
