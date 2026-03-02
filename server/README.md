# Real-time WebSocket Backend (Go + Postgres)

This backend broadcasts real-time crowd updates to all connected WebSocket clients.

The flow is:

1. A new row is inserted into Postgres table `crowd_updates`.
2. A Postgres trigger sends a `NOTIFY` payload on channel `crowd_updates_channel`.
3. The Go backend is subscribed with `LISTEN` and broadcasts that payload to all WebSocket clients.

## Endpoints

- `GET /health` — health check
- `GET /ws` — WebSocket endpoint for frontend subscriptions
- `POST /devices/location` — creates or updates a `device_id` to `location_label` mapping
- `POST /db/push` — accepts update packet JSON and inserts it into Postgres (trigger handles broadcast)

## Packet format

```json
{
    "device_id": "DEV-001",
    "timestamp": "2023-10-27T10:00:00Z",
    "status": "active",
    "metrics": {
        "people_count": 142,
        "crowd_density": 0.45,
        "threshold": 0.75
    }
}
```

`location_label` is inferred by the backend from table `device_locations` using `device_id`.

## Run with Docker (backend + postgres)

```bash
cd server
docker compose up --build
```

This starts:

- Postgres on `localhost:5432`
- Backend on `localhost:8080`

## Test publish

Create a device/location mapping first:

```bash
curl -X POST http://localhost:8080/devices/location \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "DEV-001",
    "location_label": "North Gate Area"
  }'
```

```bash
curl -X POST http://localhost:8080/db/push \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "DEV-001",
    "timestamp": "2023-10-27T10:00:00Z",
    "status": "active",
    "metrics": {
      "people_count": 142,
      "crowd_density": 0.45,
      "threshold": 0.75
    }
  }'
```

If `device_id` has no row in `device_locations`, backend returns `400`.

## Frontend WebSocket usage

```js
const ws = new WebSocket("ws://localhost:8080/ws");

ws.onmessage = (event) => {
    const packet = JSON.parse(event.data);
    console.log("Realtime update:", packet);
};
```

When a client connects, backend first sends the latest known record for every `device_id`, then continues streaming real-time inserts.

## Local run (without Docker)

You need a running Postgres instance and this env var:

```bash
export DATABASE_URL="postgres://postgres:postgres@localhost:5432/crowd_updates?sslmode=disable"
cd server
go run .
```

Schema and trigger SQL are in `db/init.sql`.
