"""OpenAI LLM client for content analysis."""

import json
from typing import Optional

from openai import OpenAI

from smartcut.config import LLM_MODEL
from smartcut.core.models import DuplicateGroup, DuplicateGroups

DUPLICATE_DETECTION_PROMPT = """You are analyzing a video transcript where the speaker often repeats the same phrase multiple times (multiple takes). The LAST take is always the best.

Below are consecutive text blocks separated by pauses. Identify groups of blocks that are duplicate takes of the same content. For each group, mark which one to KEEP (always the last one in the group) and which ones to REMOVE.

Rules:
- Only group blocks that are clearly attempts at saying the same thing
- If a block is unique content (not a retry), don't include it in any group
- The "keep" block should always be the last one in the duplicate group
- Be conservative - only mark as duplicates if you're confident

Blocks:
{blocks}

Return JSON in this exact format:
{{
  "groups": [
    {{
      "block_ids": [1, 2, 3],
      "keep": 3,
      "remove": [1, 2],
      "reason": "Three attempts at the same intro"
    }}
  ]
}}

If there are no duplicates, return: {{"groups": []}}"""


ACCENT_WORDS_PROMPT = """Identify 2-4 key words in this subtitle text that should be visually emphasized (highlighted in a different color). Choose important nouns, verbs, or key terms that carry the main meaning.

Text: "{text}"

Return JSON array of words to accent (exactly as they appear in the text):
{{"accent_words": ["word1", "word2"]}}

Rules:
- Choose 2-4 words maximum
- Pick words that carry the core meaning
- Don't accent common words like "и", "в", "на", "это", "the", "is", "a"
- Return words exactly as they appear (same case, same form)"""


class LLMClient:
    """Client for OpenAI Chat API for content analysis."""

    def __init__(self, api_key: str, model: Optional[str] = None):
        self.client = OpenAI(api_key=api_key)
        self.model = model or LLM_MODEL

    def detect_duplicates(self, paragraphs: list[dict]) -> DuplicateGroups:
        """
        Detect duplicate takes in a list of paragraphs.

        Args:
            paragraphs: List of dicts with 'id' and 'text' keys.

        Returns:
            DuplicateGroups with identified duplicate groups.
        """
        if not paragraphs:
            return DuplicateGroups(groups=[])

        # Format blocks for the prompt
        blocks_text = "\n".join(
            f"[{p['id']}] \"{p['text']}\""
            for p in paragraphs
        )

        prompt = DUPLICATE_DETECTION_PROMPT.format(blocks=blocks_text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a video editing assistant that identifies duplicate takes in transcripts."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)
            groups = [
                DuplicateGroup(
                    block_ids=g["block_ids"],
                    keep=g["keep"],
                    remove=g["remove"],
                    reason=g.get("reason", ""),
                )
                for g in result.get("groups", [])
            ]
            return DuplicateGroups(groups=groups)

        except Exception as e:
            # On error, return empty groups (no duplicates detected)
            print(f"Warning: Duplicate detection failed: {e}")
            return DuplicateGroups(groups=[])

    def identify_accent_words(self, text: str) -> list[str]:
        """
        Identify words to accent/highlight in subtitle text.

        Args:
            text: Subtitle text.

        Returns:
            List of words to highlight.
        """
        if not text or len(text.split()) < 3:
            return []

        prompt = ACCENT_WORDS_PROMPT.format(text=text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a subtitle styling assistant."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            result = json.loads(response.choices[0].message.content)
            return result.get("accent_words", [])

        except Exception as e:
            print(f"Warning: Accent word identification failed: {e}")
            return []

    def identify_accent_words_batch(self, texts: list[str]) -> list[list[str]]:
        """
        Identify accent words for multiple texts efficiently.

        Args:
            texts: List of subtitle texts.

        Returns:
            List of accent word lists, one per input text.
        """
        # For efficiency, process in batches or individually
        # For now, process individually (can be optimized later)
        return [self.identify_accent_words(text) for text in texts]
