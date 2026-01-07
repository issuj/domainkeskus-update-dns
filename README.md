# Domainkeskus DNS update script

A script that can be run on Edgerouter X, updates a DNS record on my provider who doesn't have anything resembling an API for dynamic dns.

Made by AI: I captured http interactions using browser and let Claude Sonnet 4.5 write the script based on those.

I also needed to install a missing root CA on my Edgerouter X for this to actually work, Google's AI was very helpful in figuring out which one I needed.

Also, I had GPT-OSS-120b to scrub my personal domain name and account info out of the scripts, and slop together the rest of this README below. It didn't know how to actually cron things on Edgerouter, googling "edgerouter x task-scheduler" should find you some proper examples.

---

A tiny, self‑contained utility for updating **A** and **AAAA** DNS records on the **Domainkeskus** hosting service.  It is written for **Python 2.7** so it can run directly on a Ubiquiti EdgeRouter X without any additional packages.

---

## What it does

* Logs in to the Domainkeskus control panel using the supplied credentials.
* Retrieves a one‑time SSO token.
* Pulls the current DNS zone via the Euronic DNS API.
* Replaces the **A** (IPv4) and **AAAA** (IPv6) records for a single host with the values you provide.
* Posts the updated zone back to the API.

The script can be invoked directly from the command line or via the thin wrapper shell script `domainkeskus-update-dns.sh` that automatically discovers the router’s current IPv4/IPv6 addresses.

---

## Prerequisites

* **Python 2.7** (the EdgeRouter X ships with this version by default).
* Network connectivity to `old.domainkeskus.com` and `dnsaccess.euronic.fi`.
* A Domainkeskus account with permission to edit the target domain.

---

## Configuration

All sensitive values are read from **environment variables** – never hard‑coded in the source.  Set the following before running the script (or edit `domainkeskus-update-dns.sh` and replace the placeholder values):

| Variable | Description |
|----------|-------------|
| `USERNAME` | Your Domainkeskus login name |
| `PASSWORD` | Your Domainkeskus password |
| `DOMAIN_SLD` | Second‑level domain (e.g. `example` for `example.com`) |
| `DOMAIN_TLD` | Top‑level domain (e.g. `com`) |
| `TARGET_HOST` | The host/sub‑domain you want to update (e.g. `www` or `home`) |

Example (bash):
```bash
export USERNAME=myuser
export PASSWORD='mySecretPass'
export DOMAIN_SLD=example
export DOMAIN_TLD=com
export TARGET_HOST=www
```

---

## Usage

### 1. Direct Python invocation
```bash
python domainkeskus-update-dns.py <new_ipv4> <new_ipv6>
```
Replace `<new_ipv4>` and `<new_ipv6>` with the addresses you want the host to resolve to.

### 2. Using the wrapper script (recommended on the router)
The wrapper automatically discovers the router’s current global IPv4 and IPv6 addresses and passes them to the Python script.
```bash
./domainkeskus-update-dns.sh
```
Make sure the script is executable:
```bash
chmod +x domainkeskus-update-dns.sh
```

---

## Example
```bash
# Set the required environment variables (once per session)
export USERNAME=jdoe
export PASSWORD='s3cr3t!'
export DOMAIN_SLD=mydomain
export DOMAIN_TLD=net
export TARGET_HOST=home

# Run the wrapper – it will pull the current IPs from eth0 and update DNS
./domainkeskus-update-dns.sh
```
If the DNS already contains the supplied addresses, the script will exit early with a message indicating that no update is needed.
