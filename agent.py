import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_API_URL = "http://127.0.0.1:8000"
LOG_FILE = ROOT_DIR / "conversation_log.csv"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
LOG_FIELDS = ("actor", "message", "tool_call", "timestamp")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": "List all products and their current stock quantities.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Register a product in inventory with its starting quantity and unit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product name."},
                    "quantity": {"type": "number", "description": "Starting stock quantity."},
                    "unit": {"type": "string", "description": "Unit, such as units, kg, or liters."},
                },
                "required": ["name", "quantity", "unit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_stock",
            "description": "Change stock for an existing product. Use a positive delta for deliveries and a negative delta for sales.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "ID of the product to update."},
                    "delta": {"type": "number", "description": "Positive for incoming stock, negative for sold or used stock."},
                },
                "required": ["product_id", "delta"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Find products below a stock threshold, defaulting to 10 units.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number", "description": "Optional quantity cutoff; defaults to 10."}
                },
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are Carla's coffee-supply inventory assistant. Use inventory tools to "
    "check or change stock; never claim an update succeeded unless the API "
    "confirms it. For deliveries add to an existing product's stock. For sales "
    "subtract from stock. If a product is ambiguous or missing, ask a concise "
    "clarifying question. Summarize tool results in plain language and include "
    "useful quantities and units. You may call multiple tools when needed."
)


def call_inventory_api(tool_name: str, arguments: dict, api_url: str | None = None) -> dict:
    api_url = api_url or os.getenv("INVENTORY_API_URL", DEFAULT_API_URL)
    if tool_name == "get_inventory":
        method, path, body = "GET", "/inventory", None
    elif tool_name == "add_product":
        method, path, body = "POST", "/inventory", arguments
    elif tool_name == "adjust_stock":
        product_id = arguments.get("product_id")
        method, path, body = "PATCH", f"/inventory/{product_id}", {"delta": arguments.get("delta")}
    elif tool_name == "get_low_stock_alerts":
        method, path, body = "GET", "/inventory/alerts", None
        if "threshold" in arguments:
            path = f"{path}?{urlencode({'threshold': arguments['threshold']})}"
    else:
        return {"error": f"Unknown tool: {tool_name}"}

    request_body = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{api_url.rstrip('/')}{path}",
        data=request_body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = {"detail": error.reason}
        return {"error": detail.get("detail", str(detail)), "status_code": error.code}
    except URLError as error:
        return {"error": f"Inventory API is unavailable: {error.reason}"}


class InventoryAgent:
    def __init__(
        self,
        client=None,
        api_url: str | None = None,
        log_file: Path = LOG_FILE,
        model: str | None = None,
        max_tool_rounds: int = 8,
    ):
        self.api_url = api_url or os.getenv("INVENTORY_API_URL", DEFAULT_API_URL)
        self.log_file = Path(log_file)
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
        self.max_tool_rounds = max_tool_rounds
        if client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY is missing. Add it to your .env file.")
            client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        self.client = client
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _log(self, actor: str, message: str, tool_call: str = "") -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self.log_file.exists() or self.log_file.stat().st_size == 0
        with self.log_file.open("a", newline="", encoding="utf-8") as log_file:
            writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
            if needs_header:
                writer.writeheader()
            writer.writerow(
                {
                    "actor": actor,
                    "message": message,
                    "tool_call": tool_call,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    @staticmethod
    def _tool_call_values(tool_call) -> tuple[str, str, str]:
        if isinstance(tool_call, dict):
            function = tool_call["function"]
            return tool_call["id"], function["name"], function["arguments"]
        return tool_call.id, tool_call.function.name, tool_call.function.arguments

    def _run_tool(self, tool_call) -> dict:
        call_id, name, raw_arguments = self._tool_call_values(tool_call)
        try:
            arguments = json.loads(raw_arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            result = {"error": f"Invalid arguments for {name}: {error}"}
        else:
            self._log("tool", json.dumps(arguments, ensure_ascii=False), name)
            result = call_inventory_api(name, arguments, self.api_url)
        self._log("tool", json.dumps(result, ensure_ascii=False), name)
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
        return result

    def respond(self, user_text: str) -> str:
        self._log("user", user_text)
        self.messages.append({"role": "user", "content": user_text})

        for _ in range(self.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            message_data = {"role": "assistant", "content": getattr(message, "content", None)}
            if tool_calls:
                serialized_calls = []
                for tool_call in tool_calls:
                    call_id, name, arguments = self._tool_call_values(tool_call)
                    serialized_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    )
                message_data["tool_calls"] = serialized_calls
            self.messages.append(message_data)

            if not tool_calls:
                answer = message_data["content"] or "I couldn't produce a response. Please try again."
                self._log("agent", answer)
                return answer

            if message_data["content"]:
                self._log("agent", message_data["content"])
            for tool_call in tool_calls:
                self._run_tool(tool_call)

        answer = "I reached the limit for consecutive tool calls. Please ask me to continue."
        self.messages.append({"role": "assistant", "content": answer})
        self._log("agent", answer)
        return answer


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    try:
        agent = InventoryAgent()
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error

    print("Inventory assistant ready. Type 'exit' or 'quit' to leave.")
    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if not user_text:
            continue
        if user_text.casefold() in {"exit", "quit"}:
            print("Goodbye.")
            return
        try:
            print(f"Assistant: {agent.respond(user_text)}")
        except Exception as error:
            print(f"Assistant error: {error}")


if __name__ == "__main__":
    main()