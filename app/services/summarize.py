from .voice import get_ai_answer


async def summarize_text_full(text: str, chunk_size: int = 3000) -> str:
    # 1. Делим текст на части
    chunks = split_text_into_chunks(text, chunk_size)

    # 2. Генерируем краткие суммари для каждой части
    partial_summaries = []
    for chunk in chunks:
        summary = await summarize_single_chunk(chunk)
        partial_summaries.append(summary)

    # 3. Финальный суммаризатор
    merged = "\n\n".join(partial_summaries)
    if len(partial_summaries) > 1:
        final_summary = await summarize_final_chunk(merged)
    else:
        final_summary = await summarize_single_chunk(partial_summaries[0])

    return final_summary


def split_text_into_chunks(text: str, max_chars: int = 3000) -> list[str]:
    paragraphs = text.split("\n")
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 1 <= max_chars:
            current += "\n" + p
        else:
            chunks.append(current.strip())
            current = p
    if current:
        chunks.append(current.strip())
    return chunks


async def summarize_single_chunk(chunk: str) -> str:
    prompt = f"""
    You are a summarizer. Language: "As in the TEXT section"
    Summarize the following content in 4–6 sentences.
    No markdown, no lists, just readable text.

    TEXT:
    {chunk}
    """
    return await get_ai_answer(prompt)


async def summarize_final_chunk(chunk: str) -> str:
    prompt = f"""
    You are a summarizer. Language: "As in the TEXT section"
    Summarize the following content in 12-14 sentences.
    No markdown, no lists, just readable text.

    TEXT:
    {chunk}
    """
    return await get_ai_answer(prompt)
