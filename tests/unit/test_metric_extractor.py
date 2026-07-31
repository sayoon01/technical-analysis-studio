from backend.skills.analysis.metric_extractor import extract_metrics_from_text


def test_extract_baseline_change_with_title():
    text = """
구축효과
1. 시간당생산량
정의
공장가공철근제품의월평균시간당생산량
측정방법
시간당생산량= (일별설비별생산량(Ton/Hour) * 30일) * 100
효과
기존대비8% 증가
2. Claim 발생률
정의
월평균상차및출하클레임발생수
효과
기존대비60% 감소
"""
    metrics = extract_metrics_from_text(text)
    by_name = {m.name: m for m in metrics}
    assert "시간당생산량" in by_name
    assert by_name["시간당생산량"].change_value == 8.0
    assert by_name["시간당생산량"].direction.value == "INCREASE"
    assert "Claim 발생률" in by_name or any("Claim" in m.name for m in metrics)
    claim = next(m for m in metrics if "Claim" in m.name or "클레임" in m.name)
    assert claim.change_value == 60.0
    assert claim.direction.value == "DECREASE"
    # formula fragments must not become absolute metrics
    assert not any(m.result_value == 30 for m in metrics)
    assert not any(m.name in {"효과", "기존대비"} for m in metrics)


def test_extract_inline_signed_pct():
    text = "납기준수율 +24% 향상\n재공재고 -33% 감소"
    metrics = extract_metrics_from_text(text)
    vals = {(m.name, m.change_value, m.direction.value if m.direction else None) for m in metrics}
    assert ("납기준수율", 24.0, "INCREASE") in vals
    assert ("재공재고", 33.0, "DECREASE") in vals


def test_extract_absolute_headcount_and_scale():
    text = """
회사소개
사원수
371명
311명
사업규모
1,931억원
1,762억원
1,633억원
2018
2019
2020
*2021.04 기준
"""
    metrics = extract_metrics_from_text(text)
    abs_vals = {(m.name, m.result_value, m.change_unit) for m in metrics if m.result_value is not None}
    assert ("사원수", 371.0, "명") in abs_vals
    assert ("사원수", 311.0, "명") in abs_vals
    assert ("사업규모", 1931.0, "억원") in abs_vals
    assert ("사업규모", 1762.0, "억원") in abs_vals
    assert ("사업규모", 1633.0, "억원") in abs_vals
    # bare years are not metrics
    assert not any(m.result_value in {2018, 2019, 2020} for m in metrics)
