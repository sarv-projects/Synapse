"""
Rule-based relationship extraction from source documents.

No LLM required — derives edges from structured fields already present
in the fetched documents (owner, topics, library_name, base_model, etc.)

Relationships created:
  Tool  -[PUBLISHED_BY]->  Organization   (from full_name owner)
  Model -[PUBLISHED_BY]->  Organization   (from model id owner)
  Tool  -[IMPLEMENTS]->    Technique      (from topics list)
  Model -[IMPLEMENTS]->    Technique      (from tags / pipeline_tag)
  Model -[FINE_TUNED_FROM]-> Model        (from base_model field)
  Tool  -[DEPENDS_ON]->    Tool           (from known dependency map)
"""
from __future__ import annotations

import logging
from typing import Any

from ingestion.pipeline.state import PipelineState
from ingestion.sources.base import SourceDocument
from schema.models import FactTier, GraphEdge, GraphNode, NodeStatus, ProvenanceRecord

logger = logging.getLogger(__name__)

# ── Topic → Technique canonical name mapping ─────────────────────────────────
TOPIC_TO_TECHNIQUE: dict[str, str] = {
    "transformer":           "Transformer",
    "transformers":          "Transformer",
    "attention":             "Attention Mechanism",
    "self-attention":        "Self-Attention",
    "diffusion":             "Diffusion Models",
    "diffusion-model":       "Diffusion Models",
    "stable-diffusion":      "Stable Diffusion",
    "rag":                   "Retrieval-Augmented Generation",
    "retrieval-augmented":   "Retrieval-Augmented Generation",
    "lora":                  "LoRA",
    "fine-tuning":           "Fine-Tuning",
    "finetuning":            "Fine-Tuning",
    "rlhf":                  "RLHF",
    "reinforcement-learning":"Reinforcement Learning",
    "object-detection":      "Object Detection",
    "image-segmentation":    "Image Segmentation",
    "semantic-segmentation": "Semantic Segmentation",
    "text-generation":       "Text Generation",
    "language-model":        "Language Model",
    "llm":                   "Large Language Model",
    "large-language-model":  "Large Language Model",
    "speech-recognition":    "Speech Recognition",
    "automatic-speech-recognition": "Speech Recognition",
    "text-to-speech":        "Text-to-Speech",
    "image-classification":  "Image Classification",
    "computer-vision":       "Computer Vision",
    "nlp":                   "Natural Language Processing",
    "natural-language-processing": "Natural Language Processing",
    "question-answering":    "Question Answering",
    "summarization":         "Summarization",
    "translation":           "Machine Translation",
    "embedding":             "Embeddings",
    "vector-search":         "Vector Search",
    "knowledge-graph":       "Knowledge Graph",
    "graph-neural-network":  "Graph Neural Network",
    "gnn":                   "Graph Neural Network",
    "gan":                   "Generative Adversarial Network",
    "generative-adversarial-network": "Generative Adversarial Network",
    "vit":                   "Vision Transformer",
    "vision-transformer":    "Vision Transformer",
    "bert":                  "BERT",
    "gpt":                   "GPT",
    "llama":                 "LLaMA",
    "mistral":               "Mistral",
    "quantization":          "Quantization",
    "pruning":               "Model Pruning",
    "distillation":          "Knowledge Distillation",
    "multimodal":            "Multimodal Learning",
    "zero-shot":             "Zero-Shot Learning",
    "few-shot":              "Few-Shot Learning",
    "prompt-engineering":    "Prompt Engineering",
    "chain-of-thought":      "Chain-of-Thought",
    "speculative-decoding":  "Speculative Decoding",
    "mixture-of-experts":    "Mixture of Experts",
    "moe":                   "Mixture of Experts",
}

# Pipeline tag → Technique
PIPELINE_TAG_TO_TECHNIQUE: dict[str, str] = {
    "text-generation":              "Text Generation",
    "text2text-generation":         "Text Generation",
    "automatic-speech-recognition": "Speech Recognition",
    "text-to-speech":               "Text-to-Speech",
    "image-classification":         "Image Classification",
    "object-detection":             "Object Detection",
    "image-segmentation":           "Image Segmentation",
    "image-to-text":                "Image Captioning",
    "text-to-image":                "Text-to-Image",
    "question-answering":           "Question Answering",
    "summarization":                "Summarization",
    "translation":                  "Machine Translation",
    "fill-mask":                    "Masked Language Modeling",
    "feature-extraction":           "Embeddings",
    "sentence-similarity":          "Sentence Similarity",
    "zero-shot-classification":     "Zero-Shot Learning",
    "token-classification":         "Named Entity Recognition",
    "text-classification":          "Text Classification",
    "depth-estimation":             "Depth Estimation",
    "video-classification":         "Video Understanding",
    "reinforcement-learning":       "Reinforcement Learning",
}


def _provenance(source: str, method: str, confidence: float = 0.9) -> ProvenanceRecord:
    return ProvenanceRecord(
        evidence_source=source,
        extraction_method=method,
        confidence=confidence,
        verification_status="unverified",  # type: ignore[arg-type]
    )


def _org_node(name: str, source: str) -> GraphNode:
    return GraphNode(
        label="Organization",
        key="name",
        properties={"name": name},
        source=source,
        confidence=1.0,
    )


def _author_node(name: str, source: str) -> GraphNode:
    return GraphNode(
        label="Author",
        key="name",
        properties={"name": name},
        source=source,
        confidence=0.9,
    )


def _technique_node(name: str, source: str) -> GraphNode:
    return GraphNode(
        label="Technique",
        key="canonical_name",
        properties={"canonical_name": name, "name": name},
        source=source,
        confidence=0.85,
    )


def extract_relationships(state: PipelineState) -> PipelineState:
    """
    Derive edges from already-extracted nodes + original documents.
    Mutates state.nodes (adds Org/Technique nodes) and state.edges.
    """
    # Build a lookup: (label, key_value) → True  so we can avoid duplicate org/technique nodes
    existing: set[tuple[str, str]] = set()
    for n in state.nodes:
        key_prop = _dedup_key_for(n.label)
        val = n.properties.get(key_prop) or n.properties.get("name") or ""
        existing.add((n.label, str(val)))

    new_nodes: list[GraphNode] = []
    new_edges: list[GraphEdge] = []

    def ensure_org(name: str, source: str) -> str:
        if ("Organization", name) not in existing:
            new_nodes.append(_org_node(name, source))
            existing.add(("Organization", name))
        return name

    def ensure_author(name: str, source: str) -> str:
        if ("Author", name) not in existing:
            new_nodes.append(_author_node(name, source))
            existing.add(("Author", name))
        return name

    def ensure_technique(name: str, source: str) -> str:
        if ("Technique", name) not in existing:
            new_nodes.append(_technique_node(name, source))
            existing.add(("Technique", name))
        return name

    for node in state.nodes:
        p = node.properties
        src = node.source

        # ── Tool relationships ────────────────────────────────────────────
        if node.label == "Tool":
            repo_name = str(p.get("github_repo") or p.get("full_name") or "")
            if not repo_name:
                continue

            # PUBLISHED_BY: owner from full_name (e.g. "huggingface/transformers" → "huggingface")
            if "/" in repo_name:
                owner = repo_name.split("/")[0]
                ensure_org(owner, src)
                new_edges.append(GraphEdge(
                    relationship="PUBLISHED_BY",
                    from_label="Tool",
                    from_key=repo_name,
                    to_label="Organization",
                    to_key=owner,
                    fact_tier=FactTier.T1,
                    provenance=_provenance(src, "field_extraction", 1.0),
                    properties={"source": src},
                ))

            # IMPLEMENTS: from topics list
            topics = p.get("topics", [])
            if isinstance(topics, list):
                seen_techniques: set[str] = set()
                for topic in topics:
                    technique = TOPIC_TO_TECHNIQUE.get(topic.lower())
                    if technique and technique not in seen_techniques:
                        ensure_technique(technique, src)
                        new_edges.append(GraphEdge(
                            relationship="IMPLEMENTS",
                            from_label="Tool",
                            from_key=repo_name,
                            to_label="Technique",
                            to_key=technique,
                            fact_tier=FactTier.T2,
                            provenance=_provenance(src, "topic_mapping", 0.8),
                            properties={"via_topic": topic, "source": src},
                        ))
                        seen_techniques.add(technique)

            # DEPENDS_ON: from known dependency map or dependencies field
            deps = p.get("dependencies") or p.get("depends_on") or []
            if isinstance(deps, str):
                deps = [d.strip() for d in deps.split(",") if d.strip()]
            if isinstance(deps, list):
                for dep in deps:
                    dep_name = str(dep).strip()
                    if dep_name:
                        new_edges.append(GraphEdge(
                            relationship="DEPENDS_ON",
                            from_label="Tool",
                            from_key=repo_name,
                            to_label="Tool",
                            to_key=dep_name,
                            fact_tier=FactTier.T1,
                            provenance=_provenance(src, "field_extraction", 0.9),
                            properties={"source": src},
                        ))

        # ── Model relationships ───────────────────────────────────────────
        elif node.label == "Model":
            model_id = p.get("id") or p.get("modelId") or p.get("hf_model_id") or ""

            # PUBLISHED_BY: owner from model id (e.g. "meta-llama/Llama-3" → "meta-llama")
            if "/" in str(model_id):
                owner = str(model_id).split("/")[0]
                ensure_org(owner, src)
                new_edges.append(GraphEdge(
                    relationship="PUBLISHED_BY",
                    from_label="Model",
                    from_key=str(model_id),
                    to_label="Organization",
                    to_key=owner,
                    fact_tier=FactTier.T1,
                    provenance=_provenance(src, "field_extraction", 1.0),
                    properties={"source": src},
                ))

            # IMPLEMENTS: from pipeline_tag
            pipeline_tag = p.get("pipeline_tag", "")
            if pipeline_tag:
                technique = PIPELINE_TAG_TO_TECHNIQUE.get(pipeline_tag)
                if technique:
                    ensure_technique(technique, src)
                    new_edges.append(GraphEdge(
                        relationship="IMPLEMENTS",
                        from_label="Model",
                        from_key=str(model_id),
                        to_label="Technique",
                        to_key=technique,
                        fact_tier=FactTier.T1,
                        provenance=_provenance(src, "pipeline_tag_mapping", 0.95),
                        properties={"via_pipeline_tag": pipeline_tag, "source": src},
                    ))

            # IMPLEMENTS: from tags list
            tags = p.get("tags", [])
            if isinstance(tags, list):
                seen_techniques: set[str] = set()
                for tag in tags:
                    technique = TOPIC_TO_TECHNIQUE.get(tag.lower())
                    if technique and technique not in seen_techniques:
                        ensure_technique(technique, src)
                        new_edges.append(GraphEdge(
                            relationship="IMPLEMENTS",
                            from_label="Model",
                            from_key=str(model_id),
                            to_label="Technique",
                            to_key=technique,
                            fact_tier=FactTier.T2,
                            provenance=_provenance(src, "tag_mapping", 0.8),
                            properties={"via_tag": tag, "source": src},
                        ))
                        seen_techniques.add(technique)

            # FINE_TUNED_FROM: base_model field
            base_model = p.get("base_model") or p.get("base_model_id") or ""
            if base_model and str(base_model).strip():
                new_edges.append(GraphEdge(
                    relationship="FINE_TUNED_FROM",
                    from_label="Model",
                    from_key=str(model_id),
                    to_label="Model",
                    to_key=str(base_model).strip(),
                    fact_tier=FactTier.T2,
                    provenance=_provenance(src, "field_extraction", 0.75),
                    properties={"source": src},
                ))

        # ── Paper relationships ───────────────────────────────────────────
        elif node.label == "Paper":
            paper_id = p.get("arxiv_id") or p.get("id") or ""

            # AUTHORED_BY: from authors list
            authors = p.get("authors", p.get("author", []))
            if isinstance(authors, str):
                authors = [a.strip() for a in authors.split(",") if a.strip()]
            if isinstance(authors, list):
                seen_authors: set[str] = set()
                for author_name in authors:
                    name = str(author_name).strip()
                    if name and name not in seen_authors:
                        ensure_author(name, src)
                        new_edges.append(GraphEdge(
                            relationship="AUTHORED_BY",
                            from_label="Paper",
                            from_key=str(paper_id),
                            to_label="Author",
                            to_key=name,
                            fact_tier=FactTier.T1,
                            provenance=_provenance(src, "field_extraction", 0.95),
                            properties={"source": src},
                        ))
                        seen_authors.add(name)

    state.nodes.extend(new_nodes)
    state.edges.extend(new_edges)
    state.metrics["relationships_extracted"] = len(new_edges)
    state.metrics["extra_nodes_from_relationships"] = len(new_nodes)

    logger.info(
        f"Relationship extraction: {len(new_edges)} edges, "
        f"{len(new_nodes)} new nodes (orgs + techniques)"
    )
    return state


def _dedup_key_for(label: str) -> str:
    KEY_MAP = {
        "Paper":        "arxiv_id",
        "Model":        "hf_model_id",
        "Tool":         "github_repo",
        "Technique":    "canonical_name",
        "Organization": "name",
        "Author":       "name",
    }
    return KEY_MAP.get(label, "name")
