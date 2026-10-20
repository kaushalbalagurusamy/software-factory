---
id: ml-evaluation
version: 0.1.0
title: ML and model evaluation validity
group: theory-measurement
owner: sf
scope: >-
  Judges whether a brief's model evaluation can be trusted: leakage through preprocessing or random
  splits of dependent data, uncalibrated scores used as probabilities, accuracy on imbalanced classes,
  benchmark contamination and in-distribution-only testing. Leaves rubric incentive design to
  rubric-inversion and model provider terms to provider-terms.
applies_when:
  signals: [ml model, trained model, the model, machine learning, classifier, classification, prediction, training data, train/test, test set, validation set, cross-validation, accuracy, precision, recall, f1 score, roc auc, pr-auc, auc-roc, benchmark, leaderboard, confidence score, predicted probability, risk score, calibrat, fine-tun, anomaly detect, fraud detect, forecast]
required_statements:
  - id: split-method
    statement: The brief states how evaluation data is separated from training data (chronological cutoff, entity-grouped split, or why i.i.d. random splitting is valid) and that all fitted preprocessing uses training data only.
  - id: calibration-target
    statement: Where model scores are shown or used as probabilities or confidence, the brief states the calibration method and the calibration error target measured on held-out data.
  - id: base-rates
    statement: The brief states the expected base rate of each class (or of the rare event) in deployment and the trivial baseline the model must beat.
adapters: [web_page, paper]
---

# ML and model evaluation validity

## Principles

- Leakage is using information unavailable at prediction time; it inflates offline estimates. Never fit
  anything, including preprocessing, on test data (sklearn-pitfalls).
- i.i.d. splitters are wrong for time-dependent or grouped data; use time-series or group-wise splits
  (sklearn-cv).
- Modern neural networks are poorly calibrated; only calibrated scores can be read as confidence
  (guo-2017, sklearn-calibration).
- Accuracy can beat chance only through class imbalance; balanced accuracy and precision-recall expose
  it, and ROC can mislead on imbalanced data (sklearn-metrics, saito-2015).
- Training on a benchmark's test split overstates performance (sainz-2023).
- In-distribution scores overstate out-of-distribution performance under real shifts (koh-2021).

## Questions a sweeper asks of each claim

- Is the data time-ordered, or are there several rows per customer, patient, device or document? How
  is it split? Which transforms are fitted, and on what rows?
- Are features available at the moment of prediction, or do they encode the outcome or the future?
- Is any score shown as a percentage, used as a probability in pricing, or used as an auto-approve
  threshold? Is it calibrated, on which data, against what target?
- What is the base rate of the positive class? What does the always-negative baseline score on the
  brief's metric?
- Is the evaluation set public, and could the model have seen it? Is it drawn from the deployment
  population, period and sites?

## Severity guidance

- Most traps here are measurement flaws: principal-reject (medium).
- Raise to high (production-failure) when the flawed number gates an automated decision with real
  consequences (credit, claims, clinical triage, fraud blocking) or the brief itself implies deployment
  to a shifted population.
- Pricing or underwriting on uncalibrated scores: material-exposure (high).
- Regulated uses (credit, health, employment) also go to the regulatory lenses; jurisdiction-dependent
  validation duties are ask-owner.

## Not this lens

- Rubric incentive design, proxy metrics, LLM-judge bias: rubric-inversion.
- Model and dataset licences, provider terms: licensing, provider-terms, copyright-data-rights.
- Fairness and discrimination law: ai-regulation, privacy-regulated-data.
