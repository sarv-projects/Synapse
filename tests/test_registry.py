from ingestion.source_factory import SourceFactory


def test_all_spec_sources_have_fetchers() -> None:
    factory = SourceFactory()
    source_names = factory.get_all_source_names()
    assert len(source_names) >= 9


def test_source_factory_creates_fetchers() -> None:
    factory = SourceFactory()
    fetchers = factory.create_all_fetchers()
    assert len(fetchers) >= 9
    for name, fetcher in fetchers.items():
        assert fetcher is not None
