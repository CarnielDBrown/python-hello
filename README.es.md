# Agente de inventario para suministros de café

Una API local de inventario respaldada por CSV y un asistente conversacional para una tienda de suministros de café. El agente puede consultar existencias, registrar productos y entregas, anotar ventas y avisar cuando el stock es bajo.

## Configuración

Usa Python 3.10 o posterior. Instala las dependencias y crea el archivo de entorno local:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
```

Configura `GROQ_API_KEY` en `.env`. `GROQ_MODEL` es opcional y, por defecto, usa `llama-3.3-70b-versatile`. `INVENTORY_API_URL` es opcional y, por defecto, usa `http://127.0.0.1:8000`. No compartas `.env`; Git lo ignora.

## Ejecución

Inicia la API en una terminal:

```bash
uvicorn api.app:app --reload
```

Inicia el agente conversacional en otra terminal:

```bash
python agent.py
```

Escribe `exit` o `quit` para terminar la sesión. La API lee y actualiza `products.csv`. Los eventos se agregan a `conversation_log.csv` y permanecen entre sesiones.

Ejemplos:

- «Acabamos de recibir 30 unidades de leche de avena».
- «Vendimos 2 kg de café arábica».
- «¿Qué productos tienen poco stock?».

Ejecuta las pruebas con `pytest -q`.
