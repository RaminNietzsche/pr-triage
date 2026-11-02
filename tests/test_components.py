from triage.components import by_path, path_counts, primary_component


def test_by_path_rgw():
    assert by_path(["src/rgw/rgw_main.cc", "src/rgw/rgw_op.cc"]) == "rgw"


def test_by_path_prefers_specific_over_qa_tests():
    paths = ["src/rgw/foo.cc", "qa/workunits/rgw/test.sh"]
    assert by_path(paths) == "rgw"


def test_path_counts_multiple():
    c = path_counts(["src/rgw/a.cc", "src/mon/b.cc"])
    assert c["rgw"] == 1
    assert c["mon"] == 1


def test_primary_component_label_priority_with_paths():
    rec = {
        "labels": ["rbd", "crimson"],
        "git": {"files": [{"path": "src/crimson/osd/foo.cc"}, {"path": "src/crimson/bar.cc"}]},
    }
    comp, src = primary_component(rec)
    assert comp == "crimson"
    assert src == "label"


def test_primary_component_single_label():
    rec = {"labels": ["cephfs"], "git": {"files": [{"path": "src/mds/mds.cc"}]}}
    assert primary_component(rec) == ("cephfs", "label")


def test_primary_component_path_fallback():
    rec = {"labels": [], "git": {"files": [{"path": "src/mon/mon.cc"}]}}
    assert primary_component(rec) == ("mon", "path")
