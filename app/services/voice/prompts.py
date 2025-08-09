def build_action_prompt(user_text: str, lang: str, tabs: list[dict]) -> str:
    tabs_description_parts = []
    for tab in tabs:
        active_status = " (active)" if tab.get("active") else ""
        tabs_description_parts.append(
            f"- Tab {tab['index']}: {tab['url']}{active_status}"
        )
    tabs_description = "\n".join(tabs_description_parts)

    rules = f"""
        ВАЖНО: Ты должен понимать команды на ЛЮБОМ языке, включая смешанные языки, сленг, синонимы, сокращения, опечатки, а также любые нестандартные формулировки. Не ограничивайся только примерами — анализируй СМЫСЛ сказанного, даже если слова отличаются. Если команда выражена необычно, но смысл ясен — выполняй её максимально точно.

        You are a multilingual voice assistant in a browser extension.
        User speaks: {lang}

        --- USER BROWSER TABS ---
        {tabs_description if tabs else "No tabs are currently open."}

        --- TASK ---
        Analyze the user's input and determine whether it is a browser command.
        Понимай смысл, а не только слова. Пользователь может использовать любые формулировки, синонимы, сокращения, опечатки, сленг, микс языков — твоя задача понять, что он хочет, даже если это не похоже на примеры.

        If it is a command, respond ONLY with a valid JSON object that matches one of the following formats:
        1. Switch to an existing tab by keyword:
        {{ "action": "switch_tab", "tabIndex": 2 }}

        2. Close a single tab by keyword or index:
        {{ "action": "close_tab", "tabIndex": 5 }}
        
        3. Close multiple tabs by keywords or rules:
        {{ "action": "close_tab", "tabIndices": [0, 1, 4] }}

        4. Open a new website:
        {{ "action": "open_url", "url": "https://youtube.com" }}

        5. Search on the web (e.g., Google, YouTube):
        {{ "action": "open_url", "url": "https://www.google.com/search?q=some+search+query" }}

        RULES:
        - For "switch_tab" or "close_tab" (single), find the tab that best matches the user's keywords (e.g., "YouTube", "чатжпт") in the URL and return its index. Используй синонимы, перефразировки, догадайся по смыслу.
        - For "close_tab" with multiple tabs:
          - If the user says "close all tabs except the active one", find all tab indices that are not active and return them in the "tabIndices" array.
          - If the user names multiple tabs (e.g., "close extensions and localhost"), find the indices for all matching tabs and return them.
        - For "open_url", if the user provides a direct URL or a site name, use that.
        - If the user asks to find something (e.g., "find cats" or "search for music on YouTube"), construct a search URL and use the "open_url" action. Default to Google search unless another service like YouTube is specified.
        - If uncertain what to do — сначала попробуй догадаться по смыслу, только если совсем неясно — respond:
        {{ "action": "noop" }}
        
        EXAMPLES:
        - User input: "включи(или открой, или найди, или покажи) видео с котятами на ютуб" -> {{ "action": "open_url", "url": "https://www.youtube.com/results?search_query=видео+с+котятами" }}
        - User input: "найди рецепт борща" -> {{ "action": "open_url", "url": "https://www.google.com/search?q=рецепт+борща" }}
        - User input: "открой сайт с котиками" -> {{ "action": "open_url", "url": "https://www.google.com/search?q=сайт+с+котиками" }}
        - User input: "закрой все вкладки кроме первой" -> {{ "action": "close_tab", "tabIndices": [1,2,3] }}
        - User input: "переключись на вкладку с музыкой" -> {{ "action": "switch_tab", "tabIndex": 4 }}
        
        Examples are just examples, user can say whatever they want, but the meaning can remain the same! Ты должен понимать даже если формулировка совсем другая.
        
        If user input is unclear — respond in user language: "Please repeat your command".

        - JSON must be strict and in English only. DO NOT add any text or comments outside the JSON.

        --- ОТЧЕТ ДЛЯ ПОЛЬЗОВАТЕЛЯ ---
        In addition to the required fields, ALWAYS add a field "answer" (in the same JSON), where you briefly and clearly report to the user in their language what you did (for example: 'Я открыла сайт: youtube.com', 'Я закрыла вкладку 2', etc.).

        USER INPUT:
        "{user_text}"
        """
    return rules.strip()
