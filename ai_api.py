from loguru import logger
from openai import AsyncOpenAI


class AIAPI:
    def __init__(self, api_key: str):
        self.client: AsyncOpenAI = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://discord.com",
                "X-Title": "Baja Bot",
            }
        )

    async def call_llm(self, system_instructions, user_content) -> str:
        """Calls LLM model with given system and user instructions."""
        messages_payload = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_content}
        ]

        logger.debug(f"System payload words: {len(system_instructions.split(" "))}")
        # Get user content length
        user_len = sum([len(msg["text"]) for msg in user_content if msg.get("text", None)])
        logger.debug(f"User payload words: {user_len}")

        models_to_try = [
            ["Primary", "google/gemini-2.0-flash-001"],
            ["Auto", "openrouter/auto"],
            ["Free", "openrouter/free"],
        ]

        succeeded = False
        model_idx = 0
        completion = None
        while not succeeded:
            name, model = models_to_try[model_idx]
            logger.info(f"Calling {name} model: {model}")
            try:
                completion = await self.client.chat.completions.create(
                    # model="openai/gpt-oss-20b:free",
                    model=model,
                    reasoning_effort="none",
                    messages=messages_payload
                )
                succeeded = True
            except Exception as e:
                model_idx = model_idx + 1
                logger.warning(f"{name} model failed: {e}")
                if model_idx >= len(models_to_try):
                    # Out of models, raise the exception again
                    raise e
                next_name, next_model = models_to_try[model_idx]
                logger.warning(f"Falling back to {next_name}")

        logger.info(f"Used model {completion.model}")
        logger.info(f"Total tokens used: {completion.usage.total_tokens}")

        return completion.choices[0].message.content