from api.query import plan_query, validate_cypher


def test_query_plan_uses_safe_template() -> None:
    answer = plan_query("what is new today")
    assert "MATCH" in answer.cypher
    assert answer.fact_tier.value == "T1"


def test_validator_rejects_create() -> None:
    warnings = validate_cypher("CREATE (n) RETURN n LIMIT 10")
    assert any("Forbidden token" in warning for warning in warnings)
