from app.services.voice.prompts import build_action_prompt
from app.services.voice.ai import get_35_ai_answer

import re
import json


CMD_JSON_RE = re.compile(r"\{.*\}", re.S)


class ActionAgent:
    @staticmethod
    async def handle_command(text: str, lang: str, tabs: list[dict]) -> dict:
        prompt = build_action_prompt(text, lang, tabs)
        response = await get_35_ai_answer(prompt)
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"action": "noop"}
        return {"action": "noop"}

    @staticmethod
    async def handle_question(text: str) -> str:
        prompt = f"""
        IMPORTANT:Respond to the following user question in the SAME LANGUAGE it was asked.
        - Limit your response to no more than 35 words.
        - Do not use asterisks (*) or markdown symbols.

        Question:
        {text}
        """
        response = await get_35_ai_answer(prompt)
        return response
