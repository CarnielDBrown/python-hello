# Coffee Supply Inventory Agent

A local CSV-backed inventory API and conversational assistant for a coffee supply store. The agent can check stock, register products and deliveries, record sales, and report low-stock items.

## Setup

Use Python 3.10 or newer. Install the dependencies and create a local environment file:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `GROQ_API_KEY` in `.env`. The optional `GROQ_MODEL` setting defaults to `llama-3.3-70b-versatile`; `INVENTORY_API_URL` defaults to `http://127.0.0.1:8000`. Keep `.env` private; it is ignored by Git.

## Run

Start the API in one terminal:

```bash
uvicorn api.app:app --reload
```

Start the conversational agent in a second terminal:

```bash
python agent.py
```

Type `exit` or `quit` to end the agent session. The API reads and writes `products.csv`. Conversation events are appended to `conversation_log.csv` and remain available across agent sessions.

Example requests:

- "We just received 30 units of oat milk."
- "We sold 2 kg of arabica coffee beans."
- "What products are running low?"

Run the automated tests with `pytest -q`.
