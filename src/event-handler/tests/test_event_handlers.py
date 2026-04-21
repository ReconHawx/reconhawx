"""Unit tests for event_handlers.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.event_handlers import (
    ActionResult,
    SimpleEventHandler,
    SimpleBatchManager,
    SimpleHandlerRegistry,
    _normalize_conditions_by_event_type,
)


class TestActionResult:
    """Tests for ActionResult dataclass."""

    def test_success_result(self):
        r = ActionResult(success=True, message="ok")
        assert r.success is True
        assert r.message == "ok"
        assert r.data is None

    def test_failure_result_with_data(self):
        r = ActionResult(success=False, message="fail", data={"error": "x"})
        assert r.success is False
        assert r.data["error"] == "x"


class TestSimpleEventHandler:
    """Tests for SimpleEventHandler."""

    def test_check_conditions_field_exists_present(self):
        config = {
            "event_type": "test",
            "conditions": [{"type": "field_exists", "field": "name"}],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("test", config)
        assert handler.check_conditions({"name": "value"}) is True

    def test_check_conditions_field_exists_missing(self):
        config = {
            "event_type": "test",
            "conditions": [{"type": "field_exists", "field": "name"}],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("test", config)
        assert handler.check_conditions({}) is False

    def test_check_conditions_field_exists_nested(self):
        config = {
            "event_type": "test",
            "conditions": [{"type": "field_exists", "field": "asset.name"}],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("test", config)
        assert handler.check_conditions({"asset": {"name": "x"}}) is True
        assert handler.check_conditions({"asset": {}}) is False

    def test_check_conditions_field_value_equals(self):
        config = {
            "event_type": "test",
            "conditions": [
                {"type": "field_value", "field": "severity", "expected_value": "critical", "operator": "equals"}
            ],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("test", config)
        assert handler.check_conditions({"severity": "critical"}) is True
        assert handler.check_conditions({"severity": "high"}) is False

    def test_check_conditions_field_value_not_equals(self):
        config = {
            "event_type": "test",
            "conditions": [
                {"type": "field_value", "field": "status", "expected_value": "done", "operator": "not_equals"}
            ],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("test", config)
        assert handler.check_conditions({"status": "pending"}) is True
        assert handler.check_conditions({"status": "done"}) is False

    def test_get_nested_value_simple(self):
        config = {"event_type": "test", "conditions": [], "actions": []}
        handler = SimpleEventHandler("test", config)
        assert handler._get_nested_value({"a": 1}, "a") == 1

    def test_get_nested_value_nested(self):
        config = {"event_type": "test", "conditions": [], "actions": []}
        handler = SimpleEventHandler("test", config)
        assert handler._get_nested_value({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_get_nested_value_missing_returns_none(self):
        config = {"event_type": "test", "conditions": [], "actions": []}
        handler = SimpleEventHandler("test", config)
        assert handler._get_nested_value({"a": 1}, "b") is None
        assert handler._get_nested_value({"a": {"b": 1}}, "a.c") is None

    def test_substitute_template_simple(self):
        config = {"event_type": "test", "conditions": [], "actions": []}
        handler = SimpleEventHandler("test", config)
        result = handler._substitute_template("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    def test_substitute_template_nested(self):
        config = {"event_type": "test", "conditions": [], "actions": []}
        handler = SimpleEventHandler("test", config)
        result = handler._substitute_template(
            "Program: {program_name}",
            {"program_name": "my-program"},
        )
        assert result == "Program: my-program"

    def test_substitute_template_missing_keeps_placeholder(self):
        config = {"event_type": "test", "conditions": [], "actions": []}
        handler = SimpleEventHandler("test", config)
        result = handler._substitute_template("Hello {missing}", {})
        assert result == "Hello {missing}"

    @pytest.mark.asyncio
    async def test_handle_event_executes_log_action(self):
        config = {
            "event_type": "assets.subdomain.created",
            "conditions": [{"type": "field_exists", "field": "name"}],
            "actions": [{"type": "log", "level": "info", "message_template": "Domain: {name}"}],
        }
        handler = SimpleEventHandler("test", config)
        results = await handler.handle_event({"name": "test.example.com", "program_name": "p1"})
        assert len(results) == 1
        assert results[0].success is True
        assert "logged" in results[0].message.lower()

    @pytest.mark.asyncio
    async def test_handle_event_skips_when_conditions_fail(self):
        config = {
            "event_type": "assets.subdomain.created",
            "conditions": [{"type": "field_exists", "field": "name"}],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("test", config)
        results = await handler.handle_event({"program_name": "p1"})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_handle_event_unknown_action_returns_failure(self):
        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [{"type": "unknown_action_type"}],
        }
        handler = SimpleEventHandler("test", config)
        results = await handler.handle_event({"program_name": "p1"})
        assert len(results) == 1
        assert results[0].success is False
        assert "Unknown action" in results[0].message


class TestNormalizeConditionsByEventType:
    def test_none_and_non_dict(self):
        assert _normalize_conditions_by_event_type(None) == {}
        assert _normalize_conditions_by_event_type([]) == {}
        assert _normalize_conditions_by_event_type("x") == {}

    def test_coerces_drops_non_lists_and_empty(self):
        assert _normalize_conditions_by_event_type(
            {
                "a.b": [{"type": "field_value", "field": "x"}],
                "  trim  ": [],
                "bad": "not-list",
                123: [{"type": "field_value", "field": "y"}],
            }
        ) == {"a.b": [{"type": "field_value", "field": "x"}]}


class TestConditionsByEventTypeMatching:
    def test_per_type_branch_created_vs_updated(self):
        cfg = {
            "event_type": ["assets.subdomain.created", "assets.subdomain.updated"],
            "conditions": [],
            "conditions_by_event_type": {
                "assets.subdomain.created": [
                    {
                        "type": "field_value",
                        "field": "resolution_status",
                        "operator": "equals",
                        "expected_value": "created_resolved",
                    },
                ],
                "assets.subdomain.updated": [
                    {"type": "field_value", "field": "new_ip_count", "operator": "greater_than", "expected_value": 0},
                    {"type": "field_value", "field": "previous_ip_count", "operator": "equals", "expected_value": 0},
                ],
            },
            "actions": [{"type": "log"}],
        }
        h = SimpleEventHandler("merged", cfg)
        assert h.check_conditions(
            {"event_type": "assets.subdomain.created", "resolution_status": "created_resolved"}
        )
        assert not h.check_conditions(
            {"event_type": "assets.subdomain.created", "resolution_status": "wrong"}
        )
        assert h.check_conditions(
            {"event_type": "assets.subdomain.updated", "new_ip_count": 1, "previous_ip_count": 0}
        )
        assert not h.check_conditions(
            {"event_type": "assets.subdomain.updated", "new_ip_count": 0, "previous_ip_count": 0}
        )

    def test_shared_conditions_then_per_type(self):
        cfg = {
            "event_type": ["a.created", "a.updated"],
            "conditions": [
                {"type": "field_value", "field": "program_name", "operator": "equals", "expected_value": "p1"},
            ],
            "conditions_by_event_type": {
                "a.created": [{"type": "field_value", "field": "x", "operator": "equals", "expected_value": 1}],
            },
            "actions": [{"type": "log"}],
        }
        h = SimpleEventHandler("h", cfg)
        assert h.check_conditions({"event_type": "a.updated", "program_name": "p1"})
        assert not h.check_conditions({"event_type": "a.created", "program_name": "p1", "x": 2})
        assert h.check_conditions({"event_type": "a.created", "program_name": "p1", "x": 1})

    def test_missing_per_type_entry_no_extra_constraint(self):
        cfg = {
            "event_type": ["a.created", "a.updated"],
            "conditions": [{"type": "field_exists", "field": "id"}],
            "conditions_by_event_type": {
                "a.created": [{"type": "field_value", "field": "x", "operator": "equals", "expected_value": 1}],
            },
            "actions": [{"type": "log"}],
        }
        h = SimpleEventHandler("h", cfg)
        assert h.check_conditions({"event_type": "a.updated", "id": "1"})

    def test_extra_map_keys_ignored_for_incoming_type(self):
        cfg = {
            "event_type": ["a.created"],
            "conditions": [],
            "conditions_by_event_type": {
                "a.created": [{"type": "field_value", "field": "x", "operator": "equals", "expected_value": 1}],
                "other.type": [{"type": "field_value", "field": "x", "operator": "equals", "expected_value": 99}],
            },
            "actions": [{"type": "log"}],
        }
        h = SimpleEventHandler("h", cfg)
        assert h.check_conditions({"event_type": "a.created", "x": 1})


class TestSimpleBatchManager:
    """Tests for SimpleBatchManager."""

    def test_add_to_batch_returns_dict(self):
        redis = MagicMock()
        # Pipeline: rpush, setnx, expire, expire, llen, get -> 6 results
        # Code uses results[4]=count, results[5]=first_ts
        import time
        now = int(time.time())
        pipe = MagicMock()
        pipe.execute.return_value = [None, None, None, None, 1, str(now).encode()]

        def pipeline(*args, **kwargs):
            return pipe

        redis.pipeline = pipeline

        cfg = MagicMock()
        mgr = SimpleBatchManager(redis, cfg)
        result = mgr.add_to_batch(
            "handler1",
            {"program_name": "p1", "name": "test.com"},
            {"max_events": 10, "max_delay_seconds": 60},
        )
        assert "count" in result
        assert "should_flush" in result
        assert "age_seconds" in result

    def test_get_and_clear_batch_returns_list(self):
        redis = MagicMock()
        pipe = MagicMock()
        redis.pipeline.return_value = pipe
        pipe.execute.return_value = [
            [b'{"name": "test.com", "program_name": "p1"}'],
            None,
            None,
        ]

        cfg = MagicMock()
        mgr = SimpleBatchManager(redis, cfg)
        items = mgr.get_and_clear_batch("handler1", "p1")
        assert len(items) == 1
        assert items[0]["name"] == "test.com"


class TestSimpleHandlerRegistry:
    """Tests for SimpleHandlerRegistry."""

    def test_register_and_get_handlers(self):
        registry = SimpleHandlerRegistry()
        config = {"event_type": "assets.subdomain.created", "conditions": [], "actions": [{"type": "log"}]}
        handler = SimpleEventHandler("subdomain_handler", config)
        registry.register_handler(handler)
        handlers = registry.get_handlers("assets.subdomain.created")
        assert len(handlers) == 1
        assert handlers[0].handler_id == "subdomain_handler"

    def test_register_multi_event_type_same_instance_get_handler_by_id(self):
        registry = SimpleHandlerRegistry()
        config = {
            "event_type": ["assets.subdomain.created", "assets.subdomain.updated"],
            "conditions": [],
            "actions": [{"type": "log"}],
        }
        handler = SimpleEventHandler("merged", config)
        registry.register_handler(handler)
        assert registry.get_handler_by_id("merged") is handler
        assert len(registry.get_handlers("assets.subdomain.created")) == 1
        assert len(registry.get_handlers("assets.subdomain.updated")) == 1
        assert registry.get_handlers("assets.subdomain.created")[0] is handler

    def test_get_handlers_empty_for_unknown_type(self):
        registry = SimpleHandlerRegistry()
        assert registry.get_handlers("unknown.event.type") == []

    @pytest.mark.asyncio
    async def test_handle_event_dispatches_to_registered_handler(self):
        registry = SimpleHandlerRegistry()
        config = {
            "event_type": "assets.subdomain.created",
            "conditions": [{"type": "field_exists", "field": "name"}],
            "actions": [{"type": "log", "level": "info", "message_template": "Got {name}"}],
        }
        handler = SimpleEventHandler("subdomain_handler", config)
        registry.register_handler(handler)
        results = await registry.handle_event(
            "assets.subdomain.created",
            {"name": "api.example.com", "program_name": "p1"},
        )
        assert len(results) == 1
        assert results[0].success is True


class TestWorkflowActionAsyncHttp:
    """Tests for workflow_trigger action using async HTTP (httpx)."""

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_workflow_action_success_uses_async_client(self, mock_get_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"workflow_id": "wf-123", "id": "wf-123"}
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {
                    "type": "workflow_trigger",
                    "api_url": "http://api:8000",
                    "api_key": "secret",
                    "parameters": {"workflow_name": "test_workflow"},
                }
            ],
        }
        handler = SimpleEventHandler("workflow_handler", config)
        event_data = {
            "program_name": "p1",
            "api_base_url": "http://api:8000",
            "internal_api_key": "secret",
        }
        result = await handler._execute_workflow_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is True
        assert result.data["workflow_id"] == "wf-123"
        mock_get_client.assert_called_once()
        mock_post.assert_awaited_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["workflow_name"] == "test_workflow"
        assert call_kwargs["headers"]["Authorization"] == "Bearer secret"

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_workflow_action_non_200_returns_failure(self, mock_get_client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {
                    "type": "workflow_trigger",
                    "parameters": {"workflow_name": "test_workflow"},
                }
            ],
        }
        handler = SimpleEventHandler("workflow_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_workflow_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is False
        assert "500" in result.message

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_workflow_action_http_error_returns_failure(self, mock_get_client):
        mock_get_client.side_effect = httpx.ConnectError("connection refused")

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {
                    "type": "workflow_trigger",
                    "parameters": {"workflow_name": "test_workflow"},
                }
            ],
        }
        handler = SimpleEventHandler("workflow_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_workflow_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is False
        assert "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_workflow_action_missing_workflow_name_returns_failure(self):
        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [{"type": "workflow_trigger", "parameters": {}}],
        }
        handler = SimpleEventHandler("workflow_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_workflow_action(
            config["actions"][0], event_data, is_batch=False
        )
        assert result.success is False
        assert "workflow name" in result.message.lower()


class TestPhishlabsBatchActionAsyncHttp:
    """Tests for phishlabs_batch_trigger action using async HTTP (httpx)."""

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_phishlabs_action_success_uses_async_client(self, mock_get_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "job-456"}
        mock_response.headers = {}
        mock_response.text = "{}"
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {
                    "type": "phishlabs_batch_trigger",
                    "finding_ids": ["f1", "f2"],
                    "api_url": "http://api:8000",
                    "api_key": "secret",
                }
            ],
        }
        handler = SimpleEventHandler("phishlabs_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_phishlabs_batch_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is True
        assert result.data["job_id"] == "job-456"
        assert result.data["finding_count"] == 2
        mock_get_client.assert_called_once()
        mock_post.assert_awaited_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["finding_ids"] == ["f1", "f2"]

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_phishlabs_action_extracts_finding_ids_from_event(self, mock_get_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "job-789"}
        mock_response.headers = {}
        mock_response.text = "{}"
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {
                    "type": "phishlabs_batch_trigger",
                    "finding_id_template": "{id}",
                    "api_url": "http://api:8000",
                }
            ],
        }
        handler = SimpleEventHandler("phishlabs_handler", config)
        event_data = {"program_name": "p1", "id": "finding-abc"}
        result = await handler._execute_phishlabs_batch_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is True
        assert result.data["finding_count"] == 1
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["finding_ids"] == ["finding-abc"]

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_phishlabs_action_non_200_returns_failure(self, mock_get_client):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_get_client.return_value = mock_client

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {"type": "phishlabs_batch_trigger", "finding_ids": ["f1"]},
            ],
        }
        handler = SimpleEventHandler("phishlabs_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_phishlabs_batch_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is False
        assert "400" in result.message

    @pytest.mark.asyncio
    @patch("app.event_handlers._get_http_client")
    async def test_phishlabs_action_http_error_returns_failure(self, mock_get_client):
        mock_get_client.side_effect = httpx.TimeoutException("timed out")

        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {"type": "phishlabs_batch_trigger", "finding_ids": ["f1"]},
            ],
        }
        handler = SimpleEventHandler("phishlabs_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_phishlabs_batch_action(
            config["actions"][0], event_data, is_batch=False
        )

        assert result.success is False
        assert "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_phishlabs_action_no_finding_ids_returns_failure(self):
        config = {
            "event_type": "test",
            "conditions": [],
            "actions": [
                {"type": "phishlabs_batch_trigger"},
            ],
        }
        handler = SimpleEventHandler("phishlabs_handler", config)
        event_data = {"program_name": "p1"}
        result = await handler._execute_phishlabs_batch_action(
            config["actions"][0], event_data, is_batch=False
        )
        assert result.success is False
        assert "finding" in result.message.lower()
