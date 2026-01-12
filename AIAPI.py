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

        try:
            # Try primary robust model (Gemini 2.0 Flash)
            completion = await self.client.chat.completions.create(
                model="google/gemini-2.0-flash-001",
                messages=messages_payload
            )
        except Exception as e:
            print(f"Primary model failed: {e}. Falling back to auto...")
            completion = await self.client.chat.completions.create(
                model="openrouter/auto",
                messages=messages_payload
            )

        return completion.choices[0].message.content