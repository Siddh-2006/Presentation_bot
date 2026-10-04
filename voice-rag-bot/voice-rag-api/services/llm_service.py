import os
import requests
import json
import re

SENTENCE_RE = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')


# ── Presentation mode helpers ─────────────────────────────────────────────────

def build_presentation_system_prompt(
    presentation_title: str,
    slide_title: str,
    current_sentence: str,
    presentation_summary: str,
    is_qa_phase: bool = False,
    tone: str = "professional and friendly",
) -> str:
    prompt = f"""You are a live, highly confident, and engaging human presenter speaking naturally in a video call. 
You must NEVER act like a robotic AI, large language model, or virtual assistant. You have genuine human personality, warmth, and natural conversational flow. 
If a specific persona is requested below, fully adopt it. Otherwise, default to being a friendly, confident human expert.
Your personality and tone should be: {tone}

Presentation: {presentation_title}
Current slide: {slide_title}"""

    if not is_qa_phase:
        prompt += f"""
You were just saying: "{current_sentence}"
"""

    prompt += f"""
Full presentation context:
{presentation_summary[:800]}

Rules you must follow:
- Answer the audience question in 2 to 3 sentences maximum.
- Speak naturally, smoothly, and conversationally. No bullet points, no markdown, no special characters.
- You are a human. NEVER mention AI, bots, language models, or virtual assistants.
- Do not repeat the question back."""

    if is_qa_phase:
        prompt += """
- Since the presentation is already over, answer the question and then briefly ask the judges if they have any further questions.
- You must also mention that if there are no further questions, they can permit you to exit the presentation."""
    else:
        prompt += f"""
- End your answer with exactly one bridge sentence that leads back to where you left off.
  The bridge must reference: "{current_sentence}"
  Example bridge: "Now, as I was saying, {current_sentence[:40]}..."
"""

    return prompt


# classify_question removed — routing is now handled dynamically by the fast LLM


def _build_messages(question: str, context: str, system_prompt: str | None) -> list:
    if system_prompt is None:
        system_prompt = (
            "You are a confident, friendly human expert speaking naturally in a conversation. "
            "Never act like a robotic AI or language model. Answer the question organically and concisely in 2-3 sentences. "
            "Do not use markdown, bullet points, or special characters."
        )
    user_content = f"Context:\n{context}\n\nQuestion: {question}" if context else question
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _stream_from_model(model: str, messages: list, num_predict: int = 256, force_local: bool = False):
    """Core streaming generator — yields sentences from Groq or Ollama model."""
    import time
    from loguru import logger
    
    start_t = time.time()
    first_token_t = None
    
    groq_keys_env = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY")
    groq_keys = [k.strip() for k in groq_keys_env.split(",")] if groq_keys_env else []
    
    use_groq = bool(groq_keys and not force_local)
    
    def _do_request(is_groq: bool, api_key: str = None):
        if is_groq:
            llm_url = "https://api.groq.com/openai/v1/chat/completions"
            payload = {
                "model": "llama-3.1-8b-instant",  # Default to fast Llama 3.1 on Groq
                "messages": messages,
                "stream": True,
                "temperature": 0.2,
                "max_tokens": num_predict,
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            logger.info(f"[LLM] Prompting Groq Cloud (llama-3.1-8b-instant) - max_tokens={num_predict} (Key: ...{api_key[-4:] if api_key else ''})...")
        else:
            llm_url = os.getenv("LLM_URL", "http://localhost:11434/api/chat")
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": 0.2,
                    "top_k": 20,
                    "top_p": 0.9,
                    "num_predict": num_predict,
                },
            }
            headers = {}
            logger.info(f"[LLM] Prompting LOCAL Ollama model ({model}) - max_tokens={num_predict}...")
            
        resp = requests.post(
            llm_url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=120,
        )
        if resp.status_code != 200:
            logger.error(f"[LLM] API Error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            
        return resp

    try:
        resp = None
        if use_groq:
            for key in groq_keys:
                try:
                    resp = _do_request(is_groq=True, api_key=key)
                    break # Success, exit loop
                except Exception as e:
                    logger.warning(f"[LLM] Groq API failed for key ...{key[-4:]} ({e}). Trying next key...")
                    continue
            
            # If resp is still None, all Groq keys failed
            if resp is None:
                logger.warning("[LLM] All Groq API keys failed! Falling back to LOCAL model...")
                use_groq = False
                
        if not use_groq:
            resp = _do_request(is_groq=False)

        buffer = ""
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            
            line_str = raw_line.decode('utf-8')
            
            if use_groq:
                if line_str.startswith("data: "):
                    line_str = line_str[6:]
                if line_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(line_str)
                    token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                except:
                    continue
            else:
                try:
                    chunk = json.loads(line_str)
                    msg = chunk.get("message", {})
                    if msg.get("thinking"):
                        continue
                    token = msg.get("content", "")
                    if chunk.get("done"):
                        pass
                except:
                    continue

            if token:
                if first_token_t is None:
                    first_token_t = time.time()
                    logger.debug(f"[LLM] Time to first token (TTFT): {first_token_t - start_t:.2f}s")
                buffer += token
                parts = SENTENCE_RE.split(buffer)
                if len(parts) > 1:
                    for sentence in parts[:-1]:
                        s = sentence.strip()
                        if s:
                            yield s
                    buffer = parts[-1]

        remainder = buffer.strip()
        if remainder:
            yield remainder
            
        dur = time.time() - start_t
        logger.info(f"[LLM] Stream complete in {dur:.2f}s.")

    except Exception as e:
        logger.error(f"[LLM] Error generating response: {e}")
        yield f"I'm sorry, I had trouble answering that. {e}"


def stream_llm_sentences_fast(
    question: str,
    context: str,
    system_prompt: str | None = None,
):
    """
    Fast path — uses LLM_FAST_MODEL (default: qwen2.5:3b).
    Typical latency: 2-4 seconds.
    Instructs the model to output <DEEP_THINKING> if the question is too complex.
    """
    model = os.getenv("LLM_FAST_MODEL", "qwen2.5:3b")
    
    if system_prompt:
        system_prompt += (
            "\n\nCRITICAL RULE: If the user's question requires complex reasoning, "
            "deep logical analysis, or practical implementation steps, OR if you do not know the answer and are tempted to bluff, "
            "you MUST output exactly `<DEEP_THINKING>` and nothing else."
            "\n\nCRITICAL RULE 2: If the user explicitly states they have no questions, "
            "or tells you to leave, stop, or end the meeting, "
            "you MUST output exactly `<LEAVE>` and nothing else."
        )
        
    messages = _build_messages(question, context, system_prompt)
    yield from _stream_from_model(model, messages, num_predict=256)


def stream_llm_sentences(
    question: str,
    context: str,
    system_prompt: str | None = None,
):
    """
    Deep path — uses LLM_MODEL (default: gemma4:e2b, a reasoning model).
    Typical latency: 20-40 seconds. Use only for complex questions.
    ALWAYS forces local execution since Groq doesn't host Gemma.
    """
    model = os.getenv("LLM_MODEL", "gemma4:e2b")
    messages = _build_messages(question, context, system_prompt)
    yield from _stream_from_model(model, messages, num_predict=1024, force_local=True)

