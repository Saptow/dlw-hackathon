# Crowd Control Operations Dashboard

## 🚀 Getting Started

1. **Install Dependencies:**
   ```bash
   npm install
   ```
2. **Run the Development Server:**
   ```bash
   npm run dev
   ```
3. Open `http://localhost:5173` in your browser.

*Note: By default, the dashboard runs in Simulator Mode, generating fake telemetry data for demonstration.*

---

## 🔌 Backend Developer Integration Guide

To connect the real Edge AI data to this dashboard, your backend must expose a **WebSocket Endpoint** (e.g., `ws://localhost:8080/stream`) that pushes JSON telemetry packets.

### Step 1: Format the JSON Payload (The Data Contract)

Your WebSocket server needs to push data precisely in the following JSON structure. You can push a single object update or an array of objects.

```json
{
  "device_id": "DEV-001",
  "timestamp": "2023-10-27T10:00:00Z",
  "status": "active", 
  "metrics": {
    "people_count": 142,
    "crowd_density": 0.45,
    "threshold": 0.75
  },
  "location_label": "North Gate Area"
}
```

**Important Field Constraints:**
* `status` (string): MUST be exactly one of: `"active"`, `"obscured"`, `"offline"`, or `"uncertain"`.
* `crowd_density` (float): Measured as people per square meter.
* `threshold` (float): Range `0.0` to `1.0`. Represents the Risk of Crush index (Critical State is `>= 0.8`).

### Step 2: Connect the Frontend

Once the WebSocket endpoint is running locally or on a server, follow these steps to hook it up:

1. Open `src/App.tsx`.
2. Swap the simulator hook for the production stream hook.

**Change from:**
```tsx
import { useTelemetrySimulator } from './hooks/useTelemetrySimulator';
// import { useTelemetryStream } from './hooks/useTelemetryStream';

function App() {
  const { devices, logs, packets } = useTelemetrySimulator();
```

**Change to:**
```tsx
// import { useTelemetrySimulator } from './hooks/useTelemetrySimulator';
import { useTelemetryStream } from './hooks/useTelemetryStream';

function App() {
  // Replace this URL with the actual backend WebSocket URL
  const { devices, logs, packets } = useTelemetryStream('ws://localhost:8080/stream');
```

