"""LangGraph graph builder — loads topology from YAML, applies budget gates."""
import ast
import logging
import re
import yaml
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END

from reasoning.graph.state import ReasoningState

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Loads graph topology from YAML and constructs a LangGraph StateGraph."""

    def __init__(self, topology_path: str | None = None):
        if topology_path is None:
            topology_path = str(Path(__file__).parent / "definitions" / "default.yaml")
        self.topology = self._load_topology(topology_path)
        self._node_modules: dict[str, Any] = {}

    def _load_topology(self, path: str) -> dict:
        with open(path) as f:
            data = yaml.safe_load(f)
        logger.info(f"Loaded graph topology: {data['graph']['name']} v{data['graph']['version']}")
        return data

    def _resolve_node_func(self, node_id: str, module_path: str, func_name: str):
        """Lazily import and cache node functions."""
        cache_key = f"{module_path}:{func_name}"
        if cache_key in self._node_modules:
            return self._node_modules[cache_key]

        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        self._node_modules[cache_key] = func
        return func

    def _wrap_with_budget_gate(self, func, task_type: str, model_id: str):
        """Wrap a node function with budget gate check."""
        async def wrapped(state: ReasoningState) -> ReasoningState:
            from budget.oracle import get_budget_oracle
            oracle = get_budget_oracle()
            estimated = 500  # conservative estimate
            allowed, _ = await oracle.gate(model_id, estimated)
            if not allowed:
                state.status = "FAILED"
                state.error = f"Budget exhausted for {model_id}"
                return state
            result = await func(state)
            oracle.record_usage(model_id, estimated)
            return result
        return wrapped

    def build(self) -> StateGraph:
        """Construct and return a compiled LangGraph StateGraph."""
        graph = StateGraph(ReasoningState)

        # Add all nodes
        for node_def in self.topology["nodes"]:
            func = self._resolve_node_func(
                node_def["id"], node_def["module"], node_def["function"]
            )
            graph.add_node(node_def["id"], func)
            logger.debug(f"Added node: {node_def['id']}")

        # Add edges. Conditional edges are grouped per source because LangGraph
        # expects one router per node when multiple branches leave the same node.
        edges_by_source: dict[str, list[dict]] = {}
        for edge in self.topology.get("edges", []):
            edges_by_source.setdefault(edge["from"], []).append(edge)

        for from_id, edges in edges_by_source.items():
            conditional_edges = [edge for edge in edges if edge.get("condition")]
            unconditional_edges = [edge for edge in edges if not edge.get("condition")]

            for edge in unconditional_edges:
                to_id = edge["to"]
                graph.add_edge(from_id, END if to_id == "__end__" else to_id)

            if conditional_edges:
                route_map = {
                    edge["to"]: (END if edge["to"] == "__end__" else edge["to"])
                    for edge in conditional_edges
                }
                graph.add_conditional_edges(
                    from_id,
                    self._make_branch_router(conditional_edges),
                    route_map,
                )

        # Set entry point
        entry_id = self.topology["nodes"][0]["id"]
        graph.set_entry_point(entry_id)

        compiled = graph.compile()
        logger.info(f"Compiled LangGraph with {len(self.topology['nodes'])} nodes")
        return compiled

    def _make_branch_router(self, conditional_edges: list[dict]):
        """Create a router returning the target id for the first true condition."""
        def router(state: ReasoningState) -> str:
            for edge in conditional_edges:
                if self._evaluate_condition(edge["condition"], state):
                    return edge["to"]
            logger.warning(
                "No graph condition matched from candidates: %s",
                [edge.get("condition") for edge in conditional_edges],
            )
            return conditional_edges[-1]["to"]

        return router

    def _evaluate_condition(self, condition_str: str, state: ReasoningState) -> bool:
        """Safely evaluate simple topology conditions against ReasoningState."""
        normalized = re.sub(r"\btrue\b", "True", condition_str, flags=re.IGNORECASE)
        normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
        tree = ast.parse(normalized, mode="eval")
        return bool(self._eval_ast(tree.body, state))

    def _eval_ast(self, node: ast.AST, state: ReasoningState) -> Any:
        if isinstance(node, ast.BoolOp):
            values = [self._eval_ast(value, state) for value in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not self._eval_ast(node.operand, state)
        if isinstance(node, ast.Compare):
            left = self._eval_ast(node.left, state)
            for operator, comparator in zip(node.ops, node.comparators):
                right = self._eval_ast(comparator, state)
                if isinstance(operator, ast.Eq) and not left == right:
                    return False
                if isinstance(operator, ast.NotEq) and not left != right:
                    return False
                if isinstance(operator, ast.Lt) and not left < right:
                    return False
                if isinstance(operator, ast.LtE) and not left <= right:
                    return False
                if isinstance(operator, ast.Gt) and not left > right:
                    return False
                if isinstance(operator, ast.GtE) and not left >= right:
                    return False
                left = right
            return True
        if isinstance(node, ast.Name):
            return getattr(state, node.id)
        if isinstance(node, ast.Constant):
            return node.value
        raise ValueError(f"Unsupported graph condition expression: {ast.dump(node)}")
