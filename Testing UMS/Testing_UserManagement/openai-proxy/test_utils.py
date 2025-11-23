from utils import PathMatchingTree


def test_get_matching_exact_match():
    config = {
        "foo/bar": "value1",
        "baz/qux": "value2"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("foo/bar") == "value1"


def test_get_matching_partial_match():
    config = {
        "foo/bar": "value1",
        "baz/qux": "value2"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("foo") is None


def test_get_matching_wildcard_match():
    config = {
        "/foo/*": "value1",
        "/baz/qux": "value2"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("foo/bar") == "value1"


def test_get_matching_multiple_wildcard_match():
    config = {
        "/foo/*": "value1",
        "/foo/*/bar": "value2"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("/foo") is None
    assert pmt.get_matching("/foo/baz") == "value1"
    assert pmt.get_matching("/foo/baz/bar2") == "value1"
    assert pmt.get_matching("/foo/baz/bar") == "value2"


def test_get_matching_no_match():
    config = {
        "/foo/bar": "value1",
        "/baz/qux": "value2"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("/foo") is None
    assert pmt.get_matching("/baz") is None


def test_get_matching_empty_string_match():
    config = {
        "/": "value1"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("/") == "value1"
    assert pmt.get_matching("/test") == "value1"

def test_get_matching_root_match():
    config = {
        "/": "value1"
    }
    pmt = PathMatchingTree(config)
    assert pmt.get_matching("/") == "value1"
