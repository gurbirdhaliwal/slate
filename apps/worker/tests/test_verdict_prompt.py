"""Edge cases most likely to break (§13 vibecoding workflow, step 4)."""

import pytest

from slate_worker.verdict_prompt import VerdictParseError, parse_verdict_response


def test_parses_clean_verdict():
    v = parse_verdict_response('{"score": 0.0, "failure_class": "retrieval_miss", "reasoning": "missed"}')
    assert v.score == 0.0
    assert v.failure_class == "retrieval_miss"


def test_strips_markdown_fences():
    v = parse_verdict_response('```json\n{"score": 1.0, "failure_class": null, "reasoning": "ok"}\n```')
    assert v.score == 1.0
    assert v.failure_class is None


def test_rejects_out_of_range_score():
    with pytest.raises(VerdictParseError):
        parse_verdict_response('{"score": 1.5, "failure_class": null, "reasoning": ""}')


def test_rejects_boolean_score():
    with pytest.raises(VerdictParseError):
        parse_verdict_response('{"score": true, "failure_class": null, "reasoning": ""}')


def test_rejects_invented_failure_class():
    with pytest.raises(VerdictParseError):
        parse_verdict_response('{"score": 0.2, "failure_class": "made_up_class", "reasoning": ""}')


def test_rejects_non_json():
    with pytest.raises(VerdictParseError):
        parse_verdict_response("The step looks fine to me!")


def test_score_rounded_to_3dp():
    v = parse_verdict_response('{"score": 0.6666666, "failure_class": null, "reasoning": ""}')
    assert v.score == 0.667
