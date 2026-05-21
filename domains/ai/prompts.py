PAPER_ENTITY_EXTRACTION_PROMPT = """
You are extracting canonical graph entities from AI ecosystem documents.
Return structured JSON with papers, techniques, models, organizations, and evidence snippets.
"""


RELATIONSHIP_EXTRACTION_PROMPT = """
Identify typed relationships only when the source provides explicit evidence.
Return fact tier, confidence, evidence source, and a short supporting snippet.
"""
