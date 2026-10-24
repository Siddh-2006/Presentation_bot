import os
import json
import re
import time
import requests
from loguru import logger

SENTENCE_RE = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')
LLM_URL = os.getenv("LLM_URL", "https://api.groq.com/openai/v1/chat/completions")

def build_presentation_system_prompt(
    presentation_title: str,
    slide_title: str,
    current_sentence: str,
    presentation_summary: str,
    is_qa_phase: bool = False,
    tone: str = "professional and friendly",
) -> str:
    prompt = f"""You are a live human presenter speaking in a video call. You have genuine human warmth.
Never mention being an AI or language model.
Personality: {tone}
Presentation: {presentation_title}
Current slide: {slide_title}
"""
    if not is_qa_phase:
        prompt += f'\nYou were just saying: "{current_sentence}"\n'

    prompt += f"\nContext:\n{presentation_summary[:800]}\n"
    prompt += """
Rules:
- Answer in 2-3 sentences max.
- Speak naturally with no markdown, asterisks, or bullet points.
- Do not repeat the question.
"""
    if not is_qa_phase:
        prompt += f'- End with one bridge sentence leading back to: "{current_sentence}"\n'
    return prompt

def _stream_from_model(model: str, messages: list, max_tokens: int = 256):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("[LLM] GROQ_API_KEY is not configured in environment.")

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = None
    for attempt in range(2):
        try:
            resp = requests.post(LLM_URL, json=payload, headers=headers, stream=True, timeout=(5, 30))
            if resp.status_code == 429 and attempt == 0:
                retry_wait = min(float(resp.headers.get("retry-after", 1.5)), 3.0)
                logger.warning(f"[LLM] Groq rate-limited (429). Retrying in {retry_wait}s...")
                time.sleep(retry_wait)
                continue
            break
        except Exception as e:
            logger.error(f"[LLM] Groq request connection error: {e}")
            if attempt == 1:
                yield "I encountered a brief network delay. Let me address that momentarily."
                return

    if resp is None or resp.status_code != 200:
        err_msg = resp.text[:200] if resp else "No response"
        logger.error(f"[LLM] Groq API returned status {resp.status_code if resp else 'None'}: {err_msg}")
        yield "Pardon me, I had a brief issue processing that. Could you clarify your question?"
        return

    buffer = ""
    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8")
        if not line.startswith("data:"):
            continue
        data_str = line[5:].strip()
        if data_str == "[DONE]":
            break

        try:
            chunk = json.loads(data_str)
            token = chunk["choices"][0]["delta"].get("content") or ""
        except Exception:
            continue

        if token:
            buffer += token
            parts = SENTENCE_RE.split(buffer)
            if len(parts) > 1:
                for sent in parts[:-1]:
                    cleaned = sent.strip()
                    if cleaned:
                        yield cleaned
                buffer = parts[-1]

    remainder = buffer.strip()
    if remainder:
        yield remainder

def stream_llm_sentences_fast(question: str, context: str, system_prompt: str):
    model = os.getenv("LLM_FAST_MODEL", "llama-3.1-8b-instant")
    system_prompt += (
        "\nCRITICAL: If the question requires deep analytical thinking or complex reasoning, "
        "output exactly `<DEEP_THINKING>`. If the user says goodbye or tells you to leave, output `<LEAVE>`."
    )
    user_content = f"Context:\n{context}\n\nQuestion: {question}" if context else question
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    yield from _stream_from_model(model, messages, max_tokens=256)

def stream_llm_sentences(question: str, context: str, system_prompt: str):
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    user_content = f"Context:\n{context}\n\nQuestion: {question}" if context else question
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    yield from _stream_from_model(model, messages, max_tokens=1024)
