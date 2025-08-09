from app.services.voice.ai import get_ai_answer

import json
import re


CMD_JSON_RE = re.compile(r"\{.*\}", re.S)


class TextGenerationAgent:
    @staticmethod
    async def handle_generate_text(text: str, lang: str) -> dict:
        prompt = f"""
        Analyze the user's request. If the user asks to create a note, essay, story, article, summary, letter, or any other type of text — complete the task and ALWAYS return the RESPONSE ONLY as a strict JSON in the following format:
        {{
          "command": {{
            "action": "create_note",
            "title": "<short title or topic, 2-3 words>",
            "text": "<main text, full response>",
            "answer": "<short report for the user in their language, e.g. 'Я создала заметку: Покормить кота'>"
          }}
        }}

        Rules:
        - If it is a note, action = create_note, title — a short summary of the note, text — the full note text.
        - If the user did not provide an explicit title, invent a short title based on the meaning.
        - Do not add any comments, explanations, or text outside the JSON.
        - Always return only JSON in the specified format.
        - The response language must match the user's language.
        - ALWAYS add a field "answer" (in the same JSON), where you briefly and clearly report to the user in their language what you did (for example: 'Я создала заметку: Покормить кота').

        Examples:
        User: "Create a note: buy bread and milk" → {{"command": {{"action": "create_note", "title": "Shopping List", "text": "Buy bread and milk", "answer": "Я создала заметку: Список покупок"}}}}
        User: "Write an essay about space" → {{"command": {{"action": "create_note", "title": "Space", "text": "<essay about space>", "answer": "Я создала заметку: Космос"}}}}
        User: "Make a summary on Russian history" → {{"command": {{"action": "create_note", "title": "Russian History", "text": "<summary>", "answer": "Я создала заметку: История России"}}}}
        User: "Create a story about a cat" → {{"command": {{"action": "create_note", "title": "Cat Story", "text": "<story>", "answer": "Я создала заметку: История кота"}}}}
        User: "Note: call mom tomorrow" → {{"command": {{"action": "create_note", "title": "Call Mom", "text": "Call mom tomorrow", "answer": "Я создала заметку: Позвонить маме"}}}}

        User language: {lang}
        User request: "{text}"
        """
        response = await get_ai_answer(prompt)
        # Try to parse as note command, otherwise return as plain text
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        return {"text": response}
