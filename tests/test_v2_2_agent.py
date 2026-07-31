from __future__ import annotations

import json
import unittest
from pathlib import Path

from sc2_agents.v2_2.contracts import validate_sub_reply
from sc2_agents.v2_2.main_agent import MAX_MAIN_ROUNDS
from sc2_agents.v2_2.model_view import EvidenceReferenceMap, OPAQUE_ID_KEYS
from sc2_agents.v2_2.sub_agent import MAX_TOOL_RESULT_CHARS
from sc2_agents.v2_2.tool_registry import ToolRegistry


def contains_opaque_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in OPAQUE_ID_KEYS or contains_opaque_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_opaque_key(item) for item in value)
    return False


class V22LocalBehaviorTests(unittest.TestCase):
    def test_main_round_limit_is_twenty(self):
        self.assertEqual(20, MAX_MAIN_ROUNDS)

    def test_prompt_and_context_files_are_ascii_english(self):
        root = Path(__file__).resolve().parents[1] / "sc2_agents" / "v2_2"
        for folder in (root / "prompts", root / "context"):
            for path in folder.glob("*.md"):
                path.read_text(encoding="utf-8").encode("ascii")

    def test_sub_reply_preserves_candidate_entities(self):
        reply = validate_sub_reply({
            "answer": "One candidate is supported.",
            "candidate_entities": [{"name": "A", "fields": {"minerals": 0}}],
        })
        self.assertEqual("A", reply["candidate_entities"][0]["name"])

    def test_model_view_hides_hashes_and_adds_short_relation_reference(self):
        raw = ToolRegistry().execute(
            "query_relations",
            {"entity_name": "SMART", "relation": ["ability_requires_upgrade"], "direction": "forward"},
        )
        references = EvidenceReferenceMap()
        compacted, metrics = references.compact(raw)
        self.assertFalse(contains_opaque_key(compacted))
        self.assertEqual("R1", compacted["results"][0]["evidence_ref"])
        self.assertGreater(metrics["removed_field_count"], 0)

    def test_short_reference_expands_to_raw_relation_evidence(self):
        registry = ToolRegistry()
        raw = registry.execute(
            "query_relations",
            {"entity_name": "SMART", "relation": ["ability_requires_upgrade"], "direction": "forward"},
        )
        references = EvidenceReferenceMap()
        compacted, _ = references.compact(raw)
        expanded = registry.execute(
            "query_relation_evidence",
            {"evidence_ref": compacted["results"][0]["evidence_ref"]},
            evidence_references=references,
        )
        self.assertEqual(
            "4bd260ce845ccebb5b40381fd996a01347fb0c6c9feb81f8f8e8e02fc05c145e",
            expanded["results"][0]["relation_id"],
        )

    def test_hundred_relation_model_view_fits_before_truncation_limit(self):
        raw = ToolRegistry().execute("query_relations", {"limit": 100})
        compacted, _ = EvidenceReferenceMap().compact(raw)
        content = json.dumps(compacted, ensure_ascii=False, default=str)
        self.assertLess(len(content), MAX_TOOL_RESULT_CHARS)

    def test_evidence_tool_schema_exposes_only_short_reference(self):
        tool = ToolRegistry().openai_tools(["query_relation_evidence"])[0]
        parameters = tool["function"]["parameters"]
        self.assertEqual({"evidence_ref"}, set(parameters["properties"]))
        self.assertEqual(["evidence_ref"], parameters["required"])

    def test_evidence_expander_can_be_added_after_four_primary_tools(self):
        registry = ToolRegistry()
        names = registry.names()[:4] + ["query_relation_evidence"]
        tools = registry.openai_tools(names, maximum=5)
        self.assertEqual("query_relation_evidence", tools[-1]["function"]["name"])


if __name__ == "__main__":
    unittest.main()
