---
id: ai-regulation
version: 0.2.0
title: AI-specific regulation
group: law-terms-ethics
owner: sf
scope: >-
  Judges brief claims about what an AI system does to people (infers, scores, decides, converses, collects
  biometrics) against AI-specific law, currently the EU AI Act as amended. General personal-data law
  belongs to privacy-regulated-data; copyright duties of model providers belong to copyright-data-rights.
applies_when:
  signals: [emotion, sentiment of staff, engagement score, webcam, facial, face recognition, biometric, recruitment, hiring, job applicant, candidate screening, credit score, creditworthiness, loan decision, grade exams, grading, proctoring, student assessment, chatbot, voice agent, virtual assistant, automated decision, social scoring, eu ai act, high-risk, employees, students, talking to an ai, talking to a bot, is an ai, ai assistant, ai front desk, ai receptionist, ai agent, ai-generated, synthetic content, deepfake, conversational ai]
required_statements:
  - id: ai-act-classification
    statement: The brief states whether the AI system is used on people in the EU and, if so, its risk classification under the EU AI Act (prohibited, high-risk under Article 6, transparency-only, or minimal).
    never_out_of_scope: regulatory-duties
  - id: human-oversight
    statement: For any automated decision about a person (hiring, credit, grading, eligibility), the brief states who can review, override or halt it, and that decisions are logged.
    never_out_of_scope: regulatory-duties
  - id: ai-disclosure
    statement: For any conversational or voice AI facing the public, the brief states that users are told they are interacting with an AI.
adapters: [web_page]
---

# AI regulation

## Principles

- Some practices are banned outright. Emotion inference in workplaces and education (Article 5(1)(f))
  and untargeted facial-image scraping for recognition databases (Article 5(1)(e)) are prohibited,
  applicable since 2 February 2025, with the highest fine tier in Article 99(3) (`eu-ai-act`).
- Annex III uses are high-risk. Recruitment, credit scoring and evaluation of learning outcomes are
  listed (Article 6(2), Annex III). High-risk systems need automatic logs (Article 12(1)), effective human
  oversight (Article 14(1)); deployers assign competent overseers (Article 26(2)) and keep logs at least
  six months (Article 26(6)) (`eu-ai-act`).
- Dates moved. Regulation (EU) 2026/1744 sets 2 December 2027 for Annex III high-risk obligations and
  2 August 2028 for Annex I (`eu-ai-omnibus`). A later application date is not a design waiver: systems
  built now will be on the market then.
- People must know they are talking to an AI (Article 50(1)), from the general application date of
  2 August 2026 (`eu-ai-act`).
- Read the text, not summaries. The Regulation has been amended; refresh both sources and check for
  further amending acts before relying on a date.

## Questions a sweeper asks of each claim

- Does the system infer emotions, and of whom: employees, students, customers?
- Does it make or shape a decision listed in Annex III (hiring, credit, education, essential services,
  law enforcement, migration, justice, critical infrastructure)?
- Where are the logs, how long are they kept, and who can override or halt a decision?
- Does any interface converse with people, and does it say it is an AI?
- Does it collect facial images, and how: targeted enrolment or scraping?
- Are EU users or EU deployers in scope? If unclear, ask-owner.

## Severity guidance

Prohibited practices answer yes to the first policy question: critical, and the disposition is decline
or reframe. Annex III systems with no oversight or logs are critical when the brief targets EU use and
high otherwise (production failure once the obligations apply). Missing AI disclosure is high. Territorial
scope, Article 6(3) exemptions and the medical-or-safety exception turn on facts and law: ask-owner.

## Not this lens

- GDPR lawful basis, special-category data, transfers: privacy-regulated-data.
- General-purpose AI model provider duties on copyright and training summaries: copyright-data-rights.
- Model accuracy, calibration and bias measurement method: ml-evaluation.
- Professional duties of clinicians, lawyers and engineers: professional-duty.
