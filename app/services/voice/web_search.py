from app.services.voice.ai import get_ai_answer, get_35_ai_answer
from app.core.dependencies.web import handle_web_search

import re
import logging
import langdetect
import json

logger = logging.getLogger(__name__)


async def needs_web_search(text: str) -> tuple[bool, str]:
    """
    Определяет, нужен ли веб-поиск для ответа на вопрос пользователя.
    Возвращает (нужен_ли_поиск, поисковый_запрос)
    """
    prompt = f"""
    Проанализируй вопрос пользователя и определи, нужен ли веб-поиск для получения актуальной информации.
    
    ВЕБ-ПОИСК НУЖЕН для:
    - Погоды (текущая погода, прогноз)
    - Новостей (актуальные события, последние новости)
    - Курсов валют (текущие курсы)
    - Цен на товары/услуги
    - Информации о событиях, концертах, фильмах
    - Статистики (спорт, экономика, политика)
    - Любой информации, которая может измениться со временем
    
    ВЕБ-ПОИСК НЕ НУЖЕН для:
    - Общих знаний (история, наука, факты)
    - Объяснений понятий
    - Советов и рекомендаций общего характера
    - Математических расчетов
    - Личных вопросов
    
    Ответь в формате JSON:
    {{
        "needs_search": true/false,
        "search_query": "поисковый запрос на русском языке"
    }}
    
    Если поиск не нужен, search_query может быть пустым.
    
    Примеры:
    "Какая погода в Москве?" → {{"needs_search": true, "search_query": "погода Москва сегодня"}}
    "Кто такой Пушкин?" → {{"needs_search": false, "search_query": ""}}
    "Какие новости в Казахстане?" → {{"needs_search": true, "search_query": "новости Казахстан сегодня"}}
    "Как приготовить борщ?" → {{"needs_search": false, "search_query": ""}}
    "Курс доллара к рублю" → {{"needs_search": true, "search_query": "курс доллара к рублю сегодня"}}
    
    Вопрос: "{text}"
    """

    try:
        response = await get_ai_answer(prompt)
        # Ищем JSON в ответе

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("needs_search", False), result.get("search_query", "")
        else:
            # Если JSON не найден, попробуем определить по ключевым словам
            search_keywords = [
                "погода",
                "weather",
                "новости",
                "news",
                "курс",
                "курс валют",
                "цена",
                "price",
                "стоимость",
                "расписание",
                "schedule",
                "сегодня",
                "today",
                "сейчас",
                "now",
                "актуальн",
                "current",
            ]
            text_lower = text.lower()
            needs_search = any(keyword in text_lower for keyword in search_keywords)
            return needs_search, text if needs_search else ""
    except Exception as e:
        logger.error(f"Ошибка при определении необходимости поиска: {e}")
        return False, ""


async def process_web_search_results(search_query: str, original_question: str) -> str:
    """
    Processes web search results and generates an answer based on the found information.
    The answer will be in the same language as the original question, determined automatically.
    """
    try:
        # Language detection utility (simple heuristic, can be replaced with a library)
        def detect_language(text):
            try:
                return langdetect.detect(text)
            except ImportError:
                # Fallback: simple heuristic for English/Russian
                cyrillic = re.compile("[\u0400-\u04ff]")
                if cyrillic.search(text):
                    return "ru"
                return "en"

        user_lang = detect_language(original_question)

        # Perform the search
        search_data = await handle_web_search(search_query)

        # Check if we got data
        if not search_data or "organic" not in search_data:
            return f"Could not find any information for request: '{search_query}'."

        # Extract the most relevant results
        organic_results = search_data.get("organic", [])
        if not organic_results:
            return f"Could not find any information for request: '{search_query}'."

        # Take the top 3 results for analysis
        top_results = organic_results[:3]

        # Summarize the results for the AI
        results_summary = []
        for i, result in enumerate(top_results, 1):
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            results_summary.append(f"Result {i}: {title} - {snippet}")

        # Build the prompt for the AI
        prompt = f"""
        Based only on the following web search results, answer the user's question.
        - Always answer in the same language as the user's question (detected: {user_lang}).
        - Use only the information from the search results below.
        - If there is not enough information, say so.
        - Be brief and informative (no more than 2-3 sentences).
        - Cite the source if possible.
        - Do not make up information that is not present in the search results.
        - If there are conflicting data, mention it.

        User question: "{original_question}"
        Search query: "{search_query}"

        Search results:
        {chr(10).join(results_summary)}

        Answer:
        """

        answer = await get_35_ai_answer(prompt)
        if not answer or answer.lower().startswith("error"):
            # Fallback answer based on the first found snippet
            first_result = top_results[0]
            snippet = first_result.get("snippet", "")
            return f"Based on the found information: {snippet[:200]}..."

        return answer.strip()

    except Exception as e:
        logger.error(f"Error processing web search results: {e}")
        return "Sorry, an error occurred while retrieving information. Please try again later."
