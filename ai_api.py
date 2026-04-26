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

        try:
            logger.info("Requesting primary model")
            completion = await self.client.chat.completions.create(
                # model="openai/gpt-oss-20b:free",
                model="google/gemini-2.0-flash-001",
                messages=messages_payload
            )
        except Exception as e:

            logger.warning(f"Primary model failed: {e}")
            logger.warning("Falling back to auto")
            completion = await self.client.chat.completions.create(
                model="openrouter/auto",
                messages=messages_payload
            )

        return completion.choices[0].message.content