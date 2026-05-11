# Contoso Travel MCP Server

A demo **Model Context Protocol (MCP)** server for **Contoso Travel** — a fictional airline + hotel
provider. It exposes read-only information about daily flights and hotels for 10 destinations
worldwide, backed by **Azure Table Storage**.

> Information only — no booking, no payments, no real-time pricing.

## Destinations

| City | IATA | Timezone |
|---|---|---|
| New York | JFK | America/New_York |
| Amsterdam | AMS | Europe/Amsterdam |
| Berlin | BER | Europe/Berlin |
| San Francisco | SFO | America/Los_Angeles |
| Bengaluru | BLR | Asia/Kolkata |
| Entebbe | EBB | Africa/Kampala |
| Rio de Janeiro | GIG | America/Sao_Paulo |
| Nairobi | NBO | Africa/Nairobi |
| Hong Kong | HKG | Asia/Hong_Kong |
| Tokyo | HND | Asia/Tokyo |

The seeder generates **10 cities**, **90 daily flights** (one in each direction between every city
pair, flight numbers `CT001`–`CT090`), and **100 hotels** (10 per city). Data is fully
deterministic — re-running the seeder produces identical rows.

## MCP tools

| Tool | Description |
|---|---|
| `list_cities` | List all 10 destinations. |
| `get_city_info(query)` | Resolve a city by IATA or name; includes current local time. |
| `search_flights(origin?, destination?, max_duration_minutes?)` | Search the daily schedule. |
| `get_flight(flight_number)` | Look up one flight, e.g. `CT042`. |
| `search_hotels(city, min_stars?, max_rate_usd?)` | List hotels for a city. |
| `get_hotel(hotel_id)` | Look up one hotel, e.g. `HKG-03`. |

Each flight record exposes `origin`, `destination`, local departure/arrival times in their
respective timezones, an `arrival_day_offset` (`-1`/`0`/`+1`), `duration_minutes`, `distance_km`
and `aircraft`.

## Quick start (local, with Azurite)

Prerequisites: Python 3.11+, Node.js (for [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)).

```bash
# 1. install Azurite (one-time) and start the Table service
npm install -g azurite
azurite-table --silent --location /tmp/azurite \
  --tablePort 10002 --tableHost 127.0.0.1 &

# 2. install the package
pip install -e .

# 3. configure env (UseDevelopmentStorage=true points at Azurite)
cp .env.example .env

# 4. seed the tables
python -m contoso_travel.seed --reset

# 5. run the MCP server (SSE on http://127.0.0.1:8000/sse)
python -m contoso_travel.server
```

## Configuration

The server reads configuration from environment variables (or a local `.env` file).

| Variable | Default | Description |
|---|---|---|
| `AZURE_STORAGE_CONNECTION_STRING` | _(required)_ | Azure Table Storage connection string. Use `UseDevelopmentStorage=true` for Azurite. |
| `MCP_HOST` | `127.0.0.1` | Bind host for the SSE server. |
| `MCP_PORT` | `8000` | Bind port for the SSE server. |

## VS Code MCP client config

Add the server to your VS Code `mcp.json` (or workspace `.vscode/mcp.json`):

```jsonc
{
  "servers": {
    "contoso-travel": {
      "type": "sse",
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

Then in chat, try prompts like:

- "List all Contoso Travel destinations."
- "Find a Contoso flight from AMS to JFK."
- "Show me 4-star hotels in Hong Kong under $300."
- "What's the local time in Tokyo right now?"

## Project layout

```
src/contoso_travel/
  cities.py       # 10 canonical cities (IATA, timezone, lat/lon)
  models.py       # Pydantic models: City, Flight, Hotel
  generator.py    # Deterministic flight + hotel generators
  storage.py      # Azure Table Storage read helpers
  seed.py         # CLI seeder (python -m contoso_travel.seed)
  server.py       # FastMCP server (SSE transport)
```

## Using a real Azure Storage account

Create a Storage account in the Azure portal, copy its connection string, and set it in `.env`:

```bash
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
python -m contoso_travel.seed --reset
python -m contoso_travel.server
```

## License

MIT — demo code only.