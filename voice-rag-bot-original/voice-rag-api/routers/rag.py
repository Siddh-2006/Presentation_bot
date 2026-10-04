import json
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from models.schemas import AskRequest, IngestResponse
from services.rag_service import retrieve_context, ingest_document
from services.llm_service import stream_llm_sentences
import asyncio

router = APIRouter()

@router.post("/ask")
async def api_ask(request: Request, ask_req: AskRequest):
    """
    HTTP streaming via SSE. Runs RAG -> LLM -> streams sentences.
    """
    if not ask_req.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty")

    context = await retrieve_context(request.app.state, ask_req.transcript)
    
    async def event_generator():
        # Iterate over the synchronous generator from LLM service in a separate thread
        # Because stream_llm_sentences yields strings (blocking on network), we need an async wrapper
        def fetch_next(gen):
            try:
                return next(gen)
            except StopIteration:
                return None
                
        gen = stream_llm_sentences(ask_req.transcript, context, system_prompt=ask_req.system_prompt)
        
        while True:
            sentence = await asyncio.to_thread(fetch_next, gen)
            if sentence is None:
                break
            
            data = json.dumps({"sentence": sentence, "done": False})
            yield f"data: {data}\n\n"
            
        # Final event
        final_data = json.dumps({"sentence": "", "done": True})
        yield f"data: {final_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/ingest", response_model=IngestResponse)
async def api_ingest(request: Request, file: UploadFile = File(...)):
    """
    Accepts text or pdf, chunks, embeds, and upserts to ChromaDB.
    """
    try:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        
        chunks_added = await ingest_document(request.app.state, file.filename, text)
        return IngestResponse(chunks_added=chunks_added)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
