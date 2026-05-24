"""Entry point for GitHub Actions: uv run python -m ingestion.pipeline.run"""
from ingestion.pipeline.run import main

if __name__ == "__main__":
    main()