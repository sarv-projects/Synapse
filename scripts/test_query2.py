import httpx
import json

r = httpx.post(
    "http://127.0.0.1:8082/api/v1/query",
    json={"natural_query": "show me the most starred AI tools"},
    timeout=30
)
d = r.json()
print("Cypher:", d.get("cypher_query"))
print("First result:", json.dumps(d.get("results", [{}])[0], indent=2, default=str))
