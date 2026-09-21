FROM golang:1.24-alpine AS build
ARG COMPONENT=operator
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/service ./cmd/${COMPONENT}

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/service /service
USER 65532:65532
ENTRYPOINT ["/service"]
