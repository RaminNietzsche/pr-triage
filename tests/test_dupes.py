from triage.dupes import classify, clusters, hunk_overlap, norm_title


def test_hunk_overlap_counts_overlapping_ranges():
    a = {"f.cc": [(1, 10), (20, 30)]}
    b = {"f.cc": [(5, 15)]}
    assert hunk_overlap(a, b) == 1


def test_norm_title_strips_release_prefix():
    assert norm_title("Squid: rgw fix foo") == norm_title("rgw fix foo")


def test_classify_identical_patch_ids(minimal_pr):
    a = minimal_pr(1, patch_ids=["p1", "p2"])
    b = minimal_pr(2, patch_ids=["p1", "p2"])
    kind, conf, ev = classify(a, b, 0.5)
    assert kind == "duplicate"
    assert conf == "high"


def test_classify_stacked_subset(minimal_pr):
    a = minimal_pr(1, patch_ids=["p1"])
    b = minimal_pr(2, patch_ids=["p1", "p2"])
    kind, conf, _ = classify(a, b, 0.5)
    assert kind == "stacked"
    assert conf == "low"


def test_classify_competing_fix_requires_hunks(minimal_pr):
    hunks = {"src/rgw/foo.cc": [(1, 50)]}
    a = minimal_pr(1, author="alice", title="fix ticket 99 part a", tickets=["99"], patch_ids=["pa"], hunks=hunks)
    b = minimal_pr(2, author="bob", title="fix ticket 99 part b", tickets=["99"], patch_ids=["pb"], hunks=hunks)
    kind, conf, _ = classify(a, b, 0.5)
    assert kind == "competing-fix"
    assert conf == "medium"


def test_classify_no_competing_without_hunk_overlap(minimal_pr):
    a = minimal_pr(
        1, author="alice", title="mon fix alpha", tickets=["99"], patch_ids=["pa"],
        eff_files=["src/mon/a.cc"], hunks={"src/mon/a.cc": [(1, 5)]},
    )
    b = minimal_pr(
        2, author="bob", title="rgw fix beta", tickets=["99"], patch_ids=["pb"],
        eff_files=["src/rgw/b.cc"], hunks={"src/rgw/b.cc": [(1, 5)]},
    )
    assert classify(a, b, 0.5) is None


def test_clusters_union_find():
    pairs = [
        {"a": 1, "b": 2, "kind": "duplicate"},
        {"a": 2, "b": 3, "kind": "competing-fix"},
        {"a": 4, "b": 5, "kind": "stacked"},
    ]
    cl = clusters(pairs)
    assert sorted(cl) == [[1, 2, 3]]
