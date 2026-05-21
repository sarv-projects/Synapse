"""spaCy NLP pipeline for NER, dependency parsing, and fastcoref."""
import logging

logger = logging.getLogger(__name__)


class SpacyPipeline:
    """spaCy en_core_web_trf + fastcoref for local NLP processing."""

    def __init__(self):
        self._nlp = None
        self._loaded = False

    async def load(self):
        if self._loaded:
            return
        try:
            import spacy
            self._nlp = spacy.load("en_core_web_trf")
            self._loaded = True
            logger.info("spaCy en_core_web_trf loaded")
        except Exception as e:
            logger.warning(f"spaCy model not available: {e}")

    async def extract_entities(self, text: str) -> list[dict]:
        await self.load()
        if not self._nlp:
            return []
        doc = self._nlp(text[:10000])
        return [
            {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
            for ent in doc.ents
        ]


_spacy_pipeline: SpacyPipeline | None = None


def get_spacy_pipeline() -> SpacyPipeline:
    global _spacy_pipeline
    if _spacy_pipeline is None:
        _spacy_pipeline = SpacyPipeline()
    return _spacy_pipeline
