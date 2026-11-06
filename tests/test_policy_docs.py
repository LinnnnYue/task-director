"""Documentation-policy tests: the skill's markdown must state and satisfy the rule.

`SKILL.md`, `role-templates.md` and `role-models.md` *are* the deliverable of this
repository, so their promises need to be checkable too — otherwise a later edit
can quietly delete the cross-family constraint while the code keeps passing.

Run: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cross_model_router import TIERS, allowed_tiers, cross_ok, norm_model, norm_provider, Route, tier_plans  # noqa: E402


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def frontmatter_blocks(text: str, key: str) -> list[str]:
    """Every `--- ... ---` block whose body mentions `key`."""
    blocks = re.findall(r"---\n(.*?)\n---\n", text, re.S)
    return [block for block in blocks if key in block]


def field(block: str, name: str) -> str | None:
    match = re.search(rf"{name}:\s*\"?([^\"\n]+)\"?", block)
    return match.group(1).strip() if match else None


class SkillMdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read("SKILL.md")

    def test_states_the_cross_vendor_constraint(self):
        self.assertIn("供应商与模型族约束（异族互审）", self.text)
        self.assertIn("交叉调度是硬约束，不是建议", self.text)
        self.assertIn("任何同供应商或同族配对一律拒绝或改选", self.text)

    def test_requires_both_provider_and_family_to_differ(self):
        self.assertIn("必须与评审者**同时**不同", self.text)
        self.assertIn("同族不评分", self.text)

    def test_forbids_pro_tier_for_every_task(self):
        self.assertIn("`pro` 档任何任务禁用", self.text)

    def test_degrade_never_relaxes_the_family_rule(self):
        self.assertIn("降级只降成本，不降族", self.text)
        self.assertIn("不许\"先用同族评一下\"", self.text)

    def test_names_the_known_find_first_candidate_defect(self):
        self.assertIn("不盲取目录首个", self.text)
        self.assertIn("find()", self.text)

    def test_each_dispatch_phase_carries_the_model_rule(self):
        phase2 = self.text.split("### Phase 2")[1].split("### Phase 3")[0]
        phase3 = self.text.split("### Phase 3")[1].split("### Phase 4")[0]
        phase4 = self.text.split("### Phase 4")[1].split("### Phase 5")[0]
        self.assertIn("provider=", phase2)
        self.assertIn("异族互审", phase2)
        self.assertIn("显式指定", phase3)
        self.assertIn("异族评审模型", phase4)

    def test_role_models_file_is_declared_and_loaded(self):
        self.assertIn("role_models:", self.text)
        self.assertIn("role-models.md", self.text)

    def test_documented_degradation_matches_the_code(self):
        text = self.text.split("### 降级顺序（不可越界）")[1].split("###", 1)[0]
        for task in ("simple", "standard", "complex"):
            bands = tier_plans(task)
            for tier in allowed_tiers(task):
                self.assertRegex(text, rf"`{tier}`", f"{task} 的文档未提到成本档 {tier}")
            self.assertFalse(any("pro" in band for band in bands), f"{task} 的计划包含 pro 档")

    def test_calibration_log_stays_linked_to_cross_family_evidence(self):
        self.assertIn("cross_family: false", self.text)


class RoleTemplatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read("role-templates.md")
        self.blocks = frontmatter_blocks(self.text, "task_type:")

    def test_every_template_has_a_frontmatter_block(self):
        self.assertGreaterEqual(len(self.blocks), 2)

    def test_every_template_declares_cross_family_true(self):
        for block in self.blocks:
            self.assertIn("cross_family: true", block, f"模板缺少 cross_family: true：{block[:40]}")

    def test_every_template_names_an_cross_family_model_pair(self):
        for block in self.blocks:
            worker = field(block, "worker_model")
            reviewer = field(block, "reviewer_model")
            self.assertIsNotNone(worker, block[:60])
            self.assertIsNotNone(reviewer, block[:60])
            w = Route(*worker.split("/", 1))
            r = Route(*reviewer.split("/", 1))
            self.assertTrue(
                cross_ok(w, r),
                f"模板声明的执行者与评审者同族或同供应商：{worker} vs {reviewer}",
            )

    def test_every_template_declares_a_non_pro_cost_tier(self):
        for block in self.blocks:
            tier = field(block, "cost_tier")
            self.assertIn(tier, TIERS, block[:60])
            self.assertNotEqual(tier, "pro", "模板不得以 pro 档入库")

    def test_every_agent_prompt_pins_its_model_line(self):
        agent_sections = re.split(r"\n## Agent: ", self.text)[1:]
        for section in agent_sections:
            self.assertRegex(section.split("\n## ")[0], r"模型：provider=", "角色提示词缺少模型行")

    def test_reviewer_prompts_carry_the_anti_collusion_instructions(self):
        reviewers = [
            section.split("\n## ")[0]
            for section in re.split(r"\n## Agent: ", self.text)[1:]
            if "严苛评审" in section.split("\n## ")[0]
        ]
        self.assertGreaterEqual(len(reviewers), 2, "模板里应有评审角色")
        for body in reviewers:
            self.assertIn("异供应商、异族", body, "评审角色未说明自己与执行者异族")
            self.assertIn("禁止", body, "评审角色未禁止无依据打分")


class RoleModelsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = read("role-models.md")

    def test_declares_every_tier_and_marks_pro_disabled(self):
        for tier in TIERS:
            self.assertIn(f"`{tier}`", self.text)
        self.assertIn("**任何任务禁用**", self.text)

    def test_states_the_probe_and_blacklist_policy(self):
        self.assertIn("探针", self.text)
        self.assertIn("黑名单", self.text)
        self.assertIn("TTL", self.text)

    def test_states_rotation_is_persisted(self):
        self.assertIn("跨任务持久化", self.text)

    def test_marks_cross_family_as_non_negotiable_under_degradation(self):
        self.assertIn("永不放宽族", self.text)

    def test_pool_example_matches_the_documented_schema(self):
        import json

        raw = json.loads(read("scripts/model-pool.example.json"))
        self.assertIn("candidates", raw)
        for entry in raw["candidates"]:
            self.assertIn("provider", entry)
            self.assertIn("model", entry)
            self.assertIn(entry["tier"], TIERS)
            self.assertTrue(norm_provider(entry["provider"]))
            self.assertTrue(norm_model(entry["model"]))

    def test_example_pool_can_actually_pair_cross_families(self):
        from cross_model_router import load_pool

        pool = load_pool(str(ROOT / "scripts" / "model-pool.example.json"))
        legal = [r for r in pool.routes if r.tier not in ("pro",)]
        pairs = [(a, b) for a in legal for b in legal if cross_ok(a, b)]
        self.assertTrue(pairs, "示例池无法组成任何异族配对，文档与示例不一致")


class ReadmeTest(unittest.TestCase):
    def test_chinese_readme_documents_the_rule_and_the_checks(self):
        text = read("README.md")
        self.assertIn("异族互审", text)
        self.assertIn("role-models.md", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("cross_model_router.py", text)

    def test_english_readme_documents_the_rule_and_the_checks(self):
        text = read("README.en.md")
        self.assertIn("Cross-family review", text)
        self.assertIn("role-models.md", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("cross_model_router.py", text)

    def test_readmes_list_the_new_files_in_the_structure(self):
        for name in ("README.md", "README.en.md"):
            self.assertIn("role-models.md", read(name))
            self.assertIn("tests/", read(name))


class SpecialistRegistryTest(unittest.TestCase):
    def test_separates_weights_from_routing(self):
        text = read("specialist-registry.md")
        self.assertIn("本文件不决定用哪个模型", text)
        self.assertIn("异族互审不能被任何模块覆盖", text)

    def test_warns_against_hardcoding_a_provider_in_a_module(self):
        self.assertIn("不要在模块里写死某个 provider", read("specialist-registry.md"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
