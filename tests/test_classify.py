"""Tests for the object-type classifier."""

from __future__ import annotations

from repository_object_mapper.classify import (
    classify_record,
    disagreement_rate,
    load_type_mapping,
)
from repository_object_mapper.schema import (
    ConfidenceLevel,
    Identifier,
    NormalizedRecord,
    ObjectType,
)


def test_journal_article_high_confidence(simple_article: NormalizedRecord) -> None:
    mapping = load_type_mapping("config/type_mapping.yaml")
    classify_record(simple_article, mapping)
    assert simple_article.object_type == ObjectType.ARTICLE
    assert simple_article.object_type_confidence == ConfidenceLevel.HIGH


def test_overloaded_text_low_confidence(bare_article: NormalizedRecord) -> None:
    mapping = load_type_mapping("config/type_mapping.yaml")
    classify_record(bare_article, mapping)
    # "Text" maps to article at LOW confidence by the default mapping
    assert bare_article.object_type == ObjectType.ARTICLE
    assert bare_article.object_type_confidence in {ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM}


def test_dataset_classification_from_filename(provenance) -> None:
    rec = NormalizedRecord(
        repository_name="zenodo",
        repository_a_priori_tier=3,
        local_identifier="rec-csv",
        raw_path="data/mock/rec-csv.xml",
        provenance=provenance,
        declared_type_raw=None,
        identifiers=[Identifier(scheme="url", value="https://example.com/data.csv")],
    )
    mapping = load_type_mapping("config/type_mapping.yaml")
    classify_record(rec, mapping)
    assert rec.object_type == ObjectType.DATASET


def test_thesis_keyword_detection(provenance) -> None:
    rec = NormalizedRecord(
        repository_name="unknown_repo",
        repository_a_priori_tier=1,
        local_identifier="rec-thesis",
        raw_path="x",
        provenance=provenance,
        title="PhD Thesis on scholarly communication",
        declared_type_raw=None,
    )
    mapping = load_type_mapping("config/type_mapping.yaml")
    classify_record(rec, mapping)
    assert rec.object_type == ObjectType.THESIS
    assert rec.object_type_confidence == ConfidenceLevel.HIGH


def test_type_disagreement_is_recorded(provenance) -> None:
    # Declared as article (low confidence via "Text") but title says "Dataset"
    rec = NormalizedRecord(
        repository_name="tier1_dspace_example",
        repository_a_priori_tier=1,
        local_identifier="rec-disagree",
        raw_path="x",
        provenance=provenance,
        title="Environmental dataset for 2024",
        declared_type_raw="Text",
    )
    mapping = load_type_mapping("config/type_mapping.yaml")
    classify_record(rec, mapping)
    # Rule-based = dataset, declared = article with low confidence → prefer rule
    assert rec.object_type == ObjectType.DATASET
    assert rec.type_disagreement is True


def test_disagreement_rate_aggregation(provenance) -> None:
    rec = NormalizedRecord(
        repository_name="tier1",
        repository_a_priori_tier=1,
        local_identifier="rec-1",
        raw_path="x",
        provenance=provenance,
    )
    rec.type_disagreement = True
    rec2 = NormalizedRecord(
        repository_name="tier1",
        repository_a_priori_tier=1,
        local_identifier="rec-2",
        raw_path="x",
        provenance=provenance,
    )
    rates = disagreement_rate([rec, rec2])
    assert rates["tier1"] == 0.5
