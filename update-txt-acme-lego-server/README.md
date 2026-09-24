# ACME TXT record server for lego (httpreq)

A small HTTP server that implements the [lego `httpreq` provider](https://go-acme.github.io/lego/dns/httpreq/) in **default mode**, so lego can issue/renew certificates by managing the `_acme-challenge` TXT record on Domainkeskus.

Written for **Python 2.7** (stdlib only) so it runs on a Ubiquiti EdgeRouter X, same as `../update-a-aaaa`.

## How it works

Lego calls:

- `POST /present` with `{"fqdn": "_acme-challenge.domain.", "value": "<token>"}`
- `POST /cleanup` with the same body

The server:

1. Verifies HTTP Basic auth (mandatory).
2. Checks that the fqdn ends with the configured `DOMAIN_SLD.DOMAIN_TLD`. Anything else gets a `400`. Any subdomain part is folded into the host string (e.g. `_acme-challenge.sub`).
3. Logs in to Domainkeskus, fetches the zone, adds/replaces (present) or removes (cleanup) the TXT record, and posts the zone back — same flow as the A/AAAA script.

Returns `200` on success, `401` on bad auth, `400` on bad request, `500` on upstream API errors.

## Configuration

All via environment variables (edit `domainkeskus-acme-server.sh`):

| Variable | Description |
|----------|-------------|
| `USERNAME` / `PASSWORD` | Domainkeskus login (same as update-a-aaaa) |
| `DOMAIN_SLD` / `DOMAIN_TLD` | The domain lego is allowed to touch |
| `BIND_IP` / `BIND_PORT` | Address/port to listen on (internal side of the router) |
| `HTTP_AUTH_USERNAME` / `HTTP_AUTH_PASSWORD` | Basic auth credentials for lego (separate from the Domainkeskus login) |

## Running

```sh
./domainkeskus-acme-server.sh
```

## Running as a systemd service (non-root)

The credentials live in `domainkeskus-acme-server.sh`, so keep it readable only by the service user.

```sh
# 1. Create a dedicated system user
useradd --system --no-create-home --shell /usr/sbin/nologin acme

# 2. Copy the files to the router (adjust path if you don't use /opt)
mkdir -p /opt/domainkeskus-update-dns/update-txt-acme-lego-server
cp domainkeskus-acme-server.* /opt/domainkeskus-update-dns/update-txt-acme-lego-server/

# 3. Edit credentials/bind address in the .sh, then lock down permissions
chown -R acme:acme /opt/domainkeskus-update-dns/update-txt-acme-lego-server
chmod 700 /opt/domainkeskus-update-dns/update-txt-acme-lego-server/domainkeskus-acme-server.sh

# 4. Install the unit (adjust ExecStart if you used a different path)
cp domainkeskus-acme-server.service /etc/systemd/system/
systemctl daemon-reload

# 5. Start and enable at boot
systemctl enable --now domainkeskus-acme-server

# 6. Check
systemctl status domainkeskus-acme-server
journalctl -u domainkeskus-acme-server -f
```

## Using with lego

```sh
HTTPREQ_ENDPOINT=http://192.168.1.1:9090 \
HTTPREQ_USERNAME=lego \
HTTPREQ_PASSWORD=legopass \
lego run --dns httpreq -d mydomain.com
```

## Caveats

- The API's `host` field is assumed to accept dotted values like `_acme-challenge.sub` for subdomains — unverified, test with a real subdomain before relying on wildcard certs.
- The TXT value is stored exactly as lego sends it (no quoting). If the provider's UI shows it wrong, adjust in `present_txt()`.
