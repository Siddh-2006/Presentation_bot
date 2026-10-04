import asyncio
import textwrap

async def retrieve_context(app_state, question: str, top_k: int = 3) -> str:
    def _retrieve():
        emb = app_state.embedder.encode(question).tolist()
        docs = app_state.chroma_col.query(query_embeddings=[emb], n_results=top_k)["documents"][0]
        return "\n---\n".join(docs)
    
    return await asyncio.to_thread(_retrieve)

async def ingest_document(app_state, filename: str, text: str, chunk_size: int = 400) -> int:
    def _ingest():
        chunks = textwrap.wrap(text, width=chunk_size)
        if not chunks:
            return 0
        embeddings = app_state.embedder.encode(chunks).tolist()
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        app_state.chroma_col.add(documents=chunks, embeddings=embeddings, ids=ids)
        return len(chunks)
        
    return await asyncio.to_thread(_ingest)
