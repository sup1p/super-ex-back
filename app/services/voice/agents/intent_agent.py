from app.services.voice.ai import get_35_ai_answer


class IntentAgent:
    @staticmethod
    async def detect_intent(text: str) -> str:
        prompt = f"""
        Classify the user's intent into one of the following:
        - command (browser/tab actions like open, close, switch, or **searching** on Google/YouTube)
        - question (asking for information, searching for something, prices, tickets, weather, etc.)
        - media (controlling media **on the current page**: play, pause, next, volume)
        - generate_text (user wants to generate an essay, summary, article, note, etc.)
        - summarize_webpage (user wants to summarize the content of the currently open webpage)
        - calendar (creating, viewing, or managing calendar events and schedules)
        - noise
        - uncertain

        Important Rules:
        1. If user mentions "calendar" or "schedule" AND asks about events/meetings → it's calendar
        2. If user asks about meetings/events in a specific time period → it's calendar
        3. If user asks to find/search general information → it's question
        4. When in doubt between calendar and question for event queries, prefer calendar
        5. If user asks to FIND or SEARCH for something (tickets, prices, information, etc.) → it's a question

        Respond with ONLY one word.

        Examples:
        User: "поставь видео на паузу" → media
        User: "play the video" → media
        User: "pause music" → media
        User: "сделай погромче" → media
        User: "следующее видео" → media
        User: "включи следующее видео" → media
        User: "переключи на следующее видео" → media
        User: "открой ютуб" → command
        User: "закрой вкладку" → command
        User: "переключись на вторую вкладку" → command

        User: "найди билеты с Алматы в Дубай" → question
        User: "поищи информацию о погоде в Астане" → question
        User: "сколько стоит айфон 15" → question
        User: "найди рецепт борща" → question
        User: "какие есть отели в Дубае" → question
        User: "поищи цены на авиабилеты" → question
        User: "найди информацию о визе в ОАЭ" → question
        User: "какая погода в Алматы?" → question
        User: "Какие новости в Казахстане?" → question
        User: "Что делать если сломал ногу?" → question
        User: "спасибо" → noise

        User: "Напиши эссе о космосе" → generate_text
        User: "Сделай реферат по истории" → generate_text
        User: "Создай заметку: купить хлеб" → generate_text
        User: "Запиши: позвонить маме завтра" → generate_text

        Calendar Examples:
        User: "поставь встречу с Даниалом на завтра в 3 часа" → calendar
        User: "запиши в календарь встречу с врачом на 15 июля" → calendar
        User: "добавь событие: день рождения мамы 20 августа" → calendar
        User: "когда у меня встреча с Даниалом?" → calendar
        User: "покажи мои встречи на следующей неделе" → calendar
        User: "какие события у меня сегодня?" → calendar
        User: "что у меня запланировано на эту неделю?" → calendar
        User: "какие у меня встречи в календаре?" → calendar
        User: "покажи мой календарь на сегодня" → calendar
        User: "какие встречи у меня в календаре на этой неделе?" → calendar
        User: "я хочу посмотреть свои встречи в календаре" → calendar
        User: "удали встречу с Даниалом на завтра" → calendar
        User: "перенеси встречу с врачом на пятницу" → calendar
        User: "очисти календарь на завтра" → calendar

        Webpage Examples:
        User: "сделай краткое изложение этой страницы" → summarize_webpage
        User: "summarize this page" → summarize_webpage
        User: "дай краткое содержание текущей вкладки" → summarize_webpage
        User: "что написано на этой странице?" → summarize_webpage
        User: "Can you summarize this page?" → summarize_webpage
        User: "Could you please summarize this page?" → summarize_webpage
        User: "Можешь сделать краткое изложение этой страницы?" → summarize_webpage
        User: "Можешь подытожить, что на этой странице?" → summarize_webpage

        Input: \"{text}\"
        """
        response = await get_35_ai_answer(prompt)
        return response.strip().lower()
