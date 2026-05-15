from pathlib import Path


BUNDLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "box_agent"
    / "skills"
    / "document-skills"
    / "pptx"
    / "scripts"
    / "dom-to-pptx.bundle.js"
)


def test_dom_to_pptx_bundle_documents_vendor_inflate_mode_resume() -> None:
    """Keep pako's upstream TYPEDO state documented as vendor code."""
    source = BUNDLE_PATH.read_text(encoding="utf-8")

    assert "Vendor provenance / hook-audit rationale" in source
    assert "Compatibility: this Browser bundle embeds pako's upstream inflate state machine" in source
    assert "Fail-safe:" in source
    assert "Tested: tests/test_pptx_dom_to_pptx_bundle.py" in source
    assert "const        TYPEDO = 16192" in source
    assert "if (state.mode === TYPE) {" in source
    assert "state.mode = TYPEDO;" in source


def test_dom_to_pptx_bundle_exports_browser_api() -> None:
    source = BUNDLE_PATH.read_text(encoding="utf-8")

    assert "factory(global.domToPptx = {})" in source
    assert "exports.exportToPptx = exportToPptx" in source
