"""The real policy-change demo yields usable single/repeated reviews without approval."""

from examples.baseline_review_demo import main
from thadam import (
    approve_review,
    compare_repeated,
    compare_reports,
    load_baseline_review,
    load_evaluation,
    write_approved_baseline,
)


def test_demo_generated_reviews_are_complete_and_require_explicit_approval(tmp_path, capsys):
    assert main(["--output", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert output.count("python -m thadam approve-baseline") == 2
    for mode, compare in (("single", compare_reports), ("repeated", compare_repeated)):
        baseline_path = tmp_path / f"{mode}-baseline.json"
        candidate = load_evaluation(tmp_path / f"{mode}-candidate.json")
        review = load_baseline_review(tmp_path / f"{mode}-review.json")
        assert not review.blockers
        assert review.digest in output
        assert compare(load_evaluation(baseline_path), candidate).exit_code == 2
        write_approved_baseline(
            approve_review(
                review,
                review_digest=review.digest,
                reviewer="Test reviewer",
                reason="Reviewed policy",
            ),
            baseline_path,
        )
        assert compare(load_evaluation(baseline_path), candidate).exit_code == 0
    original = (tmp_path / "repeated-baseline.json").read_bytes()
    assert main(["--output", str(tmp_path)]) == 2
    assert (tmp_path / "repeated-baseline.json").read_bytes() == original
