import { useState, useEffect, useRef } from 'react';
import type { TelemetryData, DeviceStatus, LogEntry, LogEventType, Packet } from '../types';

const LOCATIONS = [
    { label: "Platform 1 (West)", area: 300 },
    { label: "Platform 2 (East)", area: 600 },
    { label: "Concourse", area: 150 },
    { label: "Turnstiles", area: 200 },
];

const INITIAL_DEVICES: TelemetryData[] = LOCATIONS.map((loc, i) => {
    const people = Math.floor(Math.random() * 200);
    const crowd_density = people / loc.area;
    return {
        device_id: `DEV-00${i + 1}`,
        timestamp: new Date().toISOString(),
        status: "active",
        metrics: {
            people_count: people,
            crowd_density: crowd_density,
            threshold: Math.min(1.0, (crowd_density / 2.5) + (Math.random() * 0.1)), // Simulated risk index
        },
        location_label: loc.label,
    };
});

export function useTelemetrySimulator() {
    const [state, setState] = useState<{
        data: Record<string, TelemetryData>;
        logs: LogEntry[];
        packets: Packet[];
    }>(() => {
        const initialPackets = INITIAL_DEVICES.map(d => ({
            id: Math.random().toString(36).substring(2, 9),
            timestamp: d.timestamp,
            device_id: d.device_id,
            payload: {
                people_count: d.metrics.people_count,
                crowd_density: d.metrics.crowd_density,
                threshold: d.metrics.threshold
            }
        }));

        return {
            data: Object.fromEntries(INITIAL_DEVICES.map(d => [d.device_id, d])),
            logs: [],
            packets: initialPackets
        };
    });

    // Keep state in a ref for the interval to avoid stale closures,
    // which also avoids React strict mode double-invocation impurity issues
    const stateRef = useRef(state);

    useEffect(() => {
        stateRef.current = state;
    }, [state]);

    useEffect(() => {
        const interval = setInterval(() => {
            const prevState = stateRef.current;
            const nextData = { ...prevState.data };
            const newLogs: LogEntry[] = [];
            const newPackets: Packet[] = [];
            const keys = Object.keys(nextData);

            // Update 1-4 devices every tick
            const countToUpdate = Math.floor(Math.random() * 4) + 1;

            for (let i = 0; i < countToUpdate; i++) {
                const key = keys[Math.floor(Math.random() * keys.length)];
                const device = nextData[key];

                let newStatus = device.status;
                let logType: LogEventType = 'UPDATE';
                let message = 'Routine telemetry packet received';

                // ~5% chance to change status
                if (newStatus === "active" && Math.random() > 0.95) {
                    const statuses: DeviceStatus[] = ["obscured", "offline", "uncertain"];
                    newStatus = statuses[Math.floor(Math.random() * statuses.length)];
                    logType = 'STATUS_CHANGE';
                    message = `Signal degraded: Device changed to ${newStatus.toUpperCase()}`;
                } else if (newStatus !== "active" && Math.random() > 0.2) {
                    newStatus = "active";
                    logType = 'STATUS_CHANGE';
                    message = `Connection re-established: Device ACTIVE`;
                }

                let { people_count, crowd_density, threshold } = device.metrics;

                if (newStatus === "active" || newStatus === "uncertain" || newStatus === "obscured") {
                    const countChange = Math.floor(Math.random() * 31) - 15;
                    people_count = Math.max(0, people_count + countChange);

                    // Find the area for this device
                    const area = LOCATIONS.find(l => l.label === device.location_label)?.area || 300;
                    crowd_density = people_count / area;

                    // Dynamic threshold (Risk of Crush): heavily influenced by density (e.g., >2.5 ppl/m2 is critical)
                    const baseRisk = crowd_density / 2.5;
                    const volatility = (Math.random() * 0.15) - 0.05; // Random fluctuation
                    threshold = Math.min(1.0, Math.max(0, baseRisk + volatility));
                }

                if (newStatus === "active" && threshold > 0.8) {
                    logType = 'CRITICAL_ALERT';
                    message = `Crush risk critical (${(threshold * 100).toFixed(1)}%) at ${crowd_density.toFixed(2)} ppl/m²`;
                }

                const timestamp = new Date().toISOString();

                newLogs.push({
                    id: Math.random().toString(36).substring(2, 9),
                    timestamp,
                    device_id: device.device_id,
                    event_type: logType,
                    message
                });

                if (newStatus === "active" || newStatus === "uncertain" || newStatus === "obscured") {
                    newPackets.push({
                        id: Math.random().toString(36).substring(2, 9),
                        timestamp,
                        device_id: device.device_id,
                        payload: {
                            people_count,
                            crowd_density,
                            threshold
                        }
                    });
                }

                nextData[key] = {
                    ...device,
                    timestamp,
                    status: newStatus,
                    metrics: {
                        people_count,
                        crowd_density,
                        threshold
                    }
                };
            }

            setState({
                data: nextData,
                logs: [...newLogs, ...prevState.logs].slice(0, 100),
                packets: [...newPackets, ...prevState.packets].slice(0, 100)
            });

        }, 1500);

        return () => clearInterval(interval);
    }, []);

    return {
        devices: Object.values(state.data),
        logs: state.logs,
        packets: state.packets
    };
}
