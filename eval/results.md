# Evaluation results

65 AI use cases written in plain words, each labelled individually against the published texts (45 development cases used while writing the rules, 20 held-out cases written separately and run once after the rules were committed). Labelling conventions: [labelling-guide.md](labelling-guide.md). Reproduce with `python eval/run_eval.py --check` (offline, replays the recorded model replies).

## 1. Rules engine on the hand-filled intake answers

| Measure | Development | Held-out | All |
|---|---|---|---|
| Cases | 45 | 20 | 65 |
| EU AI Act tier accuracy | 100.0% | 100.0% | 100.0% |
| High-risk recall | 100.0% | 100.0% | 100.0% |
| High-risk cases missed | 0 | 0 | 0 |
| High-risk precision | 100.0% | 100.0% | 100.0% |
| Annex III area correct (high-risk cases) | 100.0% | 100.0% | 100.0% |
| Prohibited recall | 100.0% | 100.0% | 100.0% |
| Prohibited precision | 100.0% | 100.0% | 100.0% |
| Privacy-regime precision | 100.0% | 100.0% | 100.0% |
| Privacy-regime recall | 100.0% | 100.0% | 100.0% |
| Overall risk-level accuracy | 100.0% | 100.0% | 100.0% |
| Risk level rated lower than the label | 0 | 0 | 0 |

Privacy-regime labels in the set: eu_gdpr 39, uk_gdpr 8, au_app 3, nz_ipp 2, us_state 5.

## 2. Model pre-fill: the model reads only the description

Model: `gemini-flash-lite-latest`, temperature 0, one recorded reply per case (65 replies).

Field accuracy against the hand-filled answers (lists count as correct only when the whole set matches):

| Field | Development | Held-out | All |
|---|---|---|---|
| use_area | 82.2% | 85.0% | 83.1% |
| decision_mode | 80.0% | 90.0% | 83.1% |
| processing_region | 86.7% | 90.0% | 87.7% |
| data_categories | 71.1% | 85.0% | 75.4% |
| affected | 64.4% | 55.0% | 61.5% |
| people_regions | 86.7% | 65.0% | 80.0% |
| org_regions | 97.8% | 80.0% | 92.3% |
| flags | 35.6% | 40.0% | 36.9% |
| flags_precision | 68.3% | 70.2% | 68.9% |
| flags_recall | 92.2% | 97.1% | 93.7% |

End to end, with no person checking the model's answers (the hub always asks a person to confirm each one):

| Measure | Development | Held-out | All |
|---|---|---|---|
| EU AI Act tier accuracy | 91.1% | 90.0% | 90.8% |
| High-risk recall | 100.0% | 100.0% | 100.0% |
| High-risk cases missed | 0 | 0 | 0 |
| Prohibited recall | 100.0% | 66.7% | 88.9% |
| Privacy-regime precision | 100.0% | 88.2% | 96.2% |
| Privacy-regime recall | 97.3% | 75.0% | 89.5% |
| Overall risk-level accuracy | 95.6% | 85.0% | 92.3% |
| Risk level rated lower than the label | 0 | 1 | 1 |

## Cases the end-to-end run got wrong

| Case | Tier label | Got | Level label | Got |
|---|---|---|---|---|
| dev-23 | limited | limited | medium | high |
| dev-29 | limited | high | high | high |
| dev-32 | minimal | high | medium | high |
| dev-34 | minimal | limited | medium | medium |
| dev-44 | minimal | limited | medium | medium |
| hold-03 | prohibited | high | prohibited | high |
| hold-13 | limited | limited | medium | high |
| hold-16 | minimal | minimal | low | medium |
| hold-18 | minimal | limited | high | high |
