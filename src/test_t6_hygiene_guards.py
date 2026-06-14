import conviction_sizing_calibrator as csc
import outcome_logger as ol


def test_outcome_logger_rejects_sample_inputs_paths():
    try:
        ol._reject_sample_inputs_path("snapshot input", "sample_inputs/prior.json")
    except ValueError as exc:
        assert "sample_inputs" in str(exc)
        assert "canonical" in str(exc)
    else:
        raise AssertionError("expected sample_inputs path to be rejected")


def test_outcome_logger_allows_canonical_cache_paths():
    assert ol._reject_sample_inputs_path("snapshot input", "src/positions.json") is None


def test_calibrator_rejects_sample_inputs_paths():
    try:
        csc._reject_sample_inputs_path("--positions", "src/sample_inputs/positions.json")
    except ValueError as exc:
        assert "sample_inputs" in str(exc)
        assert "canonical" in str(exc)
    else:
        raise AssertionError("expected sample_inputs path to be rejected")


def test_calibrator_allows_canonical_cache_paths():
    assert csc._reject_sample_inputs_path("--positions", "src/positions.json") is None
