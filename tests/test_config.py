from schema.config import Settings


def test_settings_defaults() -> None:
    """Optional fields keep their declared defaults when only required
    fields (neo4j_uri, cors_origins) are supplied."""
    settings = Settings(
        neo4j_uri="bolt://localhost:7687",
        cors_origins=["http://localhost:5173"],
    )
    assert settings.default_domain == "ai"
    assert settings.max_query_results == 50
    assert settings.neo4j_username == "neo4j"
    assert settings.api_version == "v1"
