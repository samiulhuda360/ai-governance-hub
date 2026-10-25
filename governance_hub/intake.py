"""The intake form: what a member of staff tells the hub about an AI use case.

Every field has a plain-words question (shown on the form) so the same text drives the web form, the model
pre-fill prompt and the labelling guide for the evaluation set.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Region = Literal["EU", "UK", "AU", "NZ", "US", "other"]
DataCategory = Literal["personal", "health", "financial", "children", "biometric", "confidential"]
Affected = Literal["staff", "customers", "public"]
DecisionMode = Literal["suggests", "acts_with_review", "fully_automatic"]

REGIONS: dict[str, str] = {
    "EU": "European Union / EEA",
    "UK": "United Kingdom",
    "AU": "Australia",
    "NZ": "New Zealand",
    "US": "United States",
    "other": "Somewhere else",
}

DATA_CATEGORIES: dict[str, str] = {
    "personal": "Personal information about identifiable people (names, emails, records, recordings)",
    "health": "Health information (medical, sickness, disability, wellbeing)",
    "financial": "People's financial information (income, debts, bank or card details, credit history)",
    "children": "Information about children (under 18)",
    "biometric": "Biometric data (faces, fingerprints, voiceprints or other body measurements)",
    "confidential": "Confidential business information (contracts, prices, plans, source code)",
}

AFFECTED: dict[str, str] = {
    "staff": "Our own staff or contractors",
    "customers": "Our customers or their people",
    "public": "Members of the public",
}

DECISION_MODES: dict[str, str] = {
    "suggests": "The AI suggests, and a person decides",
    "acts_with_review": "The AI acts, and a person reviews afterwards or spot-checks",
    "fully_automatic": "Fully automatic: no person looks at each outcome",
}

# The kind of job the AI does. Plain words first; several map to EU AI Act Annex III areas.
USE_AREAS: dict[str, str] = {
    "general_productivity": "Everyday office help: drafting, summarising, searching our own documents, coding help",
    "customer_service": "Talking with customers or the public (chat assistant, email replies, phone bot)",
    "content_generation": "Creating images, video, audio or text that will be published",
    "analytics_forecasting": "Forecasting, planning or optimising operations (demand, routes, stock), not about individuals",
    "document_processing": "Reading and sorting documents or forms (invoices, customs papers, claims)",
    "marketing_personalisation": "Personalising offers, ads or recommendations for people",
    "fraud_detection": "Spotting fraud or financial crime",
    "recruitment": "Hiring: advertising jobs to people, screening CVs, ranking or interviewing candidates",
    "workforce_management": "Managing staff: allocating work, monitoring or rating performance, promotion, dismissal",
    "credit_scoring": "Deciding whether a person can get credit, or their credit score",
    "insurance_pricing": "Setting insurance prices or assessing insurance risk for people",
    "public_benefits": "Deciding who gets public benefits or public services",
    "emergency_triage": "Sorting emergency calls, dispatching emergency services, or triaging patients in an emergency",
    "education_assessment": "Education: admissions, marking, placing students at a level, or watching students in exams",
    "critical_infrastructure": "Safety-critical control of utilities, road traffic or critical digital infrastructure",
    "biometric_identification": "Recognising who a person is from their face, voice or body (matching against many people)",
    "biometric_verification": "Confirming a person is who they say they are (one-to-one check, such as face unlock)",
    "biometric_categorisation": "Sorting people into groups from their face, voice or body",
    "emotion_recognition": "Detecting people's emotions or intentions from their face, voice or body",
    "law_enforcement": "Work for or on behalf of the police or other law-enforcement bodies",
    "migration_border": "Migration, asylum, visas or border control",
    "justice_democracy": "Courts, legal disputes, or elections and voting",
    "medical": "Health care for patients (diagnosis, treatment, monitoring)",
    "other": "Something else",
}

# Yes/no questions that catch the exceptions and special cases in the EU AI Act.
FLAGS: dict[str, str] = {
    "about_individuals": "Does it make or support decisions about individual people (not about companies or things)?",
    "profiling": "Does it build a picture of individual people (their behaviour, performance, preferences, reliability)?",
    "interacts_with_people": "Will people talk to it or read its replies directly, without a person in between?",
    "generates_synthetic_media": "Does it create images, audio, video or text that others will see?",
    "deepfake": "Could its output look like a real person, place or event that did not happen?",
    "narrow_procedural_task": "Does it only do a narrow, preparatory or checking task, with people doing the real assessment?",
    "safety_component": "Is it a safety part of a regulated product (machinery, vehicles, medical devices, lifts, toys)?",
    "workplace_or_education": "Is it used on staff at work, or on students in education?",
    "medical_or_safety_reason": "Is it used only for a medical or safety reason (for example to prevent accidents)?",
    "infers_sensitive_traits": "Does it guess race, religion, politics, trade-union membership or sex life from people's data?",
    "manipulative": "Does it use hidden or deceptive techniques to change what people do, in a way that could harm them?",
    "exploits_vulnerability": "Does it target people's age, disability or difficult social or money situation to change their behaviour?",
    "social_scoring": "Does it score people on their social behaviour or personality, with bad treatment elsewhere as a result?",
    "crime_prediction_profiling": "Does it predict whether a person will commit a crime from their profile or personality alone?",
    "face_scraping": "Does it build a face database by collecting images from the internet or CCTV without targeting?",
    "real_time_public_biometric": "Is it live face or body recognition in public places for law enforcement?",
    "public_service_deployer": "Are we a public body, or a private body providing a public service?",
}


class Intake(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    purpose: str = Field(min_length=3, max_length=2000)
    team: str = Field(min_length=1, max_length=80)
    use_area: str = "general_productivity"
    data_categories: list[DataCategory] = Field(default_factory=list)
    affected: list[Affected] = Field(default_factory=list)
    decision_mode: DecisionMode = "suggests"
    vendor: str = ""
    model: str = ""
    processing_region: Region = "EU"
    people_regions: list[Region] = Field(default_factory=list)
    org_regions: list[Region] = Field(default_factory=list)
    expected_users: int = Field(default=0, ge=0, le=1_000_000)
    hours_saved_per_week: float = Field(default=0.0, ge=0, le=100_000)
    flags: list[str] = Field(default_factory=list)

    def has(self, flag: str) -> bool:
        return flag in self.flags

    def personal(self) -> bool:
        """True when any category of information about people is involved."""
        return any(c in self.data_categories for c in ("personal", "health", "financial", "children", "biometric"))


def validate_choices(intake: Intake) -> list[str]:
    """Problems that pydantic's types do not catch: unknown use area or flag names."""
    problems = []
    if intake.use_area not in USE_AREAS:
        problems.append(f"unknown use area {intake.use_area!r}")
    problems += [f"unknown flag {f!r}" for f in intake.flags if f not in FLAGS]
    return problems
