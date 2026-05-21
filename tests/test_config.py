from schema.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.default_domain == "ai"
    assert settings.max_query_results == 50
