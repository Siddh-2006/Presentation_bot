import os
import requests
import json
import re

SENTENCE_RE = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')

def stream_llm_sentences(question: str, context: str):
    llm_url = os.getenv("LLM_URL", "http://localhost:11434/api/chat")
    llm_model = os.getenv("LLM_MODEL", "gemma2:2b")
    
    messages = [
        {
            "role": "system",
            "content": (
                "You are a concise e-commerce voice assistant for Flipkart. "
                "Answer using ONLY the context provided. "
                "Reply in 2 sentences maximum. No bullet points. "
                "Speak naturally since your answer will be read aloud."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        },
    ]

    try:
        resp = requests.post(
            llm_url,
            json={
                "model": llm_model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": 0.2,
                    "top_k": 20,
                    "top_p": 0.9
                },
            },
            stream=True,
            timeout=120,
        )
        
        buffer = ""
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            print(f"[llm DEBUG] RAW CHUNK: {raw_line}")
            chunk = json.loads(raw_line)
            token = chunk.get("message", {}).get("content", "")
            buffer += token

            parts = SENTENCE_RE.split(buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    s = sentence.strip()
                    if s:
                        yield s
                buffer = parts[-1]

            if chunk.get("done"):
                break

        remainder = buffer.strip()
        if remainder:
            yield remainder

    except Exception as e:
        print(f"[llm] Error: {e}")
        yield f"I'm sorry, I encountered an error: {str(e)}"
