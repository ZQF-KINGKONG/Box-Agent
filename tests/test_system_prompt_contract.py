from pathlib import Path


def test_system_prompt_keeps_todo_separate_from_factual_evidence():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "todo_write` 只记录执行进度" in prompt
    assert "不是事实证据、检索策略或结论来源" in prompt
    assert "任务计划显示完成只代表步骤执行完毕，不代表事实已核实" in prompt


def test_system_prompt_requires_authoritative_sources_for_current_facts():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "Factual & Search Reliability" in prompt
    assert "必须按今天日期检索或核对当前权威来源" in prompt
    assert "优先使用官方公告、模型卡、开发者文档、透明度页面或权威一手来源" in prompt
    assert "不要用“公开资料不多”替代答案" in prompt
