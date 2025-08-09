from app.services.voice.ai import get_35_ai_answer

import json
import re


CMD_JSON_RE = re.compile(r"\{.*\}", re.S)


class CalendarAgent:
    @staticmethod
    async def handle_calendar_command(
        text: str, lang: str, user_events: list[dict]
    ) -> dict:
        """
        Analyze user input and map it to a calendar operation.
        Args:
            text: User's voice command text
            lang: User's language
            user_events: List of user's existing events, each containing:
                        {
                            "title": str,
                            "description": str,
                            "start_date": datetime,
                            "location": str
                        }
        Returns:
            Dict with calendar command and necessary data.
        """
        # Convert events to a more readable format for the AI
        events_text = ""
        if user_events:
            events_text = "Your current events:\n"
            for event in user_events:
                start = event["start_date"].strftime("%Y-%m-%d %H:%M")
                events_text += f"- {event['title']} on {start}"
                if event.get("location"):
                    events_text += f" at {event['location']}"
                events_text += "\n"

        prompt = f"""
        You are a multilingual calendar assistant. Analyze the user's request and map it to a calendar operation.
        The user may speak in any language and use various ways to express their intent.

        {events_text}

        Respond ONLY with a JSON object in one of these formats:

        1. For creating events:
        {{
          "command": {{
            "action": "calendar",
            "operation": "create_event",
            "data": {{
              "title": "Meeting with Danial",
              "description": "Business meeting",
              "start_date": "2025-07-03T15:00:00",
              "location": "Office" // optional
            }},
            "answer": "<short report for user in their language>"
          }}
        }}

        2. For querying events:
        {{
          "command": {{
            "action": "calendar",
            "operation": "query_events",
            "data": {{
              "query_type": "specific_event|date_range|free_slots",
              "event_title": "Meeting with Danial", // for specific_event
              "start_date": "2025-07-03", // for date_range
              "end_date": "2025-07-10"    // for date_range
            }},
            "answer": "<short report for user in their language>"
          }}
        }}

        Rules:
        - Parse dates and times into ISO format with timezone (e.g., "2025-07-29T15:00:00")
        - Always include an "answer" field with a user-friendly response in their language
        - For unclear requests, set operation to "unknown"
        - Location is optional for events
        - Description can be generated from context if not explicitly provided
        - When responding to queries, reference the actual events in the user's calendar
        - For free slots queries, consider existing events to find actually free time
        - Check for conflicts when creating new events

        Query Types Explained:
        - specific_event: When user asks about a specific event ("When is my meeting with Danial?")
        - date_range: When user asks about events in a time period ("What meetings do I have this week?")
        - free_slots: When user asks about free time ("When am I free this week?")

        Examples:
        "поставь встречу с Даниалом на завтра в 3 часа в офисе" →
        {{
          "command": {{
            "action": "calendar",
            "operation": "create_event",
            "data": {{
              "title": "Встреча с Даниалом",
              "description": "Деловая встреча с Даниалом",
              "start_date": "<tomorrow's date>T15:00:00",
              "location": "Офис"
            }},
            "answer": "Запланировал встречу с Даниалом на завтра, 15:00, в офисе"
          }}
        }}

        "когда у меня встреча с Даниалом?" →
        {{
          "command": {{
            "action": "calendar",
            "operation": "query_events",
            "data": {{
              "query_type": "specific_event",
              "event_title": "Встреча с Даниалом"
            }},
            "answer": "<based on actual events: either 'У вас встреча с Даниалом завтра в 15:00' or 'Встреч с Даниалом не найдено'>"
          }}
        }}

        "какие встречи у меня на этой неделе?" →
        {{
          "command": {{
            "action": "calendar",
            "operation": "query_events",
            "data": {{
              "query_type": "date_range",
              "start_date": "<this week start>",
              "end_date": "<this week end>"
            }},
            "answer": "<list actual events from the calendar for this week>"
          }}
        }}

        "когда у меня есть свободное время на этой неделе?" →
        {{
          "command": {{
            "action": "calendar",
            "operation": "query_events",
            "data": {{
              "query_type": "free_slots",
              "start_date": "<this week start>",
              "end_date": "<this week end>"
            }},
            "answer": "<analyze actual events and suggest truly free time slots>"
          }}
        }}

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
                return {"command": {"action": "calendar", "operation": "unknown"}}
        return {"command": {"action": "calendar", "operation": "unknown"}}
