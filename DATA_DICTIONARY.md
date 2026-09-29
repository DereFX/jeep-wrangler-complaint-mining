# Cleaned complaint data dictionary

`data/complaints.csv` has one row per distinct NHTSA complaint number after filtering. It uses these columns from the official [NHTSA complaint layout](https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt):

| Cleaned column | Original field | Meaning |
|---|---|---|
| `complaint_id` | `ODINO` | Public NHTSA complaint reference used to deduplicate repeated component rows. |
| `received_date` | `LDATE` | Date NHTSA received the complaint, formatted `YYYY-MM-DD`. It is not necessarily the failure date. |
| `model_year` | `YEARTXT` | Vehicle model year, restricted to 2018–2025. |
| `component` | `COMPDESC` | Normalized to the broad `ELECTRICAL SYSTEM` category for this cohort. |
| `complaint_source_code` | `CMPL_TYPE` | Original NHTSA source code, such as `IVOQ` for website submissions or `EVOQ` for hotline submissions. |
| `narrative` | `CDESCR` | Complaint description with whitespace normalized and common VIN, email, and phone patterns masked. |

The raw files also contain direct identifiers and other fields that are intentionally omitted. The script keeps the longest narrative if a complaint has repeated electrical component rows. It does not infer whether a reported issue is valid, unique, covered by warranty, or caused by a defect.

`data/monthly_counts.csv` is derived from `received_date` and includes `received_month` (`YYYY-MM`) and `complaint_count`. It is the baseline series before topic clustering.
