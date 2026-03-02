package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const writeWait = 10 * time.Second
const notifyChannel = "crowd_updates_channel"

type Metrics struct {
	PeopleCount  int     `json:"people_count"`
	CrowdDensity float64 `json:"crowd_density"`
	Threshold    float64 `json:"threshold"`
}

type UpdatePacket struct {
	DeviceID      string    `json:"device_id"`
	Timestamp     time.Time `json:"timestamp"`
	Status        string    `json:"status"`
	Metrics       Metrics   `json:"metrics"`
	LocationLabel string    `json:"location_label"`
}

type IncomingUpdate struct {
	DeviceID  string    `json:"device_id"`
	Timestamp time.Time `json:"timestamp"`
	Status    string    `json:"status"`
	Metrics   Metrics   `json:"metrics"`
}

type DeviceLocationRequest struct {
	DeviceID      string `json:"device_id"`
	LocationLabel string `json:"location_label"`
}

func (p UpdatePacket) Validate() error {
	if p.DeviceID == "" {
		return errors.New("device_id is required")
	}
	if p.Timestamp.IsZero() {
		return errors.New("timestamp is required")
	}
	if p.Status == "" {
		return errors.New("status is required")
	}
	if p.LocationLabel == "" {
		return errors.New("location_label is required")
	}
	if p.Metrics.PeopleCount < 0 {
		return errors.New("metrics.people_count must be >= 0")
	}
	return nil
}

func (p IncomingUpdate) Validate() error {
	if p.DeviceID == "" {
		return errors.New("device_id is required")
	}
	if p.Timestamp.IsZero() {
		return errors.New("timestamp is required")
	}
	if p.Status == "" {
		return errors.New("status is required")
	}
	if p.Metrics.PeopleCount < 0 {
		return errors.New("metrics.people_count must be >= 0")
	}
	return nil
}

func (p DeviceLocationRequest) Validate() error {
	if p.DeviceID == "" {
		return errors.New("device_id is required")
	}
	if p.LocationLabel == "" {
		return errors.New("location_label is required")
	}
	return nil
}

type Hub struct {
	mu      sync.RWMutex
	clients map[*websocket.Conn]struct{}
}

func NewHub() *Hub {
	return &Hub{clients: make(map[*websocket.Conn]struct{})}
}

func (h *Hub) Register(conn *websocket.Conn) {
	h.mu.Lock()
	h.clients[conn] = struct{}{}
	h.mu.Unlock()
}

func (h *Hub) Unregister(conn *websocket.Conn) {
	h.mu.Lock()
	delete(h.clients, conn)
	h.mu.Unlock()
	_ = conn.Close()
}

func (h *Hub) Count() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

func (h *Hub) Broadcast(packet UpdatePacket) {
	payload, err := json.Marshal(packet)
	if err != nil {
		log.Printf("failed marshaling packet: %v", err)
		return
	}

	h.mu.RLock()
	clients := make([]*websocket.Conn, 0, len(h.clients))
	for conn := range h.clients {
		clients = append(clients, conn)
	}
	h.mu.RUnlock()

	for _, conn := range clients {
		if err := conn.SetWriteDeadline(time.Now().Add(writeWait)); err != nil {
			h.Unregister(conn)
			continue
		}
		if err := conn.WriteMessage(websocket.TextMessage, payload); err != nil {
			h.Unregister(conn)
		}
	}
}

var upgrader = websocket.Upgrader{
	CheckOrigin: func(_ *http.Request) bool {
		return true
	},
}

func sendPacket(conn *websocket.Conn, packet UpdatePacket) error {
	payload, err := json.Marshal(packet)
	if err != nil {
		return err
	}

	if err := conn.SetWriteDeadline(time.Now().Add(writeWait)); err != nil {
		return err
	}

	return conn.WriteMessage(websocket.TextMessage, payload)
}

func fetchLatestPerDevice(ctx context.Context, db *pgxpool.Pool) ([]UpdatePacket, error) {
	const query = `
		SELECT
			device_id,
			event_timestamp,
			status,
			people_count,
			crowd_density,
			threshold,
			location_label
		FROM (
			SELECT DISTINCT ON (device_id)
				id,
				device_id,
				event_timestamp,
				status,
				people_count,
				crowd_density,
				threshold,
				location_label
			FROM crowd_updates
			ORDER BY device_id, event_timestamp DESC, id DESC
		) latest
		ORDER BY device_id
	`

	rows, err := db.Query(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	packets := make([]UpdatePacket, 0)
	for rows.Next() {
		var packet UpdatePacket
		if err := rows.Scan(
			&packet.DeviceID,
			&packet.Timestamp,
			&packet.Status,
			&packet.Metrics.PeopleCount,
			&packet.Metrics.CrowdDensity,
			&packet.Metrics.Threshold,
			&packet.LocationLabel,
		); err != nil {
			return nil, err
		}
		packets = append(packets, packet)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return packets, nil
}

func websocketHandler(hub *Hub, db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			log.Printf("websocket upgrade failed: %v", err)
			return
		}
		defer func() {
			_ = conn.Close()
		}()

		snapshotCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		snapshot, err := fetchLatestPerDevice(snapshotCtx, db)
		cancel()
		if err != nil {
			log.Printf("failed fetching initial websocket snapshot: %v", err)
		} else {
			for _, packet := range snapshot {
				if err := sendPacket(conn, packet); err != nil {
					log.Printf("failed sending initial websocket snapshot: %v", err)
					return
				}
			}
		}

		hub.Register(conn)
		log.Printf("websocket client connected (%d total)", hub.Count())

		defer func() {
			hub.Unregister(conn)
			log.Printf("websocket client disconnected")
		}()

		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				break
			}
		}
	}
}

func publishHandler(db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		defer r.Body.Close()

		var incoming IncomingUpdate
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&incoming); err != nil {
			http.Error(w, fmt.Sprintf("invalid JSON: %v", err), http.StatusBadRequest)
			return
		}

		if err := incoming.Validate(); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		locationLabel, err := lookupLocationLabel(r.Context(), db, incoming.DeviceID)
		if err != nil {
			if errors.Is(err, pgx.ErrNoRows) {
				http.Error(w, "unknown device_id: location mapping not found", http.StatusBadRequest)
				return
			}
			log.Printf("failed to resolve location label: %v", err)
			http.Error(w, "failed to resolve location label", http.StatusInternalServerError)
			return
		}

		packet := UpdatePacket{
			DeviceID:      incoming.DeviceID,
			Timestamp:     incoming.Timestamp,
			Status:        incoming.Status,
			Metrics:       incoming.Metrics,
			LocationLabel: locationLabel,
		}

		if err := insertUpdate(r.Context(), db, packet); err != nil {
			log.Printf("failed to persist update: %v", err)
			http.Error(w, "failed to persist update", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "stored"})
	}
}

func lookupLocationLabel(ctx context.Context, db *pgxpool.Pool, deviceID string) (string, error) {
	const query = `
		SELECT location_label
		FROM device_locations
		WHERE device_id = $1
	`

	var locationLabel string
	err := db.QueryRow(ctx, query, deviceID).Scan(&locationLabel)
	if err != nil {
		return "", err
	}

	return locationLabel, nil
}

func upsertDeviceLocation(ctx context.Context, db *pgxpool.Pool, deviceID, locationLabel string) error {
	const query = `
		INSERT INTO device_locations (device_id, location_label)
		VALUES ($1, $2)
		ON CONFLICT (device_id)
		DO UPDATE SET location_label = EXCLUDED.location_label
	`

	_, err := db.Exec(ctx, query, deviceID, locationLabel)
	return err
}

func deviceLocationHandler(db *pgxpool.Pool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}

		defer r.Body.Close()

		var payload DeviceLocationRequest
		decoder := json.NewDecoder(r.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&payload); err != nil {
			http.Error(w, fmt.Sprintf("invalid JSON: %v", err), http.StatusBadRequest)
			return
		}

		if err := payload.Validate(); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		if err := upsertDeviceLocation(r.Context(), db, payload.DeviceID, payload.LocationLabel); err != nil {
			log.Printf("failed to upsert device location: %v", err)
			http.Error(w, "failed to persist device location", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "stored"})
	}
}

func insertUpdate(ctx context.Context, db *pgxpool.Pool, packet UpdatePacket) error {
	const query = `
		INSERT INTO crowd_updates (
			device_id,
			event_timestamp,
			status,
			people_count,
			crowd_density,
			threshold,
			location_label
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`

	_, err := db.Exec(
		ctx,
		query,
		packet.DeviceID,
		packet.Timestamp,
		packet.Status,
		packet.Metrics.PeopleCount,
		packet.Metrics.CrowdDensity,
		packet.Metrics.Threshold,
		packet.LocationLabel,
	)
	return err
}

func listenForDBUpdates(ctx context.Context, dbURL string, hub *Hub) {
	for {
		if ctx.Err() != nil {
			return
		}

		conn, err := pgx.Connect(ctx, dbURL)
		if err != nil {
			log.Printf("postgres listener connect failed: %v", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(2 * time.Second):
			}
			continue
		}

		if _, err := conn.Exec(ctx, "LISTEN "+notifyChannel); err != nil {
			log.Printf("postgres LISTEN failed: %v", err)
			_ = conn.Close(ctx)
			select {
			case <-ctx.Done():
				return
			case <-time.After(2 * time.Second):
			}
			continue
		}

		log.Printf("listening for postgres notifications on channel %q", notifyChannel)

		for {
			notification, err := conn.WaitForNotification(ctx)
			if err != nil {
				if ctx.Err() != nil {
					_ = conn.Close(context.Background())
					return
				}
				log.Printf("postgres notification wait failed: %v", err)
				_ = conn.Close(context.Background())
				break
			}

			var packet UpdatePacket
			if err := json.Unmarshal([]byte(notification.Payload), &packet); err != nil {
				log.Printf("invalid notification payload: %v", err)
				continue
			}

			if err := packet.Validate(); err != nil {
				log.Printf("notification payload failed validation: %v", err)
				continue
			}

			hub.Broadcast(packet)
		}
	}
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://postgres:postgres@localhost:5432/crowd_updates?sslmode=disable"
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	dbPool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Fatalf("failed to create postgres pool: %v", err)
	}
	defer dbPool.Close()

	if err := dbPool.Ping(ctx); err != nil {
		log.Fatalf("failed to connect to postgres: %v", err)
	}

	hub := NewHub()
	go listenForDBUpdates(ctx, dbURL, hub)

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/ws", websocketHandler(hub, dbPool))
	mux.HandleFunc("/devices/location", deviceLocationHandler(dbPool))
	mux.HandleFunc("/db/push", publishHandler(dbPool))

	server := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("websocket server listening on :%s", port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server failed: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	cancel()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
	}
}
