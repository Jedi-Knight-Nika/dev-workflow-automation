import pytest

from app.domain.indexing import should_index_content, vector_literal


def test_vector_policy_supports_explicit_embedding_dimensions() -> None:
    assert vector_literal([0.25, 0.5], dimensions=2) == "[0.25,0.5]"


def test_vector_policy_rejects_invalid_dimension_configuration() -> None:
    with pytest.raises(ValueError, match="dimensions must be positive"):
        vector_literal([], dimensions=0)


def test_content_policy_rejects_binary_and_oversized_blobs() -> None:
    assert should_index_content("source code", max_bytes=20)
    assert not should_index_content("binary\x00data", max_bytes=20)
    assert not should_index_content("multibyte: ლ", max_bytes=12)


def test_content_policy_rejects_invalid_size_configuration() -> None:
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        should_index_content("", max_bytes=0)
