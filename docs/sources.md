# Sources

Every rule in `governance_hub/rules/` cites one of the provisions below. Wording in the rules is a close
paraphrase of the published text, written for staff who are not lawyers. The hub supports governance decisions;
it is not legal advice, and a qualified reviewer should confirm any finding that matters.

## EU AI Act: Regulation (EU) 2024/1689

| Provision | What it says (paraphrased) | Used for |
|---|---|---|
| Art. 4 | Providers and deployers take measures to ensure a sufficient level of AI literacy of their staff. | Training duty on every use case; training catalogue |
| Art. 5(1)(a) | Ban on subliminal, purposefully manipulative or deceptive techniques that materially distort behaviour and cause or are likely to cause significant harm. | Prohibited |
| Art. 5(1)(b) | Ban on exploiting vulnerabilities due to age, disability or a specific social or economic situation. | Prohibited |
| Art. 5(1)(c) | Ban on social scoring leading to detrimental or unfavourable treatment in unrelated contexts or out of proportion. | Prohibited |
| Art. 5(1)(d) | Ban on assessing the risk of a person committing a crime based solely on profiling or personality traits. | Prohibited |
| Art. 5(1)(e) | Ban on untargeted scraping of facial images from the internet or CCTV to build facial-recognition databases. | Prohibited |
| Art. 5(1)(f) | Ban on inferring emotions in the workplace and education institutions, except for medical or safety reasons. | Prohibited |
| Art. 5(1)(g) | Ban on biometric categorisation to infer race, political opinions, trade-union membership, religious or philosophical beliefs, sex life or sexual orientation. | Prohibited |
| Art. 5(1)(h) | Ban on real-time remote biometric identification in publicly accessible spaces for law enforcement, with narrow exceptions. | Prohibited |
| Art. 6(1), Annex I | AI that is a product or a safety component of a product under the Union harmonisation laws in Annex I and needs third-party conformity assessment is high-risk. | High-risk (product safety) |
| Art. 6(2), Annex III | AI systems in the Annex III areas are high-risk. | High-risk |
| Art. 6(3) | An Annex III system is not high-risk if it does not pose a significant risk of harm, for example narrow procedural, improving a completed human activity, detecting decision patterns without replacing human assessment, or preparatory tasks; always high-risk if it profiles natural persons. | The exception and the profiling override |
| Art. 6(4), Art. 49(2) | A provider relying on Art. 6(3) documents its assessment and registers the system. | Exception note |
| Annex III 1(a)-(c) | Remote biometric identification (excluding verification), biometric categorisation by sensitive or protected attributes, emotion recognition. | Area: biometrics |
| Annex III 2 | Safety components in critical digital infrastructure, road traffic, and supply of water, gas, heating or electricity. | Area: critical infrastructure |
| Annex III 3(a)-(d) | Education: access and admission, evaluating learning outcomes, assessing the level of education, monitoring prohibited behaviour during tests. | Area: education |
| Annex III 4(a)-(b) | Employment: recruitment and selection; decisions on work terms, promotion, termination, task allocation based on behaviour or traits, monitoring and evaluating performance. | Area: employment |
| Annex III 5(a)-(d) | Public assistance benefits; creditworthiness of natural persons (excluding fraud detection); risk assessment and pricing for life and health insurance; emergency call classification, dispatch and patient triage. | Area: essential services |
| Annex III 6, 7, 8 | Law enforcement; migration, asylum and border control; administration of justice and democratic processes. | Areas 6-8 |
| Recital 18 | Emotion recognition does not include detecting physical states such as pain or fatigue. | Fatigue-detection explanation |
| Art. 26(1)-(2), (5), (6), (7), (11) | Deployer duties for high-risk AI: follow instructions, human oversight by competent people, monitor and report, keep logs at least six months, inform workers' representatives and workers, inform affected people. | Duties and controls |
| Art. 27 | Fundamental-rights impact assessment for public bodies, private bodies providing public services, and deployers of Annex III 5(b) and 5(c) systems. | Duties and the FRIA control |
| Art. 50(1)-(4) | Transparency: people told they interact with AI; synthetic content marked; deployers of emotion recognition or biometric categorisation inform people; deepfakes and AI-generated public-interest text disclosed. | Limited tier |
| Art. 86 | Right to an explanation of individual decision-making based on an Annex III high-risk system. | Duty |

## NIST AI Risk Management Framework 1.0 (NIST AI 100-1, January 2023)

| Subcategory | Summary | Check in the hub |
|---|---|---|
| GOVERN 1.6 | Mechanisms are in place to inventory AI systems. | Add to the AI register |
| GOVERN 2.2 | Personnel and partners receive AI risk management training. | Training completed |
| GOVERN 6.1 | Policies and procedures address risks from third-party entities. | Vendor terms review |
| MAP 1.1 | Intended purposes, context and settings are understood and documented. | Purpose and out-of-scope uses |
| MAP 3.4 | Processes for operator and practitioner proficiency are defined and documented. | What reviewers need to know |
| MAP 5.1 | Likelihood and magnitude of each identified impact are identified. | Impact estimate |
| MEASURE 2.5 | The AI system is demonstrated to be valid and reliable. | Accuracy test before go-live |
| MEASURE 2.7 | Security and resilience are evaluated and documented. | Access, prompt injection, storage |
| MEASURE 2.10 | Privacy risk is examined and documented. | Personal data in and out |
| MEASURE 2.11 | Fairness and bias are evaluated and results documented. | Bias testing |
| MANAGE 2.4 | Mechanisms are in place to supersede, disengage or deactivate AI systems. | Kill switch |
| MANAGE 4.1 | Post-deployment monitoring plans are implemented. | Usage, overrides, complaints |
| MANAGE 4.3 | Incidents and errors are communicated and tracked. | Incident log |

## ISO/IEC 42001:2023 (AI management systems)

Cross-references only, for organisations running a certified AI management system: clause 6.1.4 (AI system
impact assessment), clause 7.2 (competence), clause 9.1 (monitoring and measurement), clause 10.2
(nonconformity and corrective action), and Annex A control objectives A.4 (resources for AI systems, including
documenting them), A.6 (AI system life cycle), A.7 (data for AI systems) and A.10 (third-party and customer
relationships).

## Privacy laws

| Law | Provisions used |
|---|---|
| EU GDPR, Regulation (EU) 2016/679 | Art. 3 (territorial scope), 4(1) and 4(4) (personal data, profiling), 5(1)(c) (data minimisation), 6 (lawful basis), 8 and Recital 38 (children), 9 (special categories), 13-14 (information to people), 22 (solely automated decisions), 28 (processors), 35 (DPIA), 44-46 (international transfers), 45 (adequacy: the Commission has adequacy decisions for the UK, New Zealand and the EU-US Data Privacy Framework), 88 (employment context) |
| UK GDPR and Data Protection Act 2018 | The same article numbers; DPA 2018 Schedule 1 conditions; Art. 22A-22D as inserted by the Data (Use and Access) Act 2025 (check commencement for the decision date); ICO Age Appropriate Design Code; UK adequacy regulations and the International Data Transfer Agreement |
| Australia: Privacy Act 1988 (Cth), Schedule 1 | APP 1 (open and transparent management), APP 1.7-1.9 (automated decisions in privacy policies, inserted by the Privacy and Other Legislation Amendment Act 2024, from 10 December 2026), APP 3 and 3.3 (collection; sensitive information), APP 5 (notification), APP 6 (use and disclosure), APP 8 and s 16C (cross-border disclosure and accountability), APP 10 (quality), APP 11 (security); OAIC Guide to undertaking privacy impact assessments; Privacy (Australian Government Agencies - Governance) APP Code 2017 |
| New Zealand: Privacy Act 2020 | s 11 (information held by an agent, such as a cloud provider), s 22 IPP 1 (purpose), IPP 3 (collection from the person), IPP 4 (manner of collection, children and young people), IPP 5 (storage and security), IPP 8 (accuracy before use), IPP 10 (limits on use), IPP 12 (disclosure outside New Zealand); Biometric Processing Privacy Code 2025; Office of the Privacy Commissioner Privacy Impact Assessment Toolkit |
| United States (generic state-privacy check) | California Consumer Privacy Act as amended by the CPRA (Cal. Civ. Code 1798.100, 1798.105-1798.110, 1798.121); Virginia Consumer Data Protection Act (Va. Code 59.1-577 rights including opting out of profiling, 59.1-578 controller duties including consent for sensitive data, 59.1-579 processors, 59.1-580 data protection assessments); Colorado Privacy Act (C.R.S. 6-1-1305, 6-1-1306, 6-1-1308, 6-1-1309); Illinois Biometric Information Privacy Act (740 ILCS 14); COPPA (15 U.S.C. 6501-6506). Each state law has its own applicability thresholds, which the privacy reviewer checks. |

## Hub policy (not law)

The risk points, the points bands, the controls required at each level, the review intervals (6, 12 and 24
months) and the approval route are the hub's own policy, built on the frameworks above. They live in
`governance_hub/rules/risk.yaml` and `governance_hub/workflow.py`, and an organisation can change them.
