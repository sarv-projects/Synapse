"""Quick script to check which API endpoints work and what fields they return."""
import httpx, json

def check(name, url, params=None):
    try:
        r = httpx.get(url, params=params or {}, timeout=10, follow_redirects=True)
        print(f"\n{name}: {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            items = d if isinstance(d, list) else d.get("results", d.get("papers", d.get("models", [])))
            if items:
                print(f"  count: {len(items)}")
                print(f"  keys: {list(items[0].keys())[:8]}")
    except Exception as e:
        print(f"\n{name}: ERROR — {e}")

check("HF models (downloads)", "https://huggingface.co/api/models", {"sort": "downloads", "limit": 5, "direction": -1})
check("HF models (likes)", "https://huggingface.co/api/models", {"sort": "likes", "limit": 5, "direction": -1})
check("arXiv", "https://export.arxiv.org/api/query", {"search_query": "cat:cs.AI", "max_results": 3, "sortBy": "submittedDate", "sortOrder": "descending"})
check("Papers With Code", "https://paperswithcode.com/api/v1/papers/", {"items_per_page": 5})
check("Semantic Scholar", "https://api.semanticscholar.org/graph/v1/paper/search", {"query": "large language model", "limit": 3, "fields": "title,year,authors"})
