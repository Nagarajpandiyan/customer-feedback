# GNP Demo — Quick Start (Ubuntu/Linux)


## 1. Extract the ZIP and open a terminal

Extract `GNP_Demo_Complete_Source_Code_FIXED_with_Run_Guide.zip`.
In a terminal, change into the extracted project directory — the directory containing `docker-compose.yml` or `compose.yaml`.

For example (adjust the path to where you extracted it):

```bash
cd ~/Videos/GNP_Demo_IIT_Del
```

Check that the Compose file is present:

```bash
ls
```

## 2. Check Docker

```bash
docker --version
docker compose version
```

If either command is unavailable, install Docker Engine and the Docker Compose plugin using Docker's official Ubuntu instructions:
https://docs.docker.com/engine/install/ubuntu/

## 3. Build and start the application

Run these commands from the project directory:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

The first build may take several minutes because Docker downloads images and Python/Node dependencies.

## 4. Check container status and logs

```bash
docker compose ps
```

To view recent logs:

```bash
docker compose logs --tail=100
```

To follow logs live, use `docker compose logs -f` and press `Ctrl+C` to stop viewing logs (the containers keep running).

## 5. Open the application

On the same machine as Docker:

- GNP Demo UI: http://localhost:8501
- API documentation: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

If opening from another computer, replace `localhost` with the server's IP address and ensure the relevant ports are permitted by the server firewall.

## 6. Sign in

Default demo administrator:

- Username: `gnpadmin`
- Password: `GNP-IITD-2026!`

Change default credentials and configure a strong encryption key before any non-demo deployment.

## 7. Run a live collection test

1. Sign in as administrator.
2. Open **Create Collection**.
3. Select **Live API** mode.
4. Select **Hacker News** and/or **Stack Exchange**.
5. Enter a relevant search keyword and create the task.
6. Open **Feedback Explorer** and confirm that real records and source links appear.

Hacker News and Stack Exchange do not require YouTube/Reddit credentials for the included public API integrations, but their API limits and availability apply. Demo mode generates synthetic records; those are not real public customer comments.

## 8. Stop or remove the application

Stop containers but keep them:

```bash
docker compose stop
```

Stop and remove containers while preserving named data volumes:

```bash
docker compose down
```

**Do not use `docker compose down -v` unless you intentionally want to delete persistent database data.**

## 9. Troubleshooting

If a service fails:

```bash
docker compose ps -a
docker compose logs --tail=150 api collector processor
```

If the build fails while installing Python packages, check `requirements.txt` for accidental extra characters. The cryptography dependency should be exactly:

```text
cryptography==43.0.1
```

Share the output of the commands above when asking for help. The source package has had the reported dependency-line typo corrected, but you must still verify the full Docker runtime and live collection on your own server.

---

# GNP Demo — IIT Delhi Assignment

A React + FastAPI customer-feedback collection and analysis demo. It supports four source options:

- **Hacker News** — live public comments through the Algolia Search API (no API key).
- **Stack Exchange** — live public questions/answers through the Stack Exchange API (no API key; anonymous quotas apply).
- **YouTube** — live public video comments through YouTube Data API v3 (API key required).
- **Reddit** — live public comments through Reddit's OAuth API (client ID, client secret and user agent required; access and rate limits apply).

The app also has a clearly labelled **Demo** mode that generates synthetic sample records. Synthetic records are not real public comments and should not be represented as collected reviews.

## 1. Start the application

Requirements: Docker Engine and Docker Compose.

From the project directory, run:

```bash
docker compose up --build -d
```

Open **http://localhost:8501**. The main interface is React; Streamlit is not used.

To check that services started:

```bash
docker compose ps
docker compose logs -f dashboard api collector processor
```

## 2. Administrator login

- **Username:** `gnpadmin`
- **Password:** `GNP-IITD-2026!`

Use **Admin controls** to create user accounts and assign permissions. Change the default administrator password and `APP_TOKEN_SECRET` before sharing the application outside a local academic demo.

## 3. Collection modes

Open **Create collection**.

### Demo mode — no credentials

1. Select one or more sources.
2. Choose **Demo (synthetic sample data)**.
3. Enter a task name and product-related keywords.
4. Start the task.
5. Open **Feedback Explorer** to inspect the generated sample records.

Demo records are marked `demo_unverified`, have a trust score of `0`, and have no original source URL. They are synthetic examples, not real comments from the named platform.

### Live API mode — real public data

Choose **Live API (real public comments)**. Select one or more sources:

| Source | API credentials | Notes |
|---|---|---|
| Hacker News | Not required | Uses the public Algolia HN Search API. |
| Stack Exchange | Not required for basic anonymous access | Subject to API quotas and throttling. |
| YouTube | YouTube Data API v3 key | Comments may be disabled or unavailable; quota limits apply. |
| Reddit | Client ID, client secret and user agent | Requires eligible API access and compliance with Reddit's current terms and rate limits. |

For the simplest no-key live test, select **Hacker News** and **Stack Exchange** only.

## 4. How to obtain and add API credentials

You do **not** need to add credentials to the source code or commit them to Git. The application has an administrator-only credential form so that keys can be entered after installation.

### A. YouTube Data API v3 key

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a Google Cloud project.
3. Open **APIs & Services → Library**.
4. Search for **YouTube Data API v3** and enable it.
5. Open **APIs & Services → Credentials**.
6. Select **Create Credentials → API key**.
7. Copy the key. Keep it private. If possible, restrict the key to the YouTube Data API v3 and apply appropriate usage restrictions.

Official documentation: [YouTube Data API — Getting Started](https://developers.google.com/youtube/v3/getting-started).

### B. Reddit API credentials

1. Sign in to your Reddit account.
2. Review Reddit's current [Data API terms and access guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki).
3. Follow Reddit's current developer application/access process and make sure your intended academic use is permitted.
4. When Reddit makes an application available to you, obtain its **client ID** and **client secret**.
5. Use a descriptive **User Agent**, for example: `GNPFeedbackCollector/1.0 (academic project; contact: your-email@example.com)`. Replace the example contact with an address you control if appropriate.

Reddit access policies can change. Do not assume that creating an app automatically grants unrestricted API access.

### C. Enter credentials in GNP Demo

1. Start GNP Demo and sign in using the administrator account.
2. Open **Admin controls**.
3. Find **Platform API credentials**.
4. Paste the YouTube API key into **YouTube Data API v3 key**.
5. Paste the Reddit **client ID**, **client secret**, and **user agent** into their corresponding fields.
6. Click **Save API credentials**.
7. The page should show whether YouTube and Reddit credentials are configured. Secret values are not displayed back in the browser.
8. Open **Create collection**, select the relevant platform, choose **Live API**, and start a task.

You may configure only one platform. For example, a YouTube-only live task needs a YouTube key but does not need Reddit credentials. Hacker News and Stack Exchange do not need either credential.

**Why aren't API keys pre-filled in the project?** API credentials belong to the person or organization operating the collector. Hard-coding them into a shared ZIP or source repository would expose secrets, allow others to consume the owner's quota, and make credential rotation difficult. Each operator should enter their own credentials through the admin screen. Never send API keys or client secrets in chat, screenshots, reports, or source control.

## 5. Data pipeline

```text
Selected source(s)
      |
      v
Collection worker
      |
      v
Kafka (raw topic)
      |
      v
Cleaning / normalization processor
      |
      v
Kafka (cleaned topic) + PostgreSQL
      |
      v
React dashboard / Feedback Explorer / Analytics
```

## 6. Data cleaning and duplicate prevention

The processor normalizes Unicode, decodes HTML entities, strips HTML tags, replaces URLs and email addresses with placeholders, collapses excess whitespace, rejects empty text, and calculates a content hash. PostgreSQL enforces uniqueness on `(source, source_id)` to prevent duplicate imports.

## 7. Source verification and trust score

Records store the source, source ID, product keyword, comment text, source URL when available, timestamp, engagement, retrieval details, verification status and trust score.

- Synthetic records are labelled `demo_unverified` with score `0`.
- Live API records are labelled according to the provenance fields returned by the source adapter.
- A verification status or trust score indicates provenance/completeness; it does **not** prove that an opinion is truthful or that an author is genuine.

## 8. Other features

- Role-based administrator and user accounts.
- Collection task creation, pause, resume, stop and administrator-only delete.
- Input validation in the frontend and API.
- Feedback search, source filtering and CSV export.
- Overview charts and analytics.
- Prometheus-backed health and infrastructure metrics.
- Grafana monitoring.

## 9. Services

| Component | Address |
|---|---|
| Main React UI | [http://localhost:8501](http://localhost:8501) |
| FastAPI docs | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Prometheus | [http://localhost:9090](http://localhost:9090) |
| Grafana | [http://localhost:3000](http://localhost:3000) |
| PostgreSQL host port | `localhost:5433` |

## 10. Useful commands

```bash
# Check service status
docker compose ps

# Follow application logs
docker compose logs -f dashboard api collector processor

# Stop containers but retain them
docker compose stop

# Stop and remove containers; named volumes/data are retained
docker compose down
```

`docker compose down -v` deletes persistent database, Kafka, Prometheus and Grafana data. Avoid it unless you intentionally want to reset the demo.

## 11. Security and operational notes

- Do not commit API keys, Reddit secrets, passwords or private `.env` files to source control.
- The local Compose configuration supplies a demo encryption key shared by the API and collector so that saved platform credentials can be encrypted in PostgreSQL and decrypted by the collector. For deployment beyond a local academic demo, set a private `APP_ENCRYPTION_KEY` (a valid Fernet key) securely for **both** the `api` and `collector` services. Back it up securely. Losing or changing the key makes previously stored credentials unreadable; re-enter credentials after rotating it.
- Change default admin credentials and token secrets before external deployment.
- Respect platform terms, privacy requirements, rate limits, data retention rules and API quotas.
- Public API availability and access permissions can change. A live collection task may return fewer records than requested, including zero, if matching public comments are unavailable or comments are disabled.

## 12. Validation status and assignment disclosure

The project source and Docker Compose configuration should be validated on the machine where it will be demonstrated. Static syntax/configuration checks are not the same as a full Docker runtime test. Run a small live task and verify that actual records appear in **Feedback Explorer** and PostgreSQL before claiming that live collection was demonstrated.

For the assignment, clearly distinguish:
- **Live API records:** genuinely retrieved from the selected public source.
- **Demo records:** synthetic examples used to demonstrate the pipeline.

Do not describe synthetic records as real YouTube, Reddit, Hacker News or Stack Exchange comments.
