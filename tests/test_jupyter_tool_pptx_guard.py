"""Regression tests for PPTX creation guardrails in execute_code."""

from __future__ import annotations

from box_agent.tools.jupyter_tool import JupyterSandboxTool


def test_execute_code_blocks_bare_python_pptx_new_deck_constructor():
    code = """\
from pptx import Presentation

prs = Presentation()
prs.save("deck.pptx")
"""

    assert JupyterSandboxTool._looks_like_python_pptx_new_deck(code)


def test_execute_code_allows_existing_pptx_inspection():
    code = """\
from pptx import Presentation

prs = Presentation("existing.pptx")
print(len(prs.slides))
"""

    assert not JupyterSandboxTool._looks_like_python_pptx_new_deck(code)


def test_execute_code_allows_non_pptx_data_work():
    code = """\
import pandas as pd

df = pd.read_csv("data.csv")
print(df.describe())
"""

    assert not JupyterSandboxTool._looks_like_python_pptx_new_deck(code)
