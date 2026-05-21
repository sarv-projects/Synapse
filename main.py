from schema.config import get_settings


def main() -> None:
    settings = get_settings()
    print(
        "SYNAPSE v4.0.0 ready: "
        f"domain={settings.default_domain}, "
        f"neo4j_database={settings.neo4j_database}"
    )


if __name__ == "__main__":
    main()
