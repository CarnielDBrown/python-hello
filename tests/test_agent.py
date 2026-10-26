import csv
import json
from datetime import datetime
from types import SimpleNamespace

from agent import InventoryAgent, call_inventory_api


def make_tool_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def make_response(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=tool_calls or [])
            )
        ]
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return next(self.responses)


def test_agent_runs_tool_loop_and_logs_every_event(tmp_path, monkeypatch):
    completions = FakeCompletions(
        [
            make_response(tool_calls=[make_tool_call("add_product", {
                "name": "Oat milk", "quantity": 30, "unit": "cartons"
            })]),
            make_response(content="Added 30 cartons of oat milk.")
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    api_calls = []

    def fake_api_call(name, arguments, api_url):
        api_calls.append((name, arguments, api_url))
        return {"message": "Added product.", "product": {"product_id": 1}}

    monkeypatch.setattr("agent.call_inventory_api", fake_api_call)
    log_file = tmp_path / "conversation_log.csv"
    agent = InventoryAgent(client=client, api_url="http://inventory.test", log_file=log_file)

    answer = agent.respond("We received 30 cartons of oat milk.")

    assert answer == "Added 30 cartons of oat milk."
    assert api_calls == [
        ("add_product", {"name": "Oat milk", "quantity": 30, "unit": "cartons"}, "http://inventory.test")
    ]
    second_request_messages = completions.requests[1]["messages"]
    assert any(message["role"] == "tool" and message["tool_call_id"] == "call-1" for message in second_request_messages)

    with log_file.open(newline="", encoding="utf-8") as conversation_file:
        rows = list(csv.DictReader(conversation_file))
    assert list(rows[0]) == ["actor", "message", "tool_call", "timestamp"]
    assert [row["actor"] for row in rows] == ["user", "tool", "tool", "agent"]
    assert [row["tool_call"] for row in rows] == ["", "add_product", "add_product", ""]
    assert json.loads(rows[2]["message"]) == {"message": "Added product.", "product": {"product_id": 1}}
    for row in rows:
        datetime.fromisoformat(row["timestamp"])


def test_conversation_log_appends_between_agent_sessions(tmp_path):
    log_file = tmp_path / "conversation_log.csv"
    for response_text in ("First answer.", "Second answer."):
        completions = FakeCompletions([make_response(content=response_text)])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        InventoryAgent(client=client, log_file=log_file).respond("Check stock.")

    with log_file.open(newline="", encoding="utf-8") as conversation_file:
        rows = list(csv.DictReader(conversation_file))
    assert [row["actor"] for row in rows] == ["user", "agent", "user", "agent"]
    assert [row["message"] for row in rows if row["actor"] == "agent"] == [
        "First answer.", "Second answer."
    ]


def test_tools_map_to_inventory_api_endpoints(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"message":"ok"}'

    def fake_urlopen(request, timeout):
        requests.append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "body": json.loads(request.data) if request.data else None,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    monkeypatch.setattr("agent.urlopen", fake_urlopen)
    call_inventory_api("get_inventory", {}, "http://inventory.test")
    call_inventory_api(
        "add_product", {"name": "Beans", "quantity": 3, "unit": "kg"}, "http://inventory.test"
    )
    call_inventory_api("adjust_stock", {"product_id": 7, "delta": -2}, "http://inventory.test")
    call_inventory_api("get_low_stock_alerts", {"threshold": 4.5}, "http://inventory.test")

    assert requests == [
        {"method": "GET", "url": "http://inventory.test/inventory", "body": None, "timeout": 15},
        {
            "method": "POST",
            "url": "http://inventory.test/inventory",
            "body": {"name": "Beans", "quantity": 3, "unit": "kg"},
            "timeout": 15,
        },
        {
            "method": "PATCH",
            "url": "http://inventory.test/inventory/7",
            "body": {"delta": -2},
            "timeout": 15,
        },
        {
            "method": "GET",
            "url": "http://inventory.test/inventory/alerts?threshold=4.5",
            "body": None,
            "timeout": 15,
        },
    ]