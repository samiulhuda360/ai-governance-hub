# Labelling guide for the evaluation set

Each case is an AI use case written in plain words, the way a member of staff would describe it. A person labels
it by reading the published legal texts, not the hub's rules. Each case has three parts:

1. `text`: the description, 40–120 words, in everyday language. Name an invented organisation (Acme-style
   names, such as "Northwind Clinic" or "Acme Freight"), a sector and a country. Western first names only.
2. `intake`: the form answers a careful member of staff would give from that description (the fields are in
   `governance_hub/intake.py`: `use_area`, `data_categories`, `affected`, `decision_mode`, `processing_region`,
   `people_regions`, `org_regions`, `flags`, plus `title`, `purpose`, `team`, `vendor`, `model`,
   `expected_users`, `hours_saved_per_week`). Fill in only what the text supports.
3. `labels`: the answer key.

## Labels

### `tier`: EU AI Act risk tier

Take the highest that applies.

- `prohibited`: a practice listed in **Article 5(1)(a)–(h)**: harmful manipulation; exploiting vulnerabilities
  of age, disability or social or economic situation; social scoring leading to detrimental treatment; assessing
  the risk that a person commits a crime based solely on profiling or personality traits; untargeted scraping of
  facial images to build face-recognition databases; emotion recognition in the workplace or in education
  (except for medical or safety reasons); biometric categorisation to infer race, political opinions, trade-union
  membership, religious or philosophical beliefs, sex life or sexual orientation; real-time remote biometric
  identification in publicly accessible spaces for law enforcement.
- `high`: an **Annex III** use (see the areas below), unless the **Article 6(3)** exception applies (the
  system only does a narrow procedural task, improves the result of a finished human activity, detects
  decision patterns without replacing human assessment, or does a preparatory task) **and** it does not profile
  people. A system that profiles people in an Annex III area is always high-risk (Article 6(3), last
  subparagraph). Also `high` when the AI is a safety component of a product covered by **Annex I** law
  (Article 6(1)).
- `limited`: not high-risk, but an **Article 50** transparency duty applies: people interact directly with
  the AI (50(1)); it generates synthetic audio, images, video or text (50(2)); it is an emotion-recognition or
  biometric-categorisation system (50(3)); it produces deepfakes, or text published to inform the public on
  matters of public interest (50(4)).
- `minimal`: none of the above.

Watch for the edge cases written into the Act: biometric **verification** (confirming someone is who they claim)
is excluded from Annex III point 1(a); **fraud detection** is excluded from credit scoring in point 5(b); only
**life and health** insurance is in point 5(c); credit scoring is about **natural persons**, not companies;
recital 18 says detecting **physical states such as pain or fatigue** is not emotion recognition.

### `annex_area`: required when the tier is `high`, otherwise `null`

One of `biometrics` (Annex III 1), `critical_infrastructure` (2), `education` (3), `employment` (4),
`essential_services` (5), `law_enforcement` (6), `migration` (7), `justice_democracy` (8), or
`product_safety` (Article 6(1), Annex I).

### `regimes`: privacy laws to check

A list from `eu_gdpr`, `uk_gdpr`, `au_app` (Australian Privacy Act 1988, Australian Privacy Principles),
`nz_ipp` (New Zealand Privacy Act 2020, Information Privacy Principles), `us_state` (US state privacy laws).
A regime applies when the use case handles information about identifiable people **and** either the people are
in that region or the organisation is established there. This follows the territorial scope of each law in broad
terms (for example GDPR Article 3(1) and 3(2)); thresholds such as Australia's small-business exemption are left
to the privacy reviewer. Empty when no personal information is involved.

### `risk_level`: the overall level a governance lead would give

- `prohibited`: the tier is `prohibited`.
- `high`: the tier is `high`; or the AI makes decisions about people with legal or similarly significant
  effects with no person looking at each one; or it handles health, biometric or children's information about
  customers or the public.
- `medium`: personal information about customers or the public; sensitive (health, biometric, financial)
  information about staff; the AI acts on things that affect people, with review afterwards; a transparency
  duty applies; or personal information is processed in a different region from the people it is about.
- `low`: internal use, little or no personal information, and a person decides.

Use judgement: these describe a governance lead's typical call, not a formula.
