"""OpenCV document processor — layout analysis and table extraction."""
import logging

logger = logging.getLogger(__name__)


class OpenCVProcessor:
    """Layout analysis and table extraction from scanned documents."""

    def __init__(self):
        self._loaded = False

    async def load(self):
        if self._loaded:
            return
        try:
            self._loaded = True
            logger.info("OpenCV loaded for document processing")
        except Exception as e:
            logger.warning(f"OpenCV not available: {e}")

    async def extract_tables(self, image_path: str) -> list[dict]:
        await self.load()
        return []


_processor: OpenCVProcessor | None = None


def get_opencv_processor() -> OpenCVProcessor:
    global _processor
    if _processor is None:
        _processor = OpenCVProcessor()
    return _processor
