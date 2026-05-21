SAFE_QUERY_TEMPLATES = {
    "whats_new": "MATCH (n) WHERE n.status = 'new' RETURN n ORDER BY n.created_at DESC LIMIT 50",
    "top_tools": "MATCH (t:Tool) RETURN t ORDER BY t.github_stars DESC LIMIT 20",
    "org_releases": """
        MATCH (o:Organization {name: $name})<-[:PUBLISHED_BY]-(n)
        RETURN n
        ORDER BY n.published_date DESC
        LIMIT 50
    """,
}
