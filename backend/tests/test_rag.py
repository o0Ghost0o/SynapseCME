import asyncio

from app.agent import rag
from app.agent.extractor import extract
from app.models import ExtractionResult

DIM = 8

def run(coro):
    return asyncio.run(coro)

class FakeEmbedClient:
    """Deterministic 8-dim embeddings keyed on modality keywords."""

    async def embed(self, text: str, model: str | None = None) -> list[float] | None:
        vector = [0.0] * DIM
        lowered = text.lower()
        if "resonancia" in lowered or "rm" in lowered:
            vector[0] = 1.0
        elif "tomógrafo" in lowered or "tomografo" in lowered or "tc" in lowered:
            vector[1] = 1.0
        else:
            vector[2] = 1.0
        # small deterministic perturbation so identical keywords still differ
        vector[3] = (hash(text) % 100) / 1000.0
        return vector

class NoEmbedClient:
    async def embed(self, text: str, model: str | None = None) -> list[float] | None:
        return None

def _extraction(message: str) -> ExtractionResult:
    return extract(message)

def test_index_and_retrieve_roundtrip(tmp_path):
    client = FakeEmbedClient()
    data_dir = str(tmp_path)
    msgs = [
        "Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas",
        "En el Hospital Central vi 2 tomógrafos Siemens",
        "Hay ultrasonidos en sala 3 del Hospital Norte",
    ]
    for msg in msgs:
        ext = _extraction(msg)
        assert run(rag.index_extraction(client, ext, data_dir=data_dir)) == 1

    rows = run(rag.retrieve(client, "vi una resonancia nueva", data_dir=data_dir, top_k=2))
    assert len(rows) == 2
    assert "resonancia" in rows[0]["text"]
    assert rows[0]["facility"] == "Hospital Aurora"
    assert "extractor" in rows[0]

def test_index_without_embedder_returns_zero(tmp_path):
    ext = _extraction("Visité el Hospital Aurora, vi 1 resonancia")
    assert run(rag.index_extraction(NoEmbedClient(), ext, data_dir=str(tmp_path))) == 0
    assert not (tmp_path / "observations.lance").exists()

def test_retrieve_empty_when_no_table(tmp_path):
    rows = run(
        rag.retrieve(FakeEmbedClient(), "cualquier mensaje", data_dir=str(tmp_path), top_k=3)
    )
    assert rows == []

def test_build_context_formats_snippets(tmp_path):
    client = FakeEmbedClient()
    data_dir = str(tmp_path)
    ext = _extraction("Visité el Hospital Aurora en Panamá, vi 3 resonancias magnéticas")
    run(rag.index_extraction(client, ext, data_dir=data_dir))
    context = run(rag.build_context(client, "vi una resonancia nueva", data_dir=data_dir, top_k=3))
    assert context.startswith("Contexto previo de la base de conocimiento:")
    assert "Hospital Aurora" in context
    assert "resonancia" in context

def test_build_context_empty_when_nothing(tmp_path):
    context = run(
        rag.build_context(FakeEmbedClient(), "hoy llovió mucho", data_dir=str(tmp_path), top_k=3)
    )
    assert context == ""
