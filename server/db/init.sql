CREATE TABLE IF NOT EXISTS device_locations (
    device_id TEXT PRIMARY KEY,
    location_label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crowd_updates (
    id BIGSERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    people_count INTEGER NOT NULL CHECK (people_count >= 0),
    crowd_density DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    location_label TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE crowd_updates
    DROP CONSTRAINT IF EXISTS crowd_updates_device_fk;

ALTER TABLE crowd_updates
    ADD CONSTRAINT crowd_updates_device_fk
    FOREIGN KEY (device_id)
    REFERENCES device_locations(device_id);

CREATE OR REPLACE FUNCTION notify_crowd_update()
RETURNS TRIGGER AS $$
DECLARE
    payload JSON;
BEGIN
    payload := json_build_object(
        'device_id', NEW.device_id,
        'timestamp', to_char(NEW.event_timestamp AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
        'status', NEW.status,
        'metrics', json_build_object(
            'people_count', NEW.people_count,
            'crowd_density', NEW.crowd_density,
            'threshold', NEW.threshold
        ),
        'location_label', NEW.location_label
    );

    PERFORM pg_notify('crowd_updates_channel', payload::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS crowd_updates_notify_trigger ON crowd_updates;

CREATE TRIGGER crowd_updates_notify_trigger
AFTER INSERT ON crowd_updates
FOR EACH ROW
EXECUTE FUNCTION notify_crowd_update();