from nroutersdk import ReasoningExhaustionReport, diagnose_reasoning_exhaustion


def test_diagnose_reasoning_exhaustion():
    report = diagnose_reasoning_exhaustion(
        finish_reason="length",
        output_tokens=1000,
        reasoning_tokens=1000,
        content="",
    )
    assert report.exhausted is True
    assert report.reasoning_tokens == 1000
    assert "Reasoning consumed the entire token budget" in (report.message or "")

    normal = diagnose_reasoning_exhaustion(
        finish_reason="stop",
        output_tokens=50,
        reasoning_tokens=10,
        content="ok",
    )
    assert normal.exhausted is False

    with_content = diagnose_reasoning_exhaustion(
        finish_reason="length",
        output_tokens=1000,
        reasoning_tokens=200,
        content="Partial text",
    )
    assert with_content.exhausted is False
