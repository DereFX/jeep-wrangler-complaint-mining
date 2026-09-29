"""Assign new complaint narratives to the fitted clusters.

Run: python predict_clusters.py input.csv output.csv
Input must contain complaint_id and narrative columns. Predictions are suggestions
for review, especially when cosine similarity is below 0.15.
"""

import argparse
import csv
from pathlib import Path

import numpy as np

from train_clusters import MODEL, transform_with_vocab


def predict(input_path: Path, output_path: Path, model_path: Path) -> None:
    with input_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not {"complaint_id", "narrative"}.issubset(rows[0]):
        raise ValueError("Input needs complaint_id and narrative columns with at least one row")
    with np.load(model_path) as archive:
        vocabulary = archive["vocabulary"]
        idf = archive["idf"]
        centroids = archive["centroids"]
    matrix = transform_with_vocab([row["narrative"] for row in rows], vocabulary, idf)
    similarities = matrix @ centroids.T
    labels = np.argmax(similarities, axis=1) + 1
    scores = similarities[np.arange(len(rows)), labels - 1]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("complaint_id", "cluster_id", "cosine_similarity", "needs_review"))
        for row, label, score in zip(rows, labels, scores):
            writer.writerow((row["complaint_id"], int(label), f"{score:.4f}", "yes" if score < 0.15 else "no"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", type=Path, default=MODEL / "tfidf_spherical_kmeans.npz")
    args = parser.parse_args()
    predict(args.input, args.output, args.model)
