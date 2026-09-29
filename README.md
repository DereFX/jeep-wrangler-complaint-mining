# Jeep Wrangler electrical complaint mining

## Project focus

This project helps a vehicle quality team inspect **Jeep Wrangler electrical-system complaints**. It groups narratives with similar language, shows the complaints behind each group, and tracks each group's monthly volume. A cluster or spike is a lead for human review, not proof of a defect.

The current source is the public [NHTSA consumer complaints dataset](https://www.nhtsa.gov/nhtsa-datasets-and-apis). These reports are **not manufacturer warranty claims**: they do not contain warranty decisions, repair costs, or all service visits. The same clustering workflow could later ingest internal warranty records if access is available, but the claims made in this review should match the NHTSA source.

## Phase 1 scope and result

| Decision | Value |
|---|---|
| Make and model | Jeep Wrangler |
| Component | `ELECTRICAL SYSTEM` and its subcategories |
| Model years | 2018–2025 |
| Complaint received dates | 2020-01-01 through 2026-08-31 |
| Source snapshot | Official files available on 2026-09-16 |
| Source rows scanned | 612,781 across the two five-year files |
| Rows matching make, model, and component before other filters | 1,915 |
| Cleaned distinct complaints | **1,578** across 80 complete months |

The September 2026 partial month is excluded. The preparation script also removes 28 narratives shorter than 40 characters and collapses three repeated component rows with the same NHTSA complaint number. The detailed counts and source-file SHA-256 hashes are in `data/run_metadata.json`.

## Files

- `prepare_data.py` — reproducible, standard-library-only extraction and cleaning script.
- `data/complaints.csv` — cleaned complaint-level input for text clustering. This local file is Git-ignored; review narratives before public redistribution.
- `data/monthly_counts.csv` — complete month series, including zero-count months.
- `data/run_metadata.json` — source URLs, hashes, filters, field names, and cleaning counts.
- `train_clusters.py` — TF–IDF text features and spherical k-means clustering.
- `predict_clusters.py` — assign new complaint narratives with the saved model.
- `analyze_clusters.py` — reproduce the peak-month findings.
- `data/cluster_assignments.csv` — complaint ID, assigned cluster, cosine similarity, and a review flag.
- `data/cluster_monthly_counts.csv` — full monthly series for each cluster.
- `data/cluster_summary.json` — counts, top terms, labels, and representative complaint IDs.
- `data/review_samples.csv` — representative, random, and low-similarity excerpts for human review.
- `model/cluster_labels.json` — labels assigned after inspecting examples.
- `model/tfidf_spherical_kmeans.npz` — fitted vocabulary, IDF weights, and centroids.
- `DATA_DICTIONARY.md` — fields and interpretation limits.
- `CLUSTER_REVIEW.md` — model selection, findings, and observed weaknesses.

## Reproduce the data

Download the official [2020–2024 complaints ZIP](https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2020-2024.zip) and [2025–2026 complaints ZIP](https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2025-2026.zip). Save them in a local directory under the names `complaints_2020_2024.zip` and `complaints_2025_2026.zip`.

```bash
python prepare_data.py --source-dir /path/to/downloads
```

Python 3.10 or newer is sufficient. NHTSA updates the files, so a later run can produce different counts. Use the hashes in `run_metadata.json` to identify this snapshot.

## Initial data observation

October 2025 contains 222 complaints in this cohort, 182 of them associated with model year 2024. Several narratives mention a software update and loss of power. This is an observation from the reported text, not a confirmed cause. Phase 2 should test whether those narratives form a coherent cluster and compare it with other issues, rather than treating all electrical complaints as one problem.

## Phase 2: cluster the narratives

Install the pinned NumPy version and run the model. Python's standard library handles the rest.

```bash
python -m pip install -r requirements.txt
python train_clusters.py --clusters 8
python analyze_clusters.py
python predict_clusters.py data/complaints.csv data/predicted.csv
```

The model uses unigrams and bigrams with common filler terms removed, then groups normalized TF–IDF vectors by cosine similarity. The random seed and cluster count are fixed for reproducibility. Eight clusters were selected after comparing seven, eight, and ten clusters and reviewing examples. The fitted model and narrative CSVs are Git-ignored; regenerate them from the scripts.

The largest month is October 2025: 222 complaints, including 153 assigned to the unexpected-shutdown cluster. Of those 153, 121 mention an update, OTA, or Uconnect term. This is a descriptive signal, not a finding that an update caused the reported failures. See `data/insight_checks.json` and `CLUSTER_REVIEW.md`.

## Cloud application

The project now implements the team's end-to-end pipeline: a standard JSON REST API, raw claims in S3, containerized Lambda preprocessing, Gemini classification through `classify_claim()`, DynamoDB operational records, and a Streamlit dashboard on App Runner. Terraform defines the AWS resources. See [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](API.md), and [DEPLOYMENT.md](DEPLOYMENT.md).

The eight Phase 2 clusters were used to define reviewable issue families. Gemini assigns each incoming complaint to one of those families or `other`; it does **not** discover new unsupervised clusters on every submission. The dashboard shows which issue families account for the most complaints and how their monthly counts change.

The local REST server uses a clearly marked deterministic mock classifier so the complete flow can be demonstrated without credentials. AWS always uses the Gemini adapter. Run the local demonstration from this directory:

```powershell
python -m unittest discover -s tests -v
python -m cloud.local_server
```

In another terminal:

```powershell
$env:API_BEARER_TOKEN = 'local-demo-token'
python backfill.py --limit 20
```

Install `requirements-dashboard.txt` and run `streamlit run dashboard/app.py` to view the dashboard at `http://localhost:8501`. Enter `local-demo-token` at the dashboard access prompt. Local JSON files are written outside this deliverable under the workspace `work/local_data` directory.

The AWS and GitHub deployment is pending account and repository setup. The source, containers, Terraform, and deployment sequence are prepared; no live infrastructure or Gemini inference has been claimed. The dashboard access token is a simple course demonstration control. Real warranty data requires stronger identity controls and privacy review before sending claim text to Gemini.

The source is voluntary complaint reporting, so counts are affected by awareness and reporting behavior. There is no vehicle population denominator here; the dashboard must call these **complaint counts**, not failure rates. The script masks VIN-like strings, email addresses, and phone numbers, but automated masking is incomplete and the narrative file should remain out of the public Git repository.
