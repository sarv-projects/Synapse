"""Inference providers package."""

# Re-export groq_manager access for modules that shouldn't depend on api/
def get_groq_manager():
    """Lazy accessor to avoid circular imports."""
    from api.groq_manager import get_groq_manager as _get
    return _get()
