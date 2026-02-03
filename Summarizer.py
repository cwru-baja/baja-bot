from AIAPI import AIAPI

"""
Class to parse messages and generate summarizes
"""
class Summarizer:
    def __init__(self, ai_client: AIAPI):
        self.ai_client = ai_client

    async def generate_summary(self, messages) -> str:
        """Helper function to call LLM for summarization with strict rules."""

        # UPDATED: Focus on synthesis, grouping, and ignoring noise.
        system_instruction = (
            "You are a concise executive assistant summarizing a technical Discord conversation. "
            "Your goal is to provide a high-level overview, not a play-by-play transcript.\n\n"
            "Input: A transcript of text and attached images.\n"
            "Task: Create a bulleted summary of the key topics discussed.\n\n"
            "GUIDELINES:\n"
            "1. IGNORE NOISE: completely ignore keyboard smashing (e.g., 'asdfjkl'), one-word reactions, and off-topic banter that leads nowhere.\n"
            "2. GROUP TOPICS: Do not list messages chronologically. Group thoughts by topic (e.g., 'The group discussed the Aero Gas class requirements...').\n"
            "3. SYNTHESIZE OPINIONS: Instead of 'User A liked it, User B liked it', say 'The group was generally excited about X'.\n"
            "4. IMAGES: Integrate image descriptions into the context of the conversation (e.g., 'User shared a photo of a steak while discussing dinner') rather than listing them separately at the end.\n"
            "5. BREVITY: Keep the summary under 150 words unless the transcript is massive.\n"
            "6. FORMAT: Use bullet points for distinct topics."
        )

        return await self.ai_client.call_llm(system_instruction, messages)


    async def generate_title(self, messages) -> str:
        system_instruction = (
            "You are a concise executive assistant creating a title for a thread for a technical Discord conversation. "
            "Your goal is to provide a high-level overview of the thread in just a few words.\n\n"
            "Input: A transcript of text and attached images.\n"
            "Task: Create a short title to summarize the conversation.\n\n"
            "GUIDELINES:\n"
            "1. IGNORE NOISE: completely ignore keyboard smashing (e.g., 'asdfjkl'), one-word reactions, and off-topic banter that leads nowhere.\n"
            "2. BE CLEAR: The title should adequately convey to someone unfamiliar with the conversation what it is about.\n"
            "3. BE SHORT: Keep the title short, no more than a few words."
        )

        return await self.ai_client.call_llm(system_instruction, messages)


    def build_transcript_with_images(self, messages: list) -> list:
        """
        Constructs the user content payload for the LLM, interleaving text and images.
        Includes logic to deduplicate images (original vs thumbnail).
        """
        user_content = []
        current_text_block = ""

        # Track seen image URLs to prevent duplicate "thumbnails" from being sent
        seen_images = set()

        for msg in messages:
            if msg.author.bot:
                continue

            # Format timestamp and author (Using Nickname/Display Name)
            timestamp = msg.created_at.strftime("%H:%M")
            msg_header = f"[{timestamp}] {msg.author.display_name}: "

            # Append text content if present
            if msg.content:
                current_text_block += f"{msg_header}{msg.content}\n"

            # Check for images and deduplicate
            images = []
            for att in msg.attachments:
                if att.content_type and att.content_type.startswith('image/'):
                    # Check if we've already processed this URL (or a proxy of it)
                    if att.url not in seen_images:
                        images.append(att)
                        seen_images.add(att.url)

            # Add image counter to help LLM understand there's only one image
            if images:
                # Add image count to text if message had no text content
                if not msg.content:
                    current_text_block += f"{msg_header}[Attached {len(images)} image(s)]\n"
                else:
                    # If there was text content, append the image count
                    current_text_block += f"[Attached {len(images)} image(s)]\n"

                # Flush accumulated text before adding images
                if current_text_block:
                    user_content.append({"type": "text", "text": current_text_block})
                    current_text_block = ""

                # Add images
                for img in images:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img.url}
                    })

        # Flush any remaining text after the loop
        if current_text_block:
            user_content.append({"type": "text", "text": current_text_block})

        return user_content

    async def get_summary(self, messages) -> str:
        """Generates summary based on raw messages."""
        transcript_content = self.build_transcript_with_images(messages)
        if not transcript_content:
            return "Not enough content to summarize."

        summary = await self.generate_summary(transcript_content)

        if summary:
            if len(summary) > 2000:
                summary = summary[:1997] + "..."
            return f"**Thread Summary:**\n{summary}"
        else:
            return "Failed to generate a summary."


    async def get_title(self, messages) -> str:
        transcript_content = self.build_transcript_with_images(messages)

        title = await self.generate_title(transcript_content)

        if title:
            if len(title) > 100:
                title = title[:100] + "..."
            return title
        else:
            return ""