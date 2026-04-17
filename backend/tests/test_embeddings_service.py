import numpy as np

from app.services.embeddings import cosine_similarity, pack_vector, unpack_vector


def test_pack_unpack_roundtrip():
    vec = np.array([0.1, -0.2, 0.3, 0.0], dtype=np.float32)
    blob = pack_vector(vec)
    back = unpack_vector(blob)
    assert back.dtype == np.float32
    assert back.shape == (4,)
    np.testing.assert_array_equal(back, vec)


def test_cosine_similarity_identical():
    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    m = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    scores = cosine_similarity(q, m)
    assert abs(scores[0] - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array([[0.0, 1.0]], dtype=np.float32)
    assert abs(cosine_similarity(q, m)[0]) < 1e-6


def test_cosine_similarity_batch():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]], dtype=np.float32)
    scores = cosine_similarity(q, m)
    assert scores.shape == (3,)
    assert abs(scores[0] - 1.0) < 1e-6
    assert abs(scores[1]) < 1e-6
    assert abs(scores[2] + 1.0) < 1e-6
