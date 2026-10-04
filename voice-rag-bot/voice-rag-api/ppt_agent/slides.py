import json
from pathlib import Path
from loguru import logger


class SlideStore:
    def __init__(self, json_path: str):
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"[SlideStore] Presentation file not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.title: str = data.get("title", "Untitled")
        self.presentation_id: str = data.get("id", "unknown")
        self.slides: list[dict] = data.get("slides", [])

        logger.info(
            f"[SlideStore] Loaded '{self.title}' — "
            f"{len(self.slides)} slides, "
            f"{sum(len(s['script']) for s in self.slides)} total sentences"
        )

    # ── Sentence access ───────────────────────────────────────────────────────

    def get_sentence(self, slide_idx: int, sentence_idx: int) -> str | None:
        """
        Return the sentence at (slide_idx, sentence_idx).
        Returns None if slide_idx is out of range OR sentence_idx is past
        the end of that slide's script — caller interprets None as
        'advance to next slide'.
        """
        if slide_idx < 0 or slide_idx >= len(self.slides):
            return None
        script = self.slides[slide_idx]["script"]
        if sentence_idx < 0 or sentence_idx >= len(script):
            return None
        return script[sentence_idx]

    # ── Counts ────────────────────────────────────────────────────────────────

    def get_slide_count(self) -> int:
        return len(self.slides)

    def get_script_length(self, slide_idx: int) -> int:
        """Number of sentences in slide at slide_idx (0-based)."""
        if slide_idx < 0 or slide_idx >= len(self.slides):
            return 0
        return len(self.slides[slide_idx]["script"])

    # ── Metadata ──────────────────────────────────────────────────────────────

    def get_slide_context(self, slide_idx: int) -> dict:
        """
        Returns {"number": N, "title": "...", "notes": "..."} for the
        given slide, used to inject context into LLM system prompt.
        """
        if slide_idx < 0 or slide_idx >= len(self.slides):
            return {}
        slide = self.slides[slide_idx]
        return {
            "number": slide.get("number", slide_idx + 1),
            "title":  slide.get("title", ""),
            "notes":  slide.get("notes", ""),
        }

    def get_full_text(self) -> str:
        """
        All slide titles + all script sentences concatenated.
        Used as the presentation-level context string in the LLM system prompt.
        """
        parts: list[str] = [f"Presentation: {self.title}", ""]
        for slide in self.slides:
            parts.append(f"Slide {slide.get('number', '?')}: {slide.get('title', '')}")
            parts.extend(slide.get("script", []))
            parts.append("")          # blank line between slides
        return "\n".join(parts).strip()

    # ── RAG ingestion ─────────────────────────────────────────────────────────

    async def ingest_into_rag(self, app_state, collection_name: str = "products", raw_doc_text: str = "") -> int:
        """
        Ingest the raw document text and every slide's script into a dedicated ChromaDB collection.
        Each session gets its own collection (collection_name = ppt_{session_id})
        so data never bleeds between presentations.

        Returns total number of chunks ingested across all slides.
        """
        from services.rag_service import ingest_document   # existing service

        # Create (or get) the session-specific collection
        self._collection = app_state.chroma_client.get_or_create_collection(collection_name)

        total_chunks = 0
        
        # 1. Ingest raw document text (if provided)
        if raw_doc_text.strip():
            n = await ingest_document(app_state, "raw_document", raw_doc_text, collection=self._collection)
            total_chunks += n
            logger.info(f"[SlideStore] Ingested raw document → {n} chunk(s)")

        # 2. Ingest script slices
        for idx, slide in enumerate(self.slides):
            title      = slide.get("title", f"Slide {idx + 1}")
            script     = slide.get("script", [])
            notes      = slide.get("notes", "")
            text_block = title + "\n" + "\n".join(script)
            if notes:
                text_block += "\n" + notes
            doc_id = f"slide_{idx}"

            n = await ingest_document(app_state, doc_id, text_block,
                                      collection=self._collection)
            total_chunks += n
            logger.info(f"[SlideStore] Ingested {doc_id} → {n} chunk(s)")

        logger.info(f"[SlideStore] RAG ingestion complete — {total_chunks} total chunks")
        return total_chunks

    def get_collection(self):
        """Return the ChromaDB collection created during ingestion."""
        return getattr(self, "_collection", None)

    async def cleanup_rag(self, app_state, collection_name: str):
        """Delete the session-specific ChromaDB collection on teardown."""
        import asyncio
        try:
            def _delete():
                app_state.chroma_client.delete_collection(collection_name)
            await asyncio.to_thread(_delete)
            logger.info(f"[SlideStore] Deleted RAG collection '{collection_name}'")
        except Exception as e:
            logger.warning(f"[SlideStore] Could not delete collection '{collection_name}': {e}")
