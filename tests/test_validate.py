from extract.schema import ExtractedMedication, ExtractedResult, Extraction
from extract.validate import validate


def _lab(*results: ExtractedResult, **header: str) -> Extraction:
    fields = {
        "patient_name": "Ama Mensah",
        "birth_date": "05/04/1990",
        "sex": "F",
        "collection_date": "21/03/2024",
        "clinician": "Kwame Boateng",
    } | header
    return Extraction(**fields, results=list(results))  # type: ignore[arg-type]


def _row(name: str, value: str, ref: str | None, flag: str | None = None) -> ExtractedResult:
    return ExtractedResult(test_name=name, value=value, unit="mg/dL", ref_range=ref, flag=flag)


def _kinds(ext: Extraction, doc_type: str = "lab") -> list[str]:
    return [i.kind for i in validate(ext, doc_type)]  # type: ignore[arg-type]


def test_a_consistent_report_raises_nothing() -> None:
    ext = _lab(_row("Creatinine", "1.62", "0.60 - 1.30", "H"), _row("Glucose", "88", "70 - 99"))
    assert _kinds(ext) == []


def test_a_missing_flag_is_caught_by_arithmetic() -> None:
    # The NER failure from ADR 0002: the flag was there, the model tagged it 'not a flag'.
    issues = validate(_lab(_row("Creatinine", "1.62", "0.60 - 1.30")), "lab")
    assert [i.kind for i in issues] == ["flag_mismatch"] and issues[0].field == "results[0].flag"


def test_french_formats_are_understood() -> None:
    assert _kinds(_lab(_row("Glycémie", "1,25", "0,70 - 0,99", "Haut"))) == []
    assert _kinds(_lab(_row("Cholestérol", "2,40", "< 2,00", "↑"))) == []


def test_a_number_split_across_fields_is_caught() -> None:
    # 'Kaliémie 3,5 - 5,1 4,0' read by NER v2 as flag '4', range ',', value '0'.
    assert "unknown_flag" in _kinds(_lab(_row("Kaliémie", "0", ",", "4")))


def test_missing_header_and_impossible_dates() -> None:
    assert _kinds(_lab(collection_date="")) == ["missing", "missing"]  # date and results
    assert "before_birth" in _kinds(
        _lab(_row("Na", "140", "136 - 145"), collection_date="01/01/1980")
    )


def test_referral_needs_a_reason_a_diagnosis_and_doses() -> None:
    ext = Extraction(
        patient_name="Ama Mensah",
        birth_date="1961-02-03",
        sex="F",
        clinician="Kwame Boateng",
        reason=None,
        diagnoses=[],
        medications=[ExtractedMedication(name="Metformin", dose=None, frequency="BD")],
    )
    assert sorted(_kinds(ext, "referral")) == ["missing", "missing", "missing"]


def test_cascade_without_an_llm_returns_ner_with_issues_for_review() -> None:
    from extract.cascade import Cascade

    class _Ner:
        def extract(self, text: str) -> Extraction:
            return _lab(_row("Creatinine", "1.62", "0.60 - 1.30"))  # flag missing

    result = Cascade(_Ner(), llm=None).run("doc1", "Biochemistry result 1.62 mg/dL")  # type: ignore[arg-type]
    assert result.source == "ner" and [i.kind for i in result.issues] == ["flag_mismatch"]
    assert result.notes == ["LLM fallback off: issues are left for review"]
