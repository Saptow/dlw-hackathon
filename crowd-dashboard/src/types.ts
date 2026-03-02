export type DeviceStatus = "active" | "obscured" | "offline" | "uncertain";

export interface TelemetryData {
    device_id: string;
    timestamp: string; // ISO8601
    status: DeviceStatus;
    metrics: {
        people_count: number;
        crowd_density: number; // 0-1 float
        threshold: number; // 0-1 float
    };
    location_label: string;
}

export type LogEventType = 'UPDATE' | 'STATUS_CHANGE' | 'CRITICAL_ALERT';

export interface LogEntry {
    id: string;
    timestamp: string;
    device_id: string;
    event_type: LogEventType;
    message: string;
}

export interface Packet {
    id: string;
    timestamp: string;
    device_id: string;
    payload: {
        people_count: number;
        crowd_density: number;
        threshold: number;
    };
}
