"""Integration tests for graph export formats.

These tests don't need a live Neo4j. They test the format converters
(JSON-LD, CSV, GraphML, GEXF) in isolation by feeding them pre-built
node/edge lists.
"""
from __future__ import annotations

import io
import json
import zipfile
import xml.etree.ElementTree as ET

import pytest

from export.graph_exporter import (
    GraphExporter,
    _xml_escape,
    _stringify_value,
)


pytestmark = pytest.mark.integration


SAMPLE_NODES = [
    {
        "id": "node-1",
        "labels": ["Paper"],
        "properties": {
            "title": "Attention Is All You Need",
            "year": 2017,
            "authors": ["Vaswani", "Shazeer"],
            "embedding": [0.1, 0.2, 0.3],
        },
    },
    {
        "id": "node-2",
        "labels": ["Model", "Transformer"],
        "properties": {
            "name": "GPT-4",
            "params": 1_800_000_000_000,
            "embedding": [0.4, 0.5, 0.6],
        },
    },
]
SAMPLE_EDGES = [
    {
        "id": "edge-1",
        "type": "CITES",
        "start_node": "node-1",
        "end_node": "node-2",
        "properties": {"weight": 0.95, "year": 2018},
    },
    {
        "id": "edge-2",
        "type": "USES",
        "start_node": "node-2",
        "end_node": "node-1",
        "properties": {"weight": 0.5},
    },
]


class TestXmlEscaping:
    def test_escapes_ampersand(self):
        assert _xml_escape("A & B") == "A &amp; B"

    def test_escapes_angle_brackets(self):
        assert _xml_escape("<tag>") == "&lt;tag&gt;"

    def test_escapes_quotes(self):
        assert _xml_escape('"quoted"') == "&quot;quoted&quot;"
        assert _xml_escape("'apos'") == "&apos;apos&apos;"

    def test_no_special_chars_passes_through(self):
        assert _xml_escape("hello world") == "hello world"


class TestStringify:
    def test_list_to_json(self):
        result = _stringify_value([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_dict_to_json(self):
        result = _stringify_value({"a": 1})
        assert json.loads(result) == {"a": 1}

    def test_scalar_to_string(self):
        assert _stringify_value(42) == "42"
        assert _stringify_value("hello") == "hello"


class TestGEXFExport:
    async def test_gexf_is_valid_xml(self):
        ex = GraphExporter()
        gexf = await ex._export_gexf(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        # Must be parseable XML
        root = ET.fromstring(gexf)
        assert root.tag.endswith("gexf")

    async def test_gexf_contains_all_nodes(self):
        ex = GraphExporter()
        gexf = await ex._export_gexf(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        # Should have <node> for each sample node
        ns = {"g": "http://www.gexf.net/1.2draft"}
        root = ET.fromstring(gexf)
        nodes = root.findall(".//g:node", ns)
        assert len(nodes) == 2
        ids = {n.get("id") for n in nodes}
        assert ids == {"node-1", "node-2"}

    async def test_gexf_contains_all_edges(self):
        ex = GraphExporter()
        gexf = await ex._export_gexf(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        ns = {"g": "http://www.gexf.net/1.2draft"}
        root = ET.fromstring(gexf)
        edges = root.findall(".//g:edge", ns)
        assert len(edges) == 2

    async def test_gexf_excludes_embeddings_by_default(self):
        ex = GraphExporter()
        gexf = await ex._export_gexf(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        # Embedding values should not appear in the output
        assert "0.1" not in gexf or "embedding" not in gexf

    async def test_gexf_includes_embeddings_when_requested(self):
        ex = GraphExporter()
        gexf = await ex._export_gexf(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=True)
        # When embeddings are included, attribute definitions should exist
        assert "embedding" in gexf

    async def test_gexf_escapes_special_characters(self):
        ex = GraphExporter()
        nodes = [
            {"id": "1", "labels": ["Paper"], "properties": {"title": "A & B <c>"}},
        ]
        gexf = await ex._export_gexf(nodes, [], include_embeddings=False)
        assert "&amp;" in gexf
        assert "&lt;" in gexf


class TestGraphMLExport:
    async def test_graphml_is_valid_xml(self):
        ex = GraphExporter()
        graphml = await ex._export_graphml(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        root = ET.fromstring(graphml)
        assert root.tag.endswith("graphml")

    async def test_graphml_contains_nodes_and_edges(self):
        ex = GraphExporter()
        graphml = await ex._export_graphml(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        root = ET.fromstring(graphml)
        nodes = root.findall(".//g:node", ns)
        edges = root.findall(".//g:edge", ns)
        assert len(nodes) == 2
        assert len(edges) == 2


class TestJsonLdExport:
    async def test_json_ld_structure(self):
        ex = GraphExporter()
        jld = await ex._export_json_ld(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        data = json.loads(jld)
        assert "@context" in data
        assert "@graph" in data
        assert len(data["@graph"]) == 4  # 2 nodes + 2 edges

    async def test_json_ld_excludes_embeddings(self):
        ex = GraphExporter()
        jld = await ex._export_json_ld(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        data = json.loads(jld)
        # No node should have an "embedding" key
        for item in data["@graph"]:
            assert "embedding" not in item or item.get("embedding") is None


class TestCsvExport:
    async def test_csv_is_a_zip(self):
        ex = GraphExporter()
        csv_data = await ex._export_csv(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        assert isinstance(csv_data, bytes)
        # Should be a valid zip
        bio = io.BytesIO(csv_data)
        with zipfile.ZipFile(bio, "r") as zf:
            names = zf.namelist()
        assert "nodes.csv" in names
        assert "edges.csv" in names
        assert "metadata.json" in names

    async def test_csv_metadata(self):
        ex = GraphExporter()
        csv_data = await ex._export_csv(SAMPLE_NODES, SAMPLE_EDGES, include_embeddings=False)
        bio = io.BytesIO(csv_data)
        with zipfile.ZipFile(bio, "r") as zf:
            metadata = json.loads(zf.read("metadata.json"))
        assert metadata["format"] == "csv"
        assert metadata["nodes_count"] == 2
        assert metadata["edges_count"] == 2
