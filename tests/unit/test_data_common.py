from scripts.data.common import (
    Classifier,
    PhraseIndex,
    SkillMatcher,
    has_pii,
    load_taxonomy,
    mask_pii,
    near_dup_key,
    parse_money,
    parse_rate_range,
    tokenize,
)


def test_mask_pii_masks_contacts_but_not_money_years_or_ranges() -> None:
    text = (
        "mail a.b@x.com or call +1 (555) 123-4567. Budget $2,500 in 2024, rate 10-25. "
        "whatsapp: @john99, see www.site.com/x"
    )
    out = mask_pii(text)
    assert "[EMAIL]" in out and "[PHONE]" in out and "[URL]" in out and "[HANDLE]" in out
    assert "$2,500" in out and "2024" in out and "10-25" in out
    assert not has_pii(out)


def test_has_pii_on_clean_text() -> None:
    assert not has_pii("Need a Django developer for 3 months, 20 hrs/week.")


def test_parse_money_and_rates() -> None:
    assert parse_money("$2,500 ") == 2500.0
    assert parse_money("0") is None
    assert parse_money(float("nan")) is None
    assert parse_rate_range("$10.00-$35.00") == (10.0, 35.0)
    assert parse_rate_range("$40.00 ") == (40.0, 40.0)
    assert parse_rate_range(None) == (None, None)


def test_tokenize_keeps_tech_names() -> None:
    assert tokenize("Node.js, C++ & C#; front-end/back-end. python.") == [
        "node.js", "c++", "c#", "front-end", "back-end", "python",
    ]


def test_phrase_index_prefers_longest_match() -> None:
    idx = PhraseIndex({"machine learning": "ml", "learning": "edu"})
    assert idx.matches("I do machine learning and learning design") == ["ml", "edu"]


def test_classifier_uses_taxonomy() -> None:
    clf = Classifier(load_taxonomy())
    assert clf.classify("Build a RAG chatbot with LangChain") == "ai_ml"
    assert clf.classify("Power BI dashboard for sales") == "data_analytics"
    assert clf.classify("Next.js and Django web app") == "web_dev"
    assert clf.classify("Logo design for a bakery") == "design"
    assert clf.classify("hello there") == "other"


def test_skill_matcher_word_boundaries_and_short_names() -> None:
    m = SkillMatcher(["Python", "Node.js", "UI/UX", "Machine Learning", "R", "Java"], ["R", "AI"])
    found = m.find("Need Python and node.js, UI/UX, machine learning in R. JavaScript too.")
    assert found == ["Python", "Node.js", "UI/UX", "Machine Learning", "R"]
    assert "R" not in m.find("We are a remote team")


def test_near_dup_key_ignores_case_and_punctuation() -> None:
    a = near_dup_key("Logo Design!", "Need a logo, fast.", 300)
    b = near_dup_key("logo design", "need a logo fast", 300)
    assert a == b


def test_clean_text_decodes_entities() -> None:
    from scripts.data.common import clean_text

    assert clean_text("API Integration &amp; AI   Model &quot;Builder&quot;") == 'API Integration & AI Model "Builder"'
