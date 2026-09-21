from journal_mcp.classifier import classify_journal_entry


def test_reflective_monologue_is_journal() -> None:
    transcript = (
        "Lately I have been thinking about starting the company. I feel excited, but I am "
        "worried that I keep turning every uncertainty into a decision I need to make today. "
        "I want to understand whether that pressure is useful or just anxiety. " * 3
    )
    result = classify_journal_entry(transcript, duration_seconds=180)
    assert result.status == "journal"
    assert result.confidence >= 0.62


def test_short_capture_is_not_journal() -> None:
    result = classify_journal_entry("Grocery list: eggs and milk", duration_seconds=7)
    assert result.status == "not_journal"


def test_ambiguous_content_stays_uncertain() -> None:
    result = classify_journal_entry(
        "The company direction has three possible approaches and the first one is video.",
        duration_seconds=35,
    )
    assert result.status == "uncertain"

