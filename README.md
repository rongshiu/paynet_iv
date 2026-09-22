# Credit Card Transactions — PySpark Assessment

A reproducible PySpark analysis of a messy, nested credit-card transaction feed: ingestion,
JSON flattening, data-quality handling, PII protection, and visual analysis — all in one
notebook, running in a container so it behaves the same everywhere.

**The deliverable is [`notebooks/01_credit_card_transactions.ipynb`](notebooks/01_credit_card_transactions.ipynb).**

---

## Quick start

You need **Docker Desktop** running. Nothing else — no Java, no Python, no Spark on the host.

```bash
# 1. Build the image (first run pulls ~500 MB and takes a few minutes)
docker compose build

# 2. Generate a sample dataset, if you do not have the Kaggle file yet
docker compose run --rm notebook python scripts/generate_sample_data.py --rows 40000

# 3. Start JupyterLab
docker compose up
```

Then open **<http://localhost:8888/lab?token=paynet>** and run
`notebooks/01_credit_card_transactions.ipynb` top to bottom
(**Run ▸ Restart Kernel and Run All Cells**). It takes about two to three minutes.

Stop it with `Ctrl-C`, then `docker compose down`.

| URL | What it is |
|---|---|
| <http://localhost:8888/lab?token=paynet> | JupyterLab |
| <http://localhost:4040> | Spark UI — only live while the notebook holds a session |

---

## Running it from VS Code instead

If you would rather stay in the editor than use the browser:

1. Install the **Dev Containers** extension (`ms-vscode-remote.remote-containers`), plus
   **Python** and **Jupyter**.
2. `docker compose up -d`
3. Command Palette (`Cmd-Shift-P`) → **Dev Containers: Attach to Running Container** →
   `paynet-iv-notebook`.
4. Open the notebook in that window and pick the **Python 3.11** kernel.

Or keep the container as a plain kernel server: open the notebook locally, click
**Select Kernel ▸ Existing Jupyter Server**, and enter
`http://localhost:8888/?token=paynet`.

> Running the notebook against a **local** Python interpreter will not work unless you have a
> JDK 17 installed — PySpark needs a JVM. That is the problem the container removes.

---

## Getting the real data

The notebook reads `data/raw/transactions.json`. Anything in `data/` is gitignored — transaction
data does not belong in a repository, synthetic or not.

**Option A — Kaggle (the real thing).** Download the credit-card transactions dataset on the host,
from the Kaggle website or the `kaggle` CLI, and put the JSON at `data/raw/transactions.json`. The
bind mount makes it visible to the container immediately — no rebuild, no restart.

Downloading from *inside* the container is deliberately not wired up: it would mean carrying a
Kaggle client in the image and mounting your API credentials into it, which is a lot of standing
machinery for a file you fetch once.

**Option B — the generator (works offline).**

```bash
docker compose run --rm notebook python scripts/generate_sample_data.py --rows 40000
```

This writes a synthetic file with the **same nested shape and the same families of defects** the
brief describes: five different timestamp encodings, malformed `person_name` values, currency
strings in `amt`, inconsistent casing, out-of-range coordinates, duplicate transactions, and two
lines that are not valid JSON at all. The fraud label is synthetic but not random — it is driven by
hour, category, amount, cardholder age, distance, and merchant tenure, so the analysis has something
real to find.

The notebook does not care which file it gets. The flattening step resolves columns by **leaf name**,
so it adapts to a different nesting layout without edits.

---

## What the notebook covers

| § | Content |
|---|---|
| 1 | **Ingestion** — two-pass read: infer the *structure*, discard the *types*, re-read with every leaf as `string`. Unparseable lines quarantined via `_corrupt_record`. |
| 2 | **JSON flattening** — a generic recursive struct expander, mapped to the 26 required columns by leaf name. |
| 3 | **Profiling** — null/blank/token-missing rates, cardinality, off-pattern value samples. |
| 4 | **Cleaning & data quality** — ~40 named rules, each producing a typed value *and* a flag. Includes the **timestamp conversion to UTC+8** (§4.1) and the **`person_name` derivation** (§4.2). |
| 5 | **PII handling** — in-place masking/tokenisation and a bronze/silver/gold layering, with the 26-column schema contract verified and a measured re-identification check. |
| 6 | **Feature engineering** — haversine distance, local hour/day, merchant tenure, in-category amount z-score. |
| 7 | **Visualisation** — six figures, each with its rationale, its table, and what it means. |
| 8–9 | Parquet outputs, findings, and limitations. |

### Three decisions worth knowing before you read it

**Nothing is silently dropped.** Failing rows are tagged with the rule they broke and routed to a
quarantine table. The quarantine is an output, not a side effect.

**Types are never inferred.** Schema inference on dirty data means Spark decides what to null out
and does not tell you. Every cast here is explicit and has a named failure branch.

**PII is layered, not hashed once.** `sha2(cc_num)` is *not* protection — a 16-digit card with a
known BIN and a Luhn-constrained check digit is about 10⁹ candidates, which a GPU enumerates in
seconds. The notebook uses a keyed HMAC whose secret never touches the data, and separately
generalises the quasi-identifiers (ZIP + date of birth + gender uniquely identifies most of the US
population, so tokenising the name alone achieves nothing).

**PII handling never deletes a column.** The brief specifies 26 output columns, so masking,
tokenisation and generalisation are all applied **in place**: `cc_num` becomes `374512******2099`,
`street` becomes `[REDACTED]`, `zip` becomes `468**`, `dob` drops to year of birth. Derived keys
(`card_token`, `customer_token`, `cc_bin6`, `zip3`, `age_band`) are added *beside* the originals,
not in place of them — a single hash over several concatenated identifiers would collapse five
columns into one opaque string, which is a loss of schema rather than a privacy control. §5.5
asserts the full 26-column contract and prints the treatment applied to each column.

---

## Layout

```
.
├── Dockerfile                  Python 3.11 + OpenJDK 17 + Spark 3.5 + JupyterLab
├── docker-compose.yml          Ports, bind mount, PII key
├── pyproject.toml              Dependencies + the local package (pinned; the
│                               Python/JDK/Spark trio is version sensitive)
├── notebooks/
│   └── 01_credit_card_transactions.ipynb     ← the deliverable
├── src/paynet_iv/
│   └── viz_theme.py            Chart theme and palette
├── scripts/
│   └── generate_sample_data.py Synthetic messy dataset
├── data/
│   ├── raw/                    Input JSON (gitignored)
│   └── curated/                Parquet outputs (gitignored)
└── output/figures/             Exported PNGs (gitignored)
```

### Outputs the notebook writes

| Path | Contents |
|---|---|
| `data/curated/curated_transactions/` | The silver layer — full 26-column schema, direct identifiers masked or tokenised, quasi-identifiers exact. |
| `data/curated/analytics_transactions/` | The gold layer — same schema, quasi-identifiers generalised, feature-engineered. Partitioned by local date. |
| `data/curated/quarantine_failed_rules/` | Rows that failed a fatal rule, with `dq_flags` attached. |
| `data/curated/quarantine_unparseable/` | Lines that were not valid JSON. |
| `data/curated/dq_rule_counts/` | Rule-hit counts — the scorecard chart's source. |
| `output/figures/*.png` | Every figure, exported. |

---

## Dependencies

Everything is declared in [`pyproject.toml`](pyproject.toml). The image installs it editable:

```dockerfile
RUN pip install -e ".[notebook]"
```

Two consequences worth knowing:

- The install is rooted at `/workspace`, which is also the bind-mount point — so editing
  `src/paynet_iv/viz_theme.py` on the host takes effect in the container on the next kernel restart,
  with no rebuild.
- The notebook imports `from paynet_iv import viz_theme`, a real package import rather than a
  `sys.path` fixup.

The `notebook` extra (JupyterLab, ipykernel) is separated from the core dependencies because the
package itself imports none of it — only running the notebook does.

To work on it outside Docker you would need a JDK 17 on `PATH`, then `pip install -e ".[notebook]"`.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PII_HMAC_KEY` | `local-dev-key-not-for-production` | Secret for tokenising card numbers, names, and transaction IDs. **Override this for anything real.** The notebook prints a warning when the default is in use. |
| `JUPYTER_TOKEN` | `paynet` | JupyterLab login token. |

```bash
PII_HMAC_KEY="$(openssl rand -hex 32)" docker compose up
```

Rotating the key changes every token, which breaks joins to previously published extracts — in
production the token column needs a version alongside it.

---

## Troubleshooting

**`Cannot connect to the Docker daemon`** — Docker Desktop is not running. Start it and wait for
the whale icon to settle.

**Port 8888 already in use** — another Jupyter is running. Either stop it, or change the mapping in
`docker-compose.yml` to `"8889:8888"`.

**`FileNotFoundError: ../data/raw/transactions.json`** — no input file yet. Run the generator (step 2
above) or drop the Kaggle JSON in `data/raw/`.

**Kernel dies during a wide aggregation** — the Spark driver ran out of heap. Raise
`spark.driver.memory` in the notebook's session builder, and give Docker Desktop more RAM under
*Settings ▸ Resources*.

**`java.net.UnknownHostException` on startup** — the container could not resolve its own hostname.
`SPARK_LOCAL_IP=127.0.0.1` is already set in the Dockerfile to prevent this; if you are running
outside compose, pass it explicitly.
