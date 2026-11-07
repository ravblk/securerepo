"""Регрессии по ошибкам, которые ломают результат аудита."""

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDEXER_DIR = ROOT / "services" / "indexer-service"
WORKER_DIR = ROOT / "services" / "audit-worker"
INGESTION_DIR = ROOT / "services" / "internal-rules-ingestion"


def _load_indexer_app():
    _ensure_path(INDEXER_DIR)
    module_name = "indexer_app"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, INDEXER_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_path(path: Path) -> None:
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _install_llm_stubs() -> None:
    """Импорт воркера не должен тянуть LangChain и Langfuse."""

    def module(name: str, **attrs):
        existing = sys.modules.get(name)
        if existing is not None and all(hasattr(existing, key) for key in attrs):
            return existing
        mod = existing or types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    class _Message:
        def __init__(self, content):
            self.content = content

    module("langchain_core")
    module("langchain_core.messages", SystemMessage=_Message, HumanMessage=_Message)
    module("langchain_openai", ChatOpenAI=object)

    class _StateGraph:
        def __init__(self, *args, **kwargs):
            pass

        def add_node(self, *args, **kwargs):
            pass

        def add_edge(self, *args, **kwargs):
            pass

        def set_entry_point(self, *args, **kwargs):
            pass

        def compile(self):
            return self

    module("langgraph")
    module("langgraph.graph", StateGraph=_StateGraph, END="END")
    module("langfuse", Langfuse=object)
    module("langfuse.callback", CallbackHandler=object)


def test_policy_point_ids_do_not_alias():
    _ensure_path(INGESTION_DIR)
    from ingestion.point_ids import policy_point_id

    # Старая склейка str(page)+zfill(chunk, 2) давала 1234 для обеих пар.
    assert policy_point_id(1, 234) != policy_point_id(12, 34)
    assert policy_point_id(1, 234) == 1_000_234
    assert policy_point_id(12, 34) == 12_000_034
    assert policy_point_id(1, 234) == policy_point_id(1, 234)


def test_parser_keeps_file_without_functions(tmp_path):
    _ensure_path(INDEXER_DIR)
    from indexer.parsers import parse_file

    source = tmp_path / "script.py"
    source.write_text('print("hello")\n', encoding="utf-8")

    chunks, _symbols = parse_file(source, "python", audit_id="audit-1")

    assert len(chunks) == 1
    assert "print" in chunks[0].code


def test_parser_does_not_duplicate_function_file(tmp_path):
    _ensure_path(INDEXER_DIR)
    from indexer.parsers import parse_file

    source = tmp_path / "mod.py"
    source.write_text("def foo():\n    return 1\n", encoding="utf-8")

    chunks, _symbols = parse_file(source, "python")

    assert len(chunks) == 1
    assert chunks[0].function_name == "foo"


def test_rules_search_uses_nearest_neighbours():
    _ensure_path(WORKER_DIR)
    _install_llm_stubs()
    from audit.qdrant_service import QdrantService

    client = MagicMock()
    client.search.return_value = [
        SimpleNamespace(
            score=0.91,
            payload={"title": "SQL", "text": "use binds", "lang": "python"},
        )
    ]
    client.scroll.side_effect = AssertionError("scroll must not rank the collection")

    service = QdrantService.__new__(QdrantService)
    service._client = client
    service._collection_name = "internal_policies"
    service._default_lang = "python"

    rules = service.search_basic_rules([0.2, 0.4], "python", limit=3)

    client.search.assert_called_once()
    kwargs = client.search.call_args.kwargs
    assert kwargs["query_vector"] == [0.2, 0.4]
    assert kwargs["limit"] >= 30
    assert rules[0]["text"] == "use binds"
    assert rules[0]["similarity"] == pytest.approx(0.91)


def test_empty_rules_still_call_llm():
    _ensure_path(WORKER_DIR)
    _install_llm_stubs()
    from audit.audit_workflow import AuditWorkflow

    workflow = object.__new__(AuditWorkflow)
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content='{"violations": []}')
    workflow._llm_service = MagicMock(get_llm=MagicMock(return_value=llm))
    workflow._current_trace = None

    result = workflow._analyze_code({
        "code": "print(1)",
        "file_path": "a.py",
        "lang": "python",
        "internal_rules": [],
        "audit_id": "audit-1",
        "enriched_context": "",
    })

    llm.invoke.assert_called_once()
    assert result["violations"] == []


def test_invalid_llm_json_is_an_error():
    _ensure_path(WORKER_DIR)
    _install_llm_stubs()
    from audit.audit_workflow import AuditWorkflow
    from audit.exceptions import WorkflowError

    workflow = object.__new__(AuditWorkflow)
    violations, error = workflow._parse_llm_response("this is not json")
    assert violations is None
    assert error

    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="this is not json")
    workflow._llm_service = MagicMock(get_llm=MagicMock(return_value=llm))
    workflow._current_trace = None

    with pytest.raises(WorkflowError):
        workflow._analyze_code({
            "code": "print(1)",
            "file_path": "a.py",
            "lang": "python",
            "internal_rules": [{"rule_id": "r", "text": "rule", "url": ""}],
            "audit_id": "audit-1",
            "enriched_context": "",
        })


def test_indexer_publishes_tasks_without_qdrant():
    main = _load_indexer_app()
    from indexer.models import CodeChunk, RepoMessage

    message = RepoMessage(
        repo_url="https://example.com/repo.git",
        branch="main",
        lang="python",
        audit_id="audit-1",
    )
    chunk = CodeChunk(
        id="a.py:1",
        file_path="a.py",
        function_name=None,
        code="print(1)",
        start_line=1,
        end_line=1,
    )
    main.clone_repo = lambda *args, **kwargs: Path("/tmp/repo")
    main.collect_chunks = lambda *args, **kwargs: ([chunk], [])
    main.kafka_service = MagicMock()

    main.process_repo(message)

    main.kafka_service.send_audit_tasks_from_chunks.assert_called_once_with(
        "audit-1", [chunk], "python",
    )
    main.kafka_service.send_status.assert_called_once_with(
        "audit-1", "indexed", total_chunks=1,
    )


def test_empty_repo_completes_instead_of_indexed_with_zero_tasks():
    main = _load_indexer_app()
    from indexer.models import RepoMessage

    message = RepoMessage(
        repo_url="https://example.com/repo.git",
        branch="main",
        lang="python",
        audit_id="audit-empty",
    )
    main.clone_repo = lambda *args, **kwargs: Path("/tmp/repo")
    main.collect_chunks = lambda *args, **kwargs: ([], [])
    main.kafka_service = MagicMock()

    main.process_repo(message)

    main.kafka_service.send_status.assert_called_once_with(
        "audit-empty", "completed", total_chunks=0
    )
    main.kafka_service.send_audit_tasks.assert_not_called()


def test_partial_task_publish_raises():
    _ensure_path(INDEXER_DIR)
    from indexer.exceptions import KafkaPublishError
    from indexer.kafka_service import KafkaService

    service = KafkaService()
    producer = MagicMock()
    failed = MagicMock()
    failed.get.side_effect = RuntimeError("not acknowledged")
    producer.send.side_effect = [MagicMock(), failed]
    service._producer = producer
    point = SimpleNamespace(payload={
        "chunk_id": "c",
        "code": "x",
        "file_path": "a.py",
        "lang": "python",
    })

    with pytest.raises(KafkaPublishError) as caught:
        service.send_audit_tasks("audit-1", [point, point])

    assert caught.value.audit_id == "audit-1"


def test_indexer_reads_backlog_without_auto_commit():
    _ensure_path(INDEXER_DIR)
    from indexer.kafka_service import KafkaService

    settings = KafkaService().consumer_settings()

    assert settings["auto_offset_reset"] == "earliest"
    assert settings["enable_auto_commit"] is False


def test_worker_error_is_not_swallowed():
    _ensure_path(WORKER_DIR)
    _install_llm_stubs()
    import main as worker_main

    worker_main.failed_audits.clear()
    worker_main.auditing_sent.clear()
    worker_main.audit_controller = MagicMock()
    worker_main.audit_controller.should_send_auditing_status.return_value = False
    worker_main.audit_controller.process_task.side_effect = RuntimeError("llm down")
    message = SimpleNamespace(value={
        "chunk_id": "c1",
        "code": "print(1)",
        "file_path": "a.py",
        "audit_id": "audit-1",
        "chunk_index": 0,
        "total_chunks": 2,
    })

    with pytest.raises(RuntimeError, match="llm down"):
        worker_main.process_message(message, None)

    worker_main.audit_controller.send_failed_status.assert_not_called()
    assert "audit-1" not in worker_main.failed_audits


def test_abandon_writes_dlq_and_fails_audit():
    _ensure_path(WORKER_DIR)
    _install_llm_stubs()
    import main as worker_main

    worker_main.failed_audits.clear()
    worker_main.kafka_service = MagicMock()
    worker_main.audit_controller = MagicMock()
    message = SimpleNamespace(value={"audit_id": "audit-1", "chunk_id": "c1"})

    worker_main.abandon_message(message, "still failing")

    worker_main.kafka_service.send_to_dlq.assert_called_once_with(
        {"audit_id": "audit-1", "chunk_id": "c1"},
        "still failing",
    )
    worker_main.audit_controller.send_failed_status.assert_called_once_with(
        "audit-1", "still failing"
    )
    assert "audit-1" in worker_main.failed_audits


def test_upsert_does_not_repeat_last_batch():
    _ensure_path(INGESTION_DIR)
    from qdrant_client.models import PointStruct

    from ingestion.qdrant_service import QdrantService

    calls = []

    class Retry:
        def execute_with_retry(self, func, name, **kwargs):
            calls.append(name)
            return func()

    service = QdrantService.__new__(QdrantService)
    service._retry_service = Retry()
    service._client = MagicMock()
    points = [
        PointStruct(id=index, vector=[0.1], payload={"n": index})
        for index in range(3)
    ]

    service.upsert_points(points)

    assert len(calls) == 1
