# Phase 2 cluster review

## Method and selection

The model converts each complaint narrative into TF–IDF unigram and bigram features, removes common filler language, and groups normalized vectors with spherical k-means. It has 3,300 features and eight clusters. The fixed random seed is 42. Seven, eight, and ten clusters were compared: seven produced a generic warning-light group, while ten split instrument-panel complaints into two similar groups. Eight gave the clearest operational themes in the inspected examples.

The sampled cosine silhouette score is **0.0493**, which indicates considerable overlap. The mean assigned cosine similarity is **0.2925**. Treat labels as navigation aids, not ground truth. Ninety-five of 1,578 assignments have similarity below 0.15 and are flagged for review.

| ID | Human label | Complaints | Review note |
|---:|---|---:|---|
| 1 | Steering assist and dashboard warnings | 267 | Mixed warning and steering symptoms; some unrelated steering hardware reports enter this group. |
| 2 | Display, radio, and backup camera | 130 | Some instrument-cluster and broader electrical reports also enter this group. |
| 3 | Unexpected shutdown and restart | 278 | Includes the October 2025 update-related concentration; not every complaint mentions an update. |
| 4 | Recall repair parts unavailable | 111 | A coherent service/recall process theme, not a physical failure theme. |
| 5 | Hybrid drive power loss | 220 | Often describes 4xe power or charging trouble, with overlap with cluster 3. |
| 6 | Instrument cluster and gauges | 233 | Generally coherent, though reports with multiple symptoms can cross into other display groups. |
| 7 | Battery fire and charging restrictions | 172 | Overlaps heavily with cluster 8. |
| 8 | Broader safety recall concerns | 167 | Mixes battery fire, recall availability, and other safety concerns; review before using as a defect category. |

Five randomly selected complaints per cluster were read alongside representative and low-similarity examples. Clusters 3, 4, 5, and 6 had a recognizable core issue. Clusters 2, 7, and 8 were less clean. One source row was tagged as Wrangler while its narrative referred to a Grand Cherokee, showing that the public source can contain inconsistent product text.

## Most useful signal for the project demo

October 2025 has **222** complaints in the selected cohort. Cluster 3 contains **153** of them (**68.9%**). Within those 153, **121** narratives mention an update, OTA, or Uconnect term; **142** are tagged as model year 2024. These numbers are reproduced by `analyze_clusters.py` and stored in `data/insight_checks.json`.

The pattern warrants review of the individual complaints. It does not establish a root cause, failure rate, or recall need. Reporting campaigns, near-duplicate wording, and changing complaint behavior can produce apparent spikes. The future dashboard should show the underlying narratives and the month-by-month counts alongside any alert.

## Follow-up improvements

- Add a human-reviewed evaluation set for issue themes and multi-issue narratives.
- Separate administrative recall complaints from technical failure reports before defect-trend alerts.
- Allow a report to receive more than one issue tag, since some narratives describe several failures.
- Improve negation handling. A trial that retained short `no` tokens and vehicle codes made the groups less distinct, so this baseline only retains longer negations such as `not`.
- Consider sentence embeddings if TF–IDF misses similar symptoms expressed with different words; keep the current model as an interpretable baseline.
