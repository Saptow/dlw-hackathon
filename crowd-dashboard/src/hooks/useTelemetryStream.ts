import { useState, useEffect, useRef } from 'react';
import type { TelemetryData, LogEntry, LogEventType, Packet } from '../types';

export function useTelemetryStream(websocketUrl: string) {
    const [state, setState] = useState<{
        data: Record<string, TelemetryData>;
        logs: LogEntry[];
        packets: Packet[];
        isConnected: boolean;
    }>({
        data: {}, // Starts empty until the backend sends the initial state
        logs: [],
        packets: [],
        isConnected: false,
    });

    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        // 1. Establish the WebSocket connection
        const ws = new WebSocket(websocketUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            console.log('Connected to Telemetry Stream');
            setState(prev => ({ ...prev, isConnected: true }));
        };

        ws.onclose = () => {
            console.log('Disconnected from Telemetry Stream');
            setState(prev => ({ ...prev, isConnected: false }));
            // NOTE: You can add reconnection logic here (e.g., using setTimeout to retry connection)
        };

        // 2. Listen for incoming messages from your backend
        ws.onmessage = (event) => {
            try {
                // Parse the incoming data constraint (could be a single object or an array of updates)
                const rawData = JSON.parse(event.data);
                const incomingUpdates: TelemetryData[] = Array.isArray(rawData) ? rawData : [rawData];

                setState(prevState => {
                    const nextData = { ...prevState.data };
                    const newLogs = [...prevState.logs];
                    const newPackets = [...prevState.packets];

                    for (const incomingData of incomingUpdates) {
                        const oldDeviceState = nextData[incomingData.device_id];
                        let logType: LogEventType = 'UPDATE';
                        let message = 'Routine telemetry packet received';

                        // Deduce state change events
                        if (oldDeviceState && oldDeviceState.status !== incomingData.status) {
                            logType = 'STATUS_CHANGE';
                            message = `Signal degraded: Device changed to ${incomingData.status.toUpperCase()}`;
                            if (incomingData.status === 'active') {
                                message = `Connection re-established: Device ACTIVE`;
                            }
                        }

                        // Deduce critical crowd crush risk events
                        if (incomingData.status === "active" && incomingData.metrics.threshold >= 0.8) {
                            logType = 'CRITICAL_ALERT';
                            message = `Crush risk critical (${(incomingData.metrics.threshold * 100).toFixed(1)}%) at ${incomingData.metrics.crowd_density.toFixed(2)} ppl/m²`;
                        }

                        // Update Activity Logs
                        newLogs.unshift({
                            id: Math.random().toString(36).substring(2, 9),
                            timestamp: incomingData.timestamp,
                            device_id: incomingData.device_id,
                            event_type: logType,
                            message
                        });

                        // Update Raw Packet Stream
                        if (incomingData.status === "active" || incomingData.status === "uncertain" || incomingData.status === "obscured") {
                            newPackets.unshift({
                                id: Math.random().toString(36).substring(2, 9),
                                timestamp: incomingData.timestamp,
                                device_id: incomingData.device_id,
                                payload: {
                                    people_count: incomingData.metrics.people_count,
                                    crowd_density: incomingData.metrics.crowd_density,
                                    threshold: incomingData.metrics.threshold
                                }
                            });
                        }

                        // Finally, update the central device state
                        nextData[incomingData.device_id] = incomingData;
                    }

                    // Return the new state, capping history lists to the 100 most recent items to preserve memory
                    return {
                        ...prevState,
                        data: nextData,
                        logs: newLogs.slice(0, 100),
                        packets: newPackets.slice(0, 100)
                    };
                });

            } catch (err) {
                console.error("Failed to parse incoming telemetry packet:", err);
            }
        };

        // 3. Cleanup connection when the component unmounts
        return () => {
            ws.close();
        };
    }, [websocketUrl]);

    return {
        devices: Object.values(state.data),
        logs: state.logs,
        packets: state.packets,
        isConnected: state.isConnected
    };
}
