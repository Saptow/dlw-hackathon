import { useState, useEffect, useRef } from 'react';
import type { TelemetryData, LogEntry, Packet } from '../types';

// The exact device IDs from the original mock data
const DEVICES = [
    { id: "DEV-CAM-004", label: "Platform 2 (East)" },
    { id: "DEV-MOCK-001", label: "Turnstiles" },
    { id: "DEV-MOCK-002", label: "Concourse" },
    { id: "DEV-MOCK-003", label: "Platform 1 (West)" }
];

export function usePresentationSimulator(globalThreshold: number) {
    const [state, setState] = useState<{
        data: Record<string, TelemetryData>;
        logs: LogEntry[];
        packets: Packet[];
    }>({
        data: {},
        logs: [],
        packets: []
    });

    const startTime = useRef<number>(Date.now());

    useEffect(() => {
        // Reset start time on mount/refresh
        startTime.current = Date.now();

        const interval = setInterval(() => {
            const elapsedSeconds = (Date.now() - startTime.current) / 1000;

            // Loop the 75 second presentation (1m 15s)
            const cycleTime = elapsedSeconds % 75;

            setState(prevState => {
                const updatedData: Record<string, TelemetryData> = { ...prevState.data };
                const newLogs = [...prevState.logs];
                const newPackets = [...prevState.packets];

                DEVICES.forEach(({ id, label }) => {
                    let targetDensity = 0.15; // Default low baseline everywhere

                    if (id === "DEV-MOCK-003") { // Platform 1 (West) gets the spikes
                        if (cycleTime >= 30 && cycleTime <= 50) {
                            // First spike around 40s
                            // Ramp up from 30s to 40s, down from 40s to 50s
                            const peakIntensity = 1 - (Math.abs(cycleTime - 40) / 10);
                            targetDensity = 0.15 + (0.7 * peakIntensity);
                        } else if (cycleTime >= 60 && cycleTime <= 75) {
                            // Second bigger spike around 70s
                            // Ramp up from 60s to 70s, sharp drop off after 70s
                            const peakIntensity = cycleTime <= 70
                                ? 1 - (Math.abs(cycleTime - 70) / 10)
                                : Math.max(0, 1 - ((cycleTime - 70) / 5));

                            targetDensity = 0.15 + (0.8 * peakIntensity);
                        }
                    }

                    // Add some random noise to the target density
                    const noise = (Math.random() - 0.5) * 0.05;
                    const currentDensity = Math.max(0, targetDensity + noise);

                    // Convert density to people count (assuming roughly 200m2 area)
                    const peopleCount = Math.round(currentDensity * 200);

                    const baseRisk = currentDensity / 1.5;
                    const volatility = (Math.random() * 0.15) - 0.05; // Random fluctuation
                    const threshold = Math.min(1.0, Math.max(0, baseRisk + volatility));

                    const newData: TelemetryData = {
                        device_id: id,
                        timestamp: new Date().toISOString(),
                        location_label: label,
                        status: "active",
                        metrics: {
                            people_count: peopleCount,
                            crowd_density: currentDensity,
                            threshold: threshold
                        }
                    };

                    const oldDeviceState = updatedData[id];
                    let logType: LogEntry['event_type'] = 'UPDATE';
                    let message = 'Routine telemetry packet received';

                    // // Log critical alerts if it crosses the threshold
                    // if (currentDensity >= globalThreshold && (!oldDeviceState || oldDeviceState.metrics.crowd_density < globalThreshold)) {
                    //     logType = 'CRITICAL_ALERT';
                    //     message = `Crush risk critical (${(globalThreshold * 100).toFixed(0)}%) rapidly exceeded on ${label}`;
                    // } else if (currentDensity < globalThreshold && oldDeviceState && oldDeviceState.metrics.crowd_density >= globalThreshold) {
                    //     logType = 'STATUS_CHANGE';
                    //     message = `Crowd dispersing on ${label}. Risk below threshold.`;
                    // }


                    if (logType !== 'UPDATE' || Math.random() > 0.8) { // Only log mundane updates 20% of the time to avoid spam
                        newLogs.unshift({
                            id: Math.random().toString(36).substring(2, 9),
                            timestamp: newData.timestamp,
                            device_id: id,
                            event_type: logType,
                            message
                        });
                    }

                    newPackets.unshift({
                        id: Math.random().toString(36).substring(2, 9),
                        timestamp: newData.timestamp,
                        device_id: id,
                        payload: {
                            people_count: newData.metrics.people_count,
                            crowd_density: newData.metrics.crowd_density,
                            threshold: newData.metrics.threshold
                        }
                    });

                    updatedData[id] = newData;
                });

                return {
                    data: updatedData,
                    logs: newLogs.slice(0, 100),
                    packets: newPackets.slice(0, 100)
                };
            });

        }, 1000); // Update every 1 second

        return () => clearInterval(interval);
    }, [globalThreshold]);

    return {
        devices: Object.values(state.data),
        logs: state.logs,
        packets: state.packets,
        isConnected: true // Always true for local sim
    };
}
