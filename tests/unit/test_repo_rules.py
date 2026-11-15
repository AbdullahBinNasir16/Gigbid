from scripts.check_repo_rules import (
    gigsim_import_lines,
    gigsim_text_import_lines,
    inline_prompt_lines,
    inline_prompt_text_lines,
    secret_pattern_lines,
    unbacked_readme_numbers,
)


def test_secret_placeholders_are_allowed_but_values_are_reported():
    placeholder_line = "APP_" + "SE" + "CRET_KEY=replace_me\n"
    assert secret_pattern_lines(placeholder_line) == []
    secret_line = "APP_" + "SE" + "CRET_KEY=" + "not-a-placeholder"
    assert secret_pattern_lines(secret_line) == [1]
    json_line = '"access_' + 'token": "not-a-placeholder"'
    assert secret_pattern_lines(json_line) == [1]


def test_gigsim_imports_are_detected():
    source = "import gigsim.client\nfrom gigsim.jobs import Job\n"
    assert gigsim_import_lines(source) == [1, 2]
    assert gigsim_text_import_lines('import { client } from "gigsim/client";') == [1]


def test_inline_prompt_assignment_is_detected():
    source = (
        'system_message = "' + "You" + " are a proposal writer. Follow " + "these instructions." + '"\n'
    )
    assert inline_prompt_lines(source) == [1]
    frontend_source = (
        'const systemMessage = "' + "You" + " are a proposal writer. Follow " + "these instructions." + '";'
    )
    assert inline_prompt_text_lines(frontend_source) == [1]


def test_reported_metric_must_match_an_evaluation_result():
    readme = "Accuracy: 92%\n"
    assert unbacked_readme_numbers(readme, {}) == [(1, "92%")]
    results = {"evals/results/decision.json": '{"accuracy": 0.92}'}
    assert unbacked_readme_numbers(readme, results) == []
