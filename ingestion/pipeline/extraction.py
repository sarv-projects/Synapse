from __future__ import annotations

from ingestion.pipeline.state import PipelineState
from schema.models import GraphNode, NodeStatus


def fast_path_transform(state: PipelineState) -> PipelineState:
    for document in state.documents:
        properties = dict(document.payload)
        key_map = {
            "Paper": "arxiv_id",
            "Model": "hf_model_id",
            "Tool": "github_repo",
            "Technique": "canonical_name",
            "Organization": "name",
        }

        if document.entity_type == "Tool":
            repository = properties.get("repository")
            repo_name = (
                properties.get("github_repo")
                or properties.get("full_name")
                or (repository.get("full_name") if isinstance(repository, dict) else repository)
                or properties.get("name")
            )
            if repo_name:
                properties.setdefault("github_repo", str(repo_name))
                properties.setdefault("full_name", str(repo_name))

        if document.entity_type == "Paper":
            # Map OpenAlex authorship schema to standard authors list
            authorships = properties.get("authorships")
            if isinstance(authorships, list):
                authors = []
                for auth in authorships:
                    if isinstance(auth, dict) and "author" in auth:
                        author_name = auth["author"].get("display_name")
                        if author_name:
                            authors.append(author_name)
                properties.setdefault("authors", authors)
            
            # Map doi/id to arxiv_id dedup key
            if "doi" in properties and properties["doi"]:
                properties.setdefault("arxiv_id", str(properties["doi"]))
            else:
                properties.setdefault("arxiv_id", str(properties.get("id", "")))

        key = key_map.get(document.entity_type, "name")
        state.nodes.append(
            GraphNode(
                label=document.entity_type,
                key=key,
                properties=properties,
                source=document.source_name,
                status=NodeStatus.NEW,
                confidence=0.8,
            )
        )
    state.metrics["fast_path_nodes"] = len(state.nodes)
    return state
