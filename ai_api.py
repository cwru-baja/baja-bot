import mimetypes
from typing import Any

import aiohttp
from google import genai
from google.genai import errors, types
from loguru import logger
from openai import AsyncOpenAI


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
MAX_INLINE_IMAGE_BYTES = 20 * 1024 * 1024


class AIAPI:
    def __init__(
        self,
        openrouter_api_key: str | None = None,
        gemini_api_key: str | None = None,
        gemini_thinking_budget: int | None = 0,
    ):
        self.gemini_model = DEFAULT_GEMINI_MODEL
        self.gemini_thinking_budget = gemini_thinking_budget
        self.gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

        self.openrouter_client: AsyncOpenAI | None = None
        if openrouter_api_key:
            self.openrouter_client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_api_key,
                default_headers={
                    "Authorization": f"Bearer {openrouter_api_key}",
                    "HTTP-Referer": "https://discord.com",
                    "X-Title": "Baja Bot",
                },
            )

        if not self.gemini_client and not self.openrouter_client:
            raise ValueError("At least one AI provider key is required.")

    async def call_llm(self, system_instructions, user_content) -> str:
        """Call Gemini first, then fall back to OpenRouter if needed."""
        logger.debug(f"System payload words: {len(system_instructions.split())}")
        user_len = sum(
            len(msg.get("text", ""))
            for msg in user_content
            if isinstance(msg, dict) and msg.get("text")
        )
        logger.debug(f"User payload words: {user_len}")

        gemini_error = None
        if self.gemini_client:
            try:
                return await self._call_gemini(system_instructions, user_content)
            except errors.APIError as e:
                gemini_error = e
                logger.warning(f"Gemini primary failed ({e.code}): {e.message}")
            except Exception as e:
                gemini_error = e
                logger.warning(f"Gemini primary failed: {e}")

            if self.openrouter_client:
                logger.warning("Falling back to OpenRouter")
            elif gemini_error:
                raise gemini_error

        return await self._call_openrouter(system_instructions, user_content)

    async def _call_gemini(self, system_instructions: str, user_content: list[dict[str, Any]]) -> str:
        logger.info(f"Calling Gemini primary model: {self.gemini_model}")
        contents = await self._build_gemini_contents(user_content)

        config_kwargs: dict[str, Any] = {
            "system_instruction": system_instructions,
        }
        if self.gemini_thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=self.gemini_thinking_budget
            )

        response = await self.gemini_client.aio.models.generate_content(
            model=self.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        logger.info(f"Used Gemini model {self.gemini_model}")
        total_tokens = getattr(getattr(response, "usage_metadata", None), "total_token_count", None)
        if total_tokens is not None:
            logger.info(f"Total tokens used: {total_tokens}")

        if not response.text:
            raise RuntimeError("Gemini response did not contain text.")

        return response.text

    async def _build_gemini_contents(self, user_content: list[dict[str, Any]]) -> list[Any]:
        contents: list[Any] = []
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": "Baja Bot Gemini image fetcher"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            for item in user_content:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")
                if item_type == "text":
                    text = item.get("text")
                    if text:
                        contents.append(text)
                elif item_type == "image_url":
                    image_url = self._extract_image_url(item)
                    if image_url:
                        contents.append(await self._download_image_part(session, image_url))

        if not contents:
            raise ValueError("No user content was provided to Gemini.")

        return contents

    @staticmethod
    def _extract_image_url(item: dict[str, Any]) -> str | None:
        image_url = item.get("image_url")
        if isinstance(image_url, dict):
            return image_url.get("url")
        if isinstance(image_url, str):
            return image_url
        return None

    async def _download_image_part(self, session: aiohttp.ClientSession, image_url: str) -> types.Part:
        async with session.get(image_url) as response:
            if response.status >= 400:
                raise RuntimeError(f"Failed to fetch image for Gemini: HTTP {response.status}")

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_INLINE_IMAGE_BYTES:
                raise RuntimeError("Image is too large to send inline to Gemini.")

            mime_type = self._get_image_mime_type(image_url, response.headers.get("Content-Type"))
            image_bytes = bytearray()
            async for chunk in response.content.iter_chunked(1024 * 1024):
                image_bytes.extend(chunk)
                if len(image_bytes) > MAX_INLINE_IMAGE_BYTES:
                    raise RuntimeError("Image is too large to send inline to Gemini.")

        return types.Part.from_bytes(data=bytes(image_bytes), mime_type=mime_type)

    @staticmethod
    def _get_image_mime_type(image_url: str, content_type_header: str | None) -> str:
        mime_type = (content_type_header or "").split(";", 1)[0].strip().lower()
        if mime_type.startswith("image/"):
            return mime_type

        guessed_type, _ = mimetypes.guess_type(image_url.split("?", 1)[0])
        if guessed_type and guessed_type.startswith("image/"):
            return guessed_type

        raise RuntimeError("Could not determine image MIME type for Gemini.")

    async def _call_openrouter(self, system_instructions, user_content) -> str:
        if not self.openrouter_client:
            raise RuntimeError("OpenRouter fallback is not configured.")

        messages_payload = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_content},
        ]

        models_to_try = [
            ["OpenRouter Gemini", "google/gemini-2.0-flash-001"],
            ["OpenRouter Secondary", "nvidia/nemotron-nano-12b-v2-vl:free"],
            ["OpenRouter Auto", "openrouter/auto"],
            ["OpenRouter Free", "openrouter/free"],
        ]

        last_error = None
        for idx, (name, model) in enumerate(models_to_try):
            logger.info(f"Calling {name} model: {model}")
            try:
                completion = await self.openrouter_client.chat.completions.create(
                    model=model,
                    reasoning_effort="none",
                    messages=messages_payload,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"{name} model failed: {e}")
                if idx + 1 < len(models_to_try):
                    next_name, _ = models_to_try[idx + 1]
                    logger.warning(f"Falling back to {next_name}")
                continue

            logger.info(f"Used OpenRouter model {completion.model}")
            total_tokens = getattr(getattr(completion, "usage", None), "total_tokens", None)
            if total_tokens is not None:
                logger.info(f"Total tokens used: {total_tokens}")

            content = completion.choices[0].message.content
            if not content:
                last_error = RuntimeError("OpenRouter response did not contain text.")
                logger.warning(f"{name} model returned an empty response")
                continue

            return content

        raise last_error or RuntimeError("All OpenRouter models failed.")
