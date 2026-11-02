from triage.collect import clean_body, is_component


def test_clean_body_strips_contribution_guidelines():
    body = "Fixes bug\n\n## Contribution guidelines\nDo not read this"
    assert "Contribution" not in clean_body(body)
    assert "Fixes bug" in clean_body(body)


def test_clean_body_strips_html_comments():
    assert clean_body("hello <!-- secret --> world") == "hello  world"


def test_is_component_by_label():
    pr = {"labels": [{"name": "rgw"}]}
    assert is_component(pr, {"files": []}, "rgw", "src/rgw/")


def test_is_component_by_path_prefix():
    pr = {"labels": []}
    info = {"files": [{"path": "src/rgw/rgw_main.cc", "old_path": "src/rgw/rgw_main.cc"}]}
    assert is_component(pr, info, "rgw", "src/rgw/")
    assert not is_component(pr, info, "mon", "src/mon/")
