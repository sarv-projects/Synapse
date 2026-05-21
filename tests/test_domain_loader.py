from schema.domain_loader import load_domain_pack


def test_domain_pack_loads() -> None:
    domain_pack = load_domain_pack("ai")
    assert "node_types" in domain_pack.schema
    assert len(domain_pack.aliases) > 10
