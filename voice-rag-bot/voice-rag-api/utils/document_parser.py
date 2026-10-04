import os
from loguru import logger

def extract_text_from_document(filepath: str) -> str:
    """
    Extracts raw text from a .pdf or .pptx file.
    Returns the extracted text as a single string.
    """
    if not os.path.exists(filepath):
        logger.warning(f"[DocumentParser] File not found: {filepath}")
        return ""

    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == ".pdf":
        return _extract_from_pdf(filepath)
    elif ext == ".pptx":
        return _extract_from_pptx(filepath)
    elif ext == ".docx":
        return _extract_from_docx(filepath)
    else:
        logger.warning(f"[DocumentParser] Unsupported file extension: {ext}")
        return ""

def _extract_from_pdf(filepath: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        text_parts = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                text_parts.append(f"--- Page {i+1} ---")
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"[DocumentParser] Failed to extract text from PDF {filepath}: {e}")
        return ""

def _extract_from_pptx(filepath: str) -> str:
    try:
        from pptx import Presentation
        prs = Presentation(filepath)
        text_parts = []
        for i, slide in enumerate(prs.slides):
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    slide_text.append(shape.text)
            if slide_text:
                text_parts.append(f"--- Slide {i+1} ---")
                text_parts.append("\n".join(slide_text))
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"[DocumentParser] Failed to extract text from PPTX {filepath}: {e}")
        return ""

def _extract_from_docx(filepath: str) -> str:
    try:
        from docx import Document
        doc = Document(filepath)
        text_parts = []
        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:
                text_parts.append(text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"[DocumentParser] Failed to extract text from DOCX {filepath}: {e}")
        return ""
