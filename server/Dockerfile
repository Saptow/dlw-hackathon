FROM golang:1.24-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/ws-backend .

FROM alpine:3.20

WORKDIR /app

COPY --from=builder /out/ws-backend /app/ws-backend

EXPOSE 8080

CMD ["/app/ws-backend"]