# Vivi with Docker Compose

Docker is an alternative to the native Windows/Linux launchers. Use one hosting
method per bot token; the Windows tray manages only a native process it launches.
Docker Desktop must use Linux containers on Windows.

1. Install Docker Engine + Compose on Linux, or Docker Desktop on Windows.
2. Copy .env.example to a private .env if needed. Configure your Discord token and
   optional providers there. Do not upload .env to GitHub.
3. Run from the repository:

   ```sh
   docker compose up --build -d
   docker compose logs -f vivi
   docker compose ps
   ```

The image includes Python 3.12, FFmpeg, Opus and the Discord voice dependencies.
The application runs as non-root UID 10001. A named volume persists data, timers,
configuration history, scheduled backups and transcripts. Image build context
excludes .env, .git, data, virtual environments and tests. No bot token is baked
into image layers. Environment variables are injected at runtime by Compose.

The dashboard remains **disabled** unless configured in .env. When enabled, the
container listener is explicitly allowed to bind its internal interface, while
Compose publishes it only on host **127.0.0.1:8765**. The OAuth redirect stays
`http://127.0.0.1:8765/callback`. This is a local dashboard, not a public website.
Do not change the host port binding to all interfaces. Explicit container mode
is required for the internal bind; native deployments still reject external binds.

For a local AI server running on the host, 127.0.0.1 inside Docker means the
container, not your host. On Docker Desktop use an appropriate host.docker.internal
API URL. On Linux configure a reachable host/model service deliberately, or add an
authorized host-gateway mapping. Model setup is separate from this bot. Voice needs
normal outbound Discord voice connectivity; no inbound voice port is published.

## Status, stopping and updating

```sh
docker compose logs --tail=100 vivi
docker compose stop vivi
docker compose up --build -d
# Remove containers/network but retain bot data:
docker compose down
```

Do not use `down -v` unless you intend to delete the named data volume. Preserve
private backups before moving a deployment. Configuration JSON backups do not
contain the complete database or transcripts. Existing host data is not imported
automatically; volume migration should preserve permissions for UID 10001.

HEALTHCHECK reads a credential-free heartbeat: it is healthy only after Discord
is ready and a fresh scheduler heartbeat is present. A missing token stops with
a clear configuration error rather than reporting healthy. The native supervisor
retries transient crashes; Compose additionally allows up to five retries of
unexpected container failures. Health status alone does not trigger a restart,
and this policy does not guarantee startup after a host reboot. Use your host's
Docker/service startup configuration for that behavior.

## Build proxies

A normal public build requires no extra flags. For a managed build proxy with a
custom CA, the Dockerfile accepts an optional BuildKit secret named proxy_ca:

```sh
docker build --secret id=proxy_ca,src=/path/to/combined-ca-bundle.crt -t vivi .
```

The bundle is mounted only for package installation, with verification enabled;
it is not copied into the final image. Runtime proxy trust, if needed on your host,
should likewise use a read-only CA mount and supported SSL_CERT_FILE configuration.
Do not put proxy credentials into the Dockerfile or disable TLS verification.

The optional webhook receiver uses a separate port, 8766, also published only on
host loopback. Expose only its /hooks/ route through your own HTTPS reverse proxy.
For full-data encryption in Docker, mount your key read-only **outside /app** (for
example /run/vivi-key) and set BACKUP_KEY_FILE to that path. Do not bake keys into
the image. See [ADVANCED.md](ADVANCED.md).

Generate backup keys on the host and mount them read-only; a key generated only
in a container’s writable layer will be lost when that container is replaced.
Restore into a writable separate directory (for example /tmp/restored-vivi),
then copy/inspect that data before removing the container.
