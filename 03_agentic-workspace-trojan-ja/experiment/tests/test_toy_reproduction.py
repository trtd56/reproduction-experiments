import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_toy_reproduction.py"
SPEC = importlib.util.spec_from_file_location("run_toy_reproduction", SCRIPT_PATH)
toy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = toy
SPEC.loader.exec_module(toy)


def test_naive_reproduces_persistent_control_failures():
    results, summary = toy.run_all()
    naive = summary["by_mode"]["naive"]
    assert naive["attack_successes"] == 4
    assert naive["attack_total"] == 4
    assert naive["attack_success_rate"] == 1.0
    assert any(
        result.mode == "naive"
        and result.scenario == "sales_report_falsification"
        and "目標達成率: 120%" in result.output
        for result in results
    )


def test_guard_blocks_attack_triggers_before_memory_persistence():
    results, summary = toy.run_all()
    guarded = summary["by_mode"]["guarded"]
    assert guarded["attack_successes"] == 0
    assert guarded["attack_total"] == 4
    assert guarded["blocked_line_count"] >= 4
    assert any(
        result.mode == "guarded"
        and result.scenario == "sales_report_falsification"
        and "目標達成率: 84%" in result.output
        for result in results
    )


def test_borderline_clean_case_shows_false_positive_tradeoff():
    _, summary = toy.run_all()
    guarded = summary["by_mode"]["guarded"]
    assert guarded["false_positives"] == 1
    assert guarded["clean_total"] == 2
