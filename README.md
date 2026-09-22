# Credit Card Transactions — PySpark Assessment

A reproducible PySpark analysis of a messy, doubly-nested credit-card transaction feed: ingestion,
JSON flattening, data-quality handling, PII protection, and visual analysis — all in one notebook,
running in a container so it behaves the same everywhere.

**The deliverable is [`notebooks/01_credit_card_transactions.ipynb`](notebooks/01_credit_card_transactions.ipynb).**

The committed outputs were produced on the assessment's own dataset —
[`jinquan/cc-sample-data`](https://www.kaggle.com/datasets/jinquan/cc-sample-data), 1,296,675 rows
and 967 MB of newline-delimited JSON. The data itself is **not** in this repository and never will
be: `data/` is gitignored in full, because a feed carrying card numbers, names and street addresses
does not belong in version control. See [Getting the data](#getting-the-data).

---

## Quick start

You need **Docker Desktop** running, the dataset in `data/raw/`, and a tokenisation key. Nothing
else — no Java, no Python, no Spark on the host.

```bash
# 1. Build the image (first run pulls ~500 MB and takes a few minutes)
docker compose build

# 2. Put the data in place — see "Getting the data" below
#    -> data/raw/transactions.json

# 3. Start JupyterLab with a PII tokenisation key
PII_HMAC_KEY="$(openssl rand -hex 32)" docker compose up
```

Then open **<http://localhost:8888/lab?token=paynet>** and run
`notebooks/01_credit_card_transactions.ipynb` top to bottom
(**Run ▸ Restart Kernel and Run All Cells**).

Stop it with `Ctrl-C`, then `docker compose down`.

| URL | What it is |
|---|---|
| <http://localhost:8888/lab?token=paynet> | JupyterLab |
| <http://localhost:4040> | Spark UI — only live while the notebook holds a session |

> **`PII_HMAC_KEY` has no default and the notebook will not start without one.** That is
> deliberate. Card numbers are tokenised with a keyed HMAC, and a key committed to a public
> repository is not a key — it makes every token reversible by anyone holding the repo. The
> notebook rejects a missing key, a known placeholder, or anything under 32 characters.
> In production this comes from a secret store, not from `openssl` on the command line.
>
> Rotating the key changes every token, which breaks joins to previously published extracts — in
> production the token column needs a version alongside it.

---

<a name="getting-the-data"></a>

## Getting the data

The notebook reads `data/raw/transactions.json`.

```bash
pip install kagglehub
python -c "import kagglehub, shutil, pathlib; \
  p = kagglehub.dataset_download('jinquan/cc-sample-data'); \
  shutil.copy(pathlib.Path(p)/'cc_sample_transaction.json', 'data/raw/transactions.json')"
```

Or download it from the [dataset page](https://www.kaggle.com/datasets/jinquan/cc-sample-data) and
unzip `cc_sample_transaction.json` to `data/raw/transactions.json`. The bind mount makes it visible
to the container immediately — no rebuild, no restart.

Downloading from *inside* the container is deliberately not wired up: it would mean carrying a
Kaggle client in the image and mounting API credentials into it, which is a lot of standing
machinery for a file you fetch once.

### Running it from VS Code instead

1. Install the **Dev Containers** extension (`ms-vscode-remote.remote-containers`), plus
   **Python** and **Jupyter**.
2. `PII_HMAC_KEY="$(openssl rand -hex 32)" docker compose up -d`
3. Command Palette (`Cmd-Shift-P`) → **Dev Containers: Attach to Running Container** →
   `paynet-iv-notebook`.
4. Open the notebook in that window and pick the **Python 3.11** kernel.

> Running the notebook against a **local** Python interpreter will not work unless you have a
> JDK 17 installed — PySpark needs a JVM. That is the problem the container removes.

---

## Three things about this file that are not in the column list

These shape most of the notebook, and none of them is visible from the schema.

**1. The nesting is doubly encoded.** `personal_detail` is not a nested object — it is a *string*
containing JSON, and `address` inside it is a second escaped JSON string inside that:

```json
"personal_detail": "{\"person_name\":\"Jennifer,Banks,eeeee\", ...,
                     \"address\":\"{\\\"street\\\":\\\"561 Perry Cove\\\", ...}\"}"
```

A struct flattener alone recovers nothing. §2 alternates struct expansion with `from_json` parsing
of string columns whose contents look like objects, repeating until a pass changes nothing.

**2. The three time columns use three different units.** `trans_date_trans_time` is a naive datetime
string with no offset at all; `merch_eff_time` is epoch **microseconds**; `merch_last_update_time`
is epoch **milliseconds**. About a tenth of both merchant columns is digit-truncated and is not a
valid instant under any unit. §4.1 infers the unit by **magnitude** — divide by each candidate and
keep the quotient that lands in a plausible window — rather than by digit count, which is wrong on
this file in both directions.

**3. `person_name` uses four separators.** `,`, `@`, `|` and `/`, in roughly equal sixths, with
padding junk (`eeeee`, `NOOOO`, `!!!`, `!`) attached in most encodings. §4.2 normalises the
separators and strips the junk — and grades quality against the **original** string, so the repairs
are itemised rather than hidden.

---

## What the notebook covers

| § | Content |
|---|---|
| 1 | **Ingestion** — two-pass read: infer the *structure*, discard the *types*, re-read with every leaf as `string`. Unparseable lines quarantined via `_corrupt_record`. |
| 2 | **JSON flattening** — a generic recursive struct expander *plus* embedded-JSON parsing, mapped to the 26 required columns by leaf name. |
| 3 | **Profiling** — null/blank/token-missing rates, cardinality, off-pattern value samples. |
| 4 | **Cleaning & data quality** — ~50 named rules, each producing a typed value *and* a flag. Includes the **timestamp conversion to UTC+8** (§4.1) and the **`person_name` derivation** (§4.2). |
| 5 | **PII handling** — in-place masking/tokenisation and a bronze/silver/gold layering, with the 26-column schema contract verified and a measured re-identification check. |
| 6 | **Feature engineering** — haversine distance, UTC+8 hour/day, merchant tenure, in-category amount z-score. |
| 7 | **Visualisation** — six figures, each with its rationale, its table, and what it means. |
| 8–9 | Parquet outputs, findings, and limitations. |

### Decisions worth knowing before you read it

**Nothing is silently dropped.** Failing rows are tagged with the rule they broke and routed to a
quarantine table. The quarantine is an output, not a side effect.

**Types are never inferred.** Schema inference on dirty data means Spark decides what to null out
and does not tell you. Every cast here is explicit and has a named failure branch. The same applies
to the embedded JSON and to the epoch units: the *shape* is inferred, the *values* never guessed.

**PII is layered, not hashed once.** `sha2(cc_num)` is *not* protection — a 16-digit card with a
known BIN and a Luhn-constrained check digit is about 10⁹ candidates, which a GPU enumerates in
seconds. The notebook uses a keyed HMAC whose secret never touches the data, and separately
generalises the quasi-identifiers (ZIP + date of birth + gender uniquely identifies most of the US
population, so tokenising the name alone achieves nothing).

**PII handling never deletes a *required* column.** The brief specifies 26 output columns, so
masking, tokenisation and generalisation are all applied **in place**: `cc_num` becomes
`374512******2099`, `street` becomes `[REDACTED]`, `zip` becomes `468**`, `dob` drops to year of
birth. Derived keys (`card_token`, `cc_bin6`, `cc_last4`, `zip3`, `age_band`) are added *beside*
the originals, not in place of them.

The one column that *is* dropped is **`person_name`** — the raw string `first` and `last` are
derived from, which is not one of the 26. Masking `first` and `last` while carrying the unmasked
source beside them protects nothing. §5.6 asserts it is gone, and asserts that every retained
identifier actually holds a masked *value*, not merely a masked column name.

**The quarantine is not an exemption.** `quarantine_failed_rules` is written through the *same*
silver treatment as the clean rows — one function, two callers — so a row that failed a
data-quality rule is not a way around the PII policy. Unparseable lines are stored redacted by
character class, since a line that never parsed cannot be protected column by column.

**The identity key was chosen by measurement, and so was its failure mode.** The obvious cardholder
key — `HMAC(first | last | dob)` — is built from the dirtiest columns in the feed, and §5.5 measures
what that costs. The card key has its own failure mode, measured in the same place: a card number
that fails its Luhn checksum tokenises to a phantom cardholder who does not exist. So `card_token`
is **NULL** where the checksum failed, with `card_identity_reliable` beside it — and since
`count(DISTINCT ...)` ignores NULL, every card-level metric is correct by construction rather than
by remembering to filter. Those rows stay in every *transaction*-level figure; only the identity is
withheld.

**Conflicting duplicates are quarantined, not resolved.** Where one `trans_num` carries two
different contents, *every* version is quarantined. Picking "the first by ingestion order" is not
available: `Unnamed: 0` is a source index that a replayed row shares with the row it replays, and
Spark does not preserve JSON line order anyway, so that rule produced a nondeterministic survivor.

**"UTC+8" is a rendering, not a local clock.** The brief asks for output at UTC+8; every address in
the feed is in the United States; `trans_date_trans_time` carries no offset. Those cannot all
describe a cardholder's wall clock, so no hour in this notebook is called "local time" — the columns
are `hour_utc8` and `dow_utc8`, and §7.1 draws no conclusion that depends on what a cardholder was
doing at that hour. Confirming the source timezone with the data producer is a prerequisite for any
hour-of-day conclusion.

**Timestamps are delivered in the brief's columns.** `trans_date_trans_time`,
`merch_last_update_time` and `merch_eff_time` carry the UTC+8 string the brief asks for
(`2019-09-01 10:37:00.000000 +0800`), asserted against that format in §5.6. The canonical typed
instant stays beside each as `<col>_utc`, because cross-field rules and engineered features have to
compute on instants, not strings.

**Previews are redacted before §5 runs.** The profiling cells in §1–§4 look at values that are still
raw. They are redacted by character class for display — digits to `9`, upper to `X`, lower to `x`,
punctuation kept — so a defect's *shape* stays visible (`9999-9999-9999-9999`, `Xxxxx|Xxxxxx!!!`)
while the identity does not. That is what keeps real card numbers and addresses out of a notebook
that goes to GitHub.

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
├── data/
│   ├── raw/                    Input JSON (gitignored)
│   └── curated/                Parquet outputs (gitignored)
└── output/figures/             Exported PNGs (gitignored)
```

### Outputs the notebook writes

| Path | Contents |
|---|---|
| `data/curated/curated_transactions/` | The silver layer — full 26-column schema, direct identifiers masked or tokenised, quasi-identifiers exact. |
| `data/curated/analytics_transactions/` | The gold layer — same schema, quasi-identifiers generalised, feature-engineered. Partitioned by `date_utc8`. |
| `data/curated/quarantine_failed_rules/` | Rows that failed a fatal rule, with `dq_flags` attached — **silver-tier protected**. |
| `data/curated/quarantine_unparseable/` | Lines that were not valid JSON, redacted by character class. |
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
| `PII_HMAC_KEY` | **none — required** | Secret for tokenising card numbers and transaction IDs. The notebook refuses to start without one of at least 32 characters. |
| `JUPYTER_TOKEN` | `paynet` | JupyterLab login token. |

---

## Troubleshooting

**`PII_HMAC_KEY: set PII_HMAC_KEY...`** — compose is refusing to start without a key. See Quick
start; this is working as intended.

**`Cannot connect to the Docker daemon`** — Docker Desktop is not running. Start it and wait for
the whale icon to settle.

**Port 8888 already in use** — another Jupyter is running. Either stop it, or change the mapping in
`docker-compose.yml` to `"8889:8888"`.

**`FileNotFoundError: ../data/raw/transactions.json`** — no input file yet. See
[Getting the data](#getting-the-data).

**Kernel dies during a wide aggregation** — the Spark driver ran out of heap. This feed is 967 MB
and 1.3 M rows, so give Docker Desktop at least 8 GB under *Settings ▸ Resources* and raise
`spark.driver.memory` in the notebook's session builder to match.

**`java.net.UnknownHostException` on startup** — the container could not resolve its own hostname.
`SPARK_LOCAL_IP=127.0.0.1` is already set in the Dockerfile to prevent this; if you are running
outside compose, pass it explicitly.

**`proxyconnect tcp: ... lookup http.docker.internal: i/o timeout` on build** — Docker Desktop's
internal DNS has wedged; its proxy hostname stops resolving inside the VM. Restart Docker Desktop.
