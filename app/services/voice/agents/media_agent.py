from app.services.voice.ai import get_35_ai_answer

import re
import json


CMD_JSON_RE = re.compile(r"\{.*\}", re.S)


class MediaAgent:
    MEDIA_COMMANDS = [
        "play",
        "pause",
        "toggle",
        "next",
        "prev",
        "forward",
        "backward",
        "volume_up",
        "volume_down",
    ]

    @staticmethod
    async def handle_media_command(text: str, lang: str) -> dict:
        """
        Analyze user input and map it to a media command.
        Returns a dict in the required format for media control.
        """
        prompt = f"""
You are a multilingual assistant for browser media control. The user may speak in any language and use various ways to express their intent.

Your task: Analyze the user's request and map it to one of these media commands:
- play
- pause
- toggle
- next
- prev
- forward
- backward
- volume_up
- volume_down

Respond ONLY with a JSON object in this format:
{{
  \"command\": {{
    \"action\": \"control_media\",
    \"mediaCommand\": \"<one of: play, pause, toggle, next, prev, forward, backward, volume_up, volume_down>\"
  }}
}}

Do not add any text or comments outside the JSON.

You must understand the user's intent even if the command is formulated in an unusual way, in any language, or with synonyms. Use your best judgment to match the intent to the closest media command.

Examples:
User: "Сделай погромче" → {{"command": {{"action": "control_media", "mediaCommand": "volume_up"}}}}
User: "Volume up" → {{"command": {{"action": "control_media", "mediaCommand": "volume_up"}}}}
User: "Сделай потише" → {{"command": {{"action": "control_media", "mediaCommand": "volume_down"}}}}
User: "Volume down" → {{"command": {{"action": "control_media", "mediaCommand": "volume_down"}}}}
User: "Поставь видео на паузу" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Останови видео" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Pause the video." → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Pause o vídeo." → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Deixa o vídeo parado." → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Play the next video" → {{"command": {{"action": "control_media", "mediaCommand": "next"}}}}
User: "Следующее видео" → {{"command": {{"action": "control_media", "mediaCommand": "next"}}}}
User: "Avançar vídeo" → {{"command": {{"action": "control_media", "mediaCommand": "forward"}}}}
User: "Перемотай вперед" → {{"command": {{"action": "control_media", "mediaCommand": "forward"}}}}
User: "Назад на 20 секунд" → {{"command": {{"action": "control_media", "mediaCommand": "backward"}}}}
User: "Toggle a video" → {{"command": {{"action": "control_media", "mediaCommand": "toggle"}}}}
User: "Включить видео" → {{"command": {{"action": "control_media", "mediaCommand": "play"}}}}
User: "Start the video" → {{"command": {{"action": "control_media", "mediaCommand": "play"}}}}
User: "Resume playback" → {{"command": {{"action": "control_media", "mediaCommand": "play"}}}}
User: "Pause" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}
User: "Stop" → {{"command": {{"action": "control_media", "mediaCommand": "pause"}}}}

If the request is unclear or not related to media, respond:
{{"command": {{"action": "control_media", "mediaCommand": "noop"}}}}

User language: {lang}
User input: "{text}"
"""
        response = await get_35_ai_answer(prompt)
        match = CMD_JSON_RE.search(response)
        if match:
            json_str = match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"command": {"action": "control_media", "mediaCommand": "noop"}}
        return {"command": {"action": "control_media", "mediaCommand": "noop"}}
