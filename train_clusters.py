"""Train a reproducible TF-IDF + spherical k-means complaint clustering model.

Run: python train_clusters.py --clusters 10
The script writes assignments, cluster summaries, trend counts, review samples,
and the fitted model. Requires NumPy; no external model service is used.
"""

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODEL = ROOT / "model"

# Keep issue terms and the negation "not". Remove common prose and terms shared by nearly
# every report so groups form around failure symptoms and parts.
STOP = set("""
a about above after again against all am an and any are as at be because been
before being below between both but by can could did do does doing down during
each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself of
off on once only or other our ours ourselves out over own same she should so
some such than that the their theirs them themselves then there these they
this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself yourselves
also able according already another around back came come comes contact dealer
dealership driver driving issue issues jeep vehicle vehicles wrangler car cars
truck trucks owner owners stated states said says told took went got get getting
time times day days month months year years first last one two three several
many model make new old called service problem problems happened happen happens
failure mileage manufacturer diagnosed repaired repair owns nhtsa campaign
number electrical system xxx information redacted pursuant freedom act foia
reasonable exceeded amount
""".split())
TOKEN = re.compile(r"[a-z][a-z0-9]{2,}")
FOIA = re.compile(r"information redacted pursuant to the freedom of information act.*", re.I)


def tokenize(text: str) -> list[str]:
    text = FOIA.sub(" ", text)
    return [term for term in TOKEN.findall(text.lower()) if term not in STOP and not term.isdigit()]


def features(tokens: list[str]) -> Counter:
    result = Counter(tokens)
    result.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]) if a != b)
    return result


def vectorize(texts: list[str], min_df: int = 5, max_df_ratio: float = 0.6, max_features: int = 6000):
    documents = [features(tokenize(text)) for text in texts]
    df = Counter(term for document in documents for term in document)
    eligible = [term for term, freq in df.items() if min_df <= freq <= max_df_ratio * len(texts)]
    eligible.sort(key=lambda term: (-df[term], term))
    vocabulary = eligible[:max_features]
    idf = np.array([math.log((1 + len(texts)) / (1 + df[term])) + 1 for term in vocabulary], dtype=np.float32)
    matrix = transform_with_vocab(texts, vocabulary, idf, documents=documents)
    return matrix, vocabulary, idf


def transform_with_vocab(texts: list[str], vocabulary, idf: np.ndarray, documents=None) -> np.ndarray:
    if documents is None:
        documents = [features(tokenize(text)) for text in texts]
    index = {term: j for j, term in enumerate(vocabulary)}
    matrix = np.zeros((len(texts), len(vocabulary)), dtype=np.float32)
    for i, document in enumerate(documents):
        for term, count in document.items():
            j = index.get(term)
            if j is not None:
                matrix[i, j] = (1 + math.log(count)) * idf[j]
    norm = np.linalg.norm(matrix, axis=1)
    norm[norm == 0] = 1
    matrix /= norm[:, None]
    return matrix


def initialize(matrix: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    n = len(matrix)
    indices = [int(rng.integers(n))]
    nearest = 1 - matrix @ matrix[indices[0]]
    for _ in range(1, k):
        weights = np.maximum(nearest, 0) ** 2
        if weights.sum() == 0:
            next_index = int(rng.integers(n))
        else:
            next_index = int(rng.choice(n, p=weights / weights.sum()))
        indices.append(next_index)
        nearest = np.minimum(nearest, 1 - matrix @ matrix[next_index])
    return matrix[indices].copy()


def fit_kmeans(matrix: np.ndarray, k: int, seed: int = 42, restarts: int = 3, max_iter: int = 40):
    best = None
    for attempt in range(restarts):
        rng = np.random.default_rng(seed + attempt)
        centroids = initialize(matrix, k, rng)
        previous = None
        for _ in range(max_iter):
            similarities = matrix @ centroids.T
            labels = np.argmax(similarities, axis=1)
            if previous is not None and np.array_equal(labels, previous):
                break
            previous = labels.copy()
            updated = np.zeros_like(centroids)
            np.add.at(updated, labels, matrix)
            lengths = np.linalg.norm(updated, axis=1)
            for j in range(k):
                if lengths[j] == 0:
                    updated[j] = matrix[int(rng.integers(len(matrix)))]
                else:
                    updated[j] /= lengths[j]
            centroids = updated
        similarities = matrix @ centroids.T
        labels = np.argmax(similarities, axis=1)
        confidence = similarities[np.arange(len(matrix)), labels]
        objective = float(confidence.mean())
        if best is None or objective > best[0]:
            best = objective, labels, confidence, centroids
    return best


def sample_silhouette(matrix: np.ndarray, labels: np.ndarray, seed: int = 7, sample_size: int = 350) -> float:
    rng = np.random.default_rng(seed)
    sample = rng.choice(len(matrix), size=min(sample_size, len(matrix)), replace=False)
    assignment = labels[sample]
    distances = 1 - matrix[sample] @ matrix[sample].T
    values = []
    for i, label in enumerate(assignment):
        same = np.flatnonzero(assignment == label)
        if len(same) <= 1:
            values.append(0.0)
            continue
        a = float(distances[i, same[same != i]].mean())
        b = min(float(distances[i, assignment == other].mean()) for other in set(assignment) if other != label)
        values.append((b - a) / max(a, b) if max(a, b) else 0.0)
    return float(np.mean(values))


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def save_results(rows, matrix, vocabulary, idf, objective, labels, confidence, centroids, silhouette):
    DATA.mkdir(exist_ok=True)
    MODEL.mkdir(exist_ok=True)
    k = len(centroids)
    label_file = MODEL / "cluster_labels.json"
    human_labels = {}
    if label_file.exists():
        label_config = json.loads(label_file.read_text(encoding="utf-8"))
        if label_config.get("cluster_count") == k:
            human_labels = label_config.get("labels", {})
    vocab = np.array(vocabulary)
    np.savez_compressed(MODEL / "tfidf_spherical_kmeans.npz", vocabulary=vocab, idf=idf, centroids=centroids,
                        cluster_count=np.array(k), seed=np.array(42))

    with (DATA / "cluster_assignments.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("complaint_id", "received_date", "model_year", "cluster_id", "cosine_similarity", "needs_review"))
        for row, label, score in zip(rows, labels, confidence):
            writer.writerow((row["complaint_id"], row["received_date"], row["model_year"], int(label) + 1,
                             f"{score:.4f}", "yes" if score < 0.15 else "no"))

    all_months = load_rows(DATA / "monthly_counts.csv")
    months = [row["received_month"] for row in all_months]
    month_counts = Counter((int(label) + 1, row["received_date"][:7]) for row, label in zip(rows, labels))
    with (DATA / "cluster_monthly_counts.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("cluster_id", "received_month", "complaint_count"))
        for label in range(1, k + 1):
            for month in months:
                writer.writerow((label, month, month_counts[(label, month)]))

    summaries = []
    review_rows = []
    review_rng = np.random.default_rng(2026)
    for label in range(k):
        indices = np.flatnonzero(labels == label)
        ranked = indices[np.argsort(-confidence[indices])]
        top_terms = vocab[np.argsort(-centroids[label])[:14]].tolist()
        top_months = sorted(((month, month_counts[(label + 1, month)]) for month in months), key=lambda item: -item[1])[:4]
        summaries.append({
            "cluster_id": label + 1,
            "label": human_labels.get(str(label + 1), "Unreviewed cluster"),
            "count": len(indices),
            "share_percent": round(100 * len(indices) / len(rows), 1),
            "mean_cosine_similarity": round(float(confidence[indices].mean()), 3),
            "top_terms": top_terms,
            "representative_complaint_ids": [rows[i]["complaint_id"] for i in ranked[:5]],
            "top_months": top_months,
        })
        selected = (
            [(int(i), "representative") for i in ranked[:3]]
            + [(int(i), "random") for i in review_rng.choice(indices, size=min(5, len(indices)), replace=False)]
            + [(int(i), "low_similarity") for i in ranked[-3:]]
        )
        for i, kind in selected:
            review_rows.append((label + 1, kind, rows[i]["complaint_id"], rows[i]["received_date"],
                                f"{confidence[i]:.3f}", rows[i]["narrative"][:700]))
    with (DATA / "review_samples.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("cluster_id", "sample_kind", "complaint_id", "received_date", "cosine_similarity", "narrative_excerpt"))
        writer.writerows(review_rows)
    summary = {
        "method": "TF-IDF unigrams and bigrams; spherical k-means using cosine similarity",
        "documents": len(rows), "features": len(vocabulary), "clusters": k,
        "mean_assignment_cosine": round(objective, 4),
        "sample_silhouette_cosine": round(silhouette, 4),
        "low_similarity_review_count": int((confidence < 0.15).sum()),
        "clusters_detail": summaries,
        "note": "Cluster labels are unsupervised suggestions; inspect review_samples.csv before interpreting them.",
    }
    (DATA / "cluster_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=int, default=10)
    parser.add_argument("--input", type=Path, default=DATA / "complaints.csv")
    args = parser.parse_args()
    if not 2 <= args.clusters <= 30:
        parser.error("--clusters must be between 2 and 30")
    rows = load_rows(args.input)
    matrix, vocabulary, idf = vectorize([row["narrative"] for row in rows])
    objective, labels, confidence, centroids = fit_kmeans(matrix, args.clusters)
    silhouette = sample_silhouette(matrix, labels)
    result = save_results(rows, matrix, vocabulary, idf, objective, labels, confidence, centroids, silhouette)
    print(json.dumps({key: value for key, value in result.items() if key != "clusters_detail"}, indent=2))
    for item in result["clusters_detail"]:
        print(item["cluster_id"], item["count"], ", ".join(item["top_terms"][:8]))
