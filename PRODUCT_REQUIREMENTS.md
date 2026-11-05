# Dexian Medical Doctor — Product Requirements

This document records the product direction. It is the reference for product
scope, safety boundaries, architecture, and future implementation decisions.

## 1. Product goal and boundaries

Dexian Medical Doctor is a two-mode, guideline-grounded medical information and
clinical decision-support prototype:

- **Patient mode** helps a person describe a concern, gathers relevant context, gives
  cautious health information, and helps them decide what kind of professional care
  to seek.
- **Doctor mode** helps a clinician retrieve and synthesize medical reference
  information, consider possible explanations, identify missing information, and
  review relevant questions or investigations.

The product supports, but does not replace, a qualified clinician. It must not claim
to be a doctor, provide definitive diagnosis, rule out serious disease, make
autonomous treatment decisions, or imply that it is clinically validated.

Patient and doctor modes must be visibly distinct. A mode selection is not proof of
identity, professional status, or authorization. Until real authentication and
deployment controls are designed, doctor mode is a prototype feature and must not
be represented as a verified professional service.

## 2. Patient mode

### Purpose

Provide empathetic, plain-language symptom navigation grounded in retrieved
guidelines. Help the patient understand what information is relevant and how to seek
appropriate professional care. Do not attempt to become the patient's doctor.

### Conversation behavior

- Support multi-turn conversations and retain relevant context within the current
  conversation.
- Ask one short, relevant follow-up question at a time when key information is missing
  or ambiguous. For example, clarify symptom location, onset, duration, injury, or
  associated symptoms as relevant to the concern.
- Use previous answers, avoid repeating answered questions, and acknowledge
  corrections or contradictory details.
- Distinguish facts the patient reported from uncertain or missing information. Never
  fill gaps with assumptions.
- Do not keep asking questions indefinitely in pursuit of diagnostic certainty. When
  enough context is available for safe general guidance, explain limits and next
  steps; if uncertainty remains, say so and recommend appropriate professional
  assessment.
- Keep replies natural, direct, empathetic, concise, and free of unnecessary medical
  jargon or repetitive disclaimers.

### Permitted assistance

- Explain retrieved medical information in accessible language.
- Help the patient prepare a concise summary of symptoms, timing, relevant history,
  and questions to bring to a clinician.
- Give general guidance about the appropriate level or type of professional care
  only when supported by a clinician-reviewed policy and applicable evidence.
- Explain that a clinician may decide whether examination, imaging, or laboratory
  tests are appropriate. Do not prescribe a test panel or imply the patient should
  order tests independently.

### Prohibited behavior

- Do not tell a patient they have a specific disease as a diagnosis, claim certainty,
  eliminate diagnostic possibilities, or provide unvalidated diagnostic percentages.
- Do not recommend starting, stopping, or changing medicines or individualized
  treatment.
- Do not advise delay of care when a reviewed safety rule indicates escalation.
- Do not infer that a patient is safe merely because they did not mention a warning
  sign.

## 3. Doctor mode

### Purpose

Act as a reference-retrieval and clinical reasoning support tool for a clinician who
remains responsible for assessment and decisions. It is not an autonomous diagnostic
or treatment system.

### Doctor profile and scope

- Allow a doctor profile to record specialty, relevant interests, preferred
  jurisdiction, and preferred guideline sources.
- Mark specialty and professional status as **self-reported** unless they have been
  verified through an explicitly designed, lawful verification process.
- Do not collect identity documents or other sensitive credential data in the local
  prototype.
- Compare the clinician's self-reported specialty with the case domain and retrieved
  references. Explain whether the question appears within, adjacent to, or outside
  that declared scope, and why.
- Scope feedback is advisory, not credential validation or a judgment of competence.
  For out-of-scope or unsupported cases, identify the limit and suggest consultation
  or referral for clinician consideration; do not block access to general reference
  information.

### Clinical information support

- Retrieve relevant textbook and guideline passages and present a concise synthesis
  with source citations, edition/version, jurisdiction, and page or section where
  available. Doctor mode should show citations by default so the clinician can verify
  claims.
- Separate retrieved evidence, reported case facts, model-generated interpretation,
  and unknown information. Never fabricate source details.
- Help identify missing history or examination details and propose focused questions
  that may clarify the case.
- Suggest potentially relevant investigations only as clinician-reviewable options.
  State the clinical question each option may help address, limitations, and
  guideline support when available. Do not claim a test is required, order tests, or
  substitute for local protocols or clinician judgment.
- Do not claim that a differential is exhaustive or that a condition has been ruled
  out.

### Diagnostic possibilities and probabilities

- The clinician may ask for a differential diagnosis or relative likelihoods; the
  system may assist only within a clearly defined and evaluated clinical domain.
- Never invent precise percentages from the language model's confidence, retrieved
  similarity scores, or informal reasoning. A numeric probability is allowed only
  when produced by a separately validated and calibrated method for the relevant
  population, setting, and use, with its provenance and limitations shown.
- If no such validated method exists, use qualitative, explicitly non-calibrated
  language (for example, "consider" or "less supported by the information provided")
  and explain which information is missing. Do not present qualitative rankings as
  measured probabilities.
- Any future probability feature requires clinical validation, calibration studies,
  subgroup performance assessment, governance approval, and ongoing monitoring
  before deployment.

## 4. Shared safety and escalation

- Apply a clinician-reviewed safety policy to both modes. Do not rely on a generative
  model alone to detect emergencies or decide escalation.
- When a reviewed escalation condition is met, give clear, calm direction to seek
  the level of urgent professional help defined by the approved policy. Do not
  continue routine questioning as though the situation were low risk.
- Safety policy content, escalation wording, and evaluation scenarios must be
  reviewed by qualified clinicians familiar with the intended population and care
  setting.
- Tests and model evaluations are necessary but are not proof of clinical safety.
- Do not make medical or legal compliance claims without documented review and
  approval from qualified professionals.

## 5. Evidence and citations

- Ground medical and guideline-related claims in retrieved, relevant source passages.
- **Patient mode:** do not show or announce citations by default. Provide source
  details when the patient asks, in a clear and understandable form.
- **Doctor mode:** show source citations by default to support verification and
  professional use.
- Keep provenance available internally in both modes. A citation must resolve to the
  actual supporting passage and its available source metadata.
- Never fabricate a citation, overstate what a passage supports, or silently treat
  embedding similarity as proof of clinical relevance.
- If relevant evidence is unavailable, outdated, conflicting, or not applicable to
  the selected jurisdiction, disclose that limitation and avoid unsupported claims.
- Track source title, issuing organization, edition/version, publication/update date,
  jurisdiction, and page/section when available. Define a review/update process for
  the corpus before professional reliance.

## 6. Egypt-specific legal, ethical, and clinical governance

Egypt is an intended jurisdiction, but this requirements document is not a legal
opinion and does not establish compliance with Egyptian law or medical ethics.

Before any real-patient or professional deployment in Egypt:

- Obtain review from qualified Egyptian healthcare counsel and practicing clinicians
  familiar with applicable Egyptian law, professional duties, medical ethics, and
  the intended clinical setting.
- Determine and document whether the product's functions or claims trigger medical
  device, health-service, professional-practice, or other regulatory obligations;
  obtain required approvals before deployment.
- Review applicable requirements for health and personal data, consent, processing,
  storage, access, retention, deletion, breach handling, and any cross-border
  processing. Do not assume local-only development settings satisfy these duties.
- Define who is accountable for clinical content, safety incidents, complaints,
  oversight, and changes to models, prompts, retrieval sources, and policies.
- Maintain an auditable record of approved clinical policies, source corpus versions,
  evaluations, known limitations, and release decisions, subject to privacy and
  retention review.
- Do not advertise the system as a doctor, a substitute for medical care, a validated
  diagnostic system, or legally compliant unless the appropriate evidence and
  approvals exist.

## 7. Conversation data, profiles, and privacy

- Store conversation messages and structured state separately from the Qdrant
  guideline index. Qdrant stores reference material, not patient conversation history.
- Scope every conversation read and write to its session. Do not leak context or
  profile data between patients, clinicians, or modes.
- Keep a concise, structured summary of relevant case details with explicit states
  such as reported, unknown, or uncertain. Do not turn missing information into a
  guessed fact.
- Separate patient case history from doctor profile data. Store only information
  needed for the function, and avoid unnecessary identifiers.
- For the initial local prototype, SQLite may be used behind a persistence boundary.
  This is a development choice, not a claim of production-grade security or
  suitability for identifiable health data.
- Before real-user deployment, define consent, access control, encryption, backup,
  retention and deletion, incident response, and applicable privacy review.
- Do not send identifiable patient information to a model provider or external
  service without an approved privacy, security, and legal review.

## 8. Technical architecture

- Keep retrieval of medical reference material separate from conversation and profile
  persistence.
- Add separate, explicit patient and doctor conversation flows, with mode-specific
  schemas, system instructions, response policies, and citation presentation.
- A client-selected mode is not authorization. Add appropriate authentication and
  authorization before enabling professional profiles or real patient data in a
  deployed service.
- Process each message in explicit stages: authenticate/resolve mode and session,
  load only authorized context, apply the reviewed safety policy, update structured
  state, retrieve applicable sources, validate a structured outcome, and persist the
  turn.
- Use structured outcomes such as `ask`, `answer`, and `escalate`; validate them
  before responding. Keep safety decisions and access control outside model-generated
  prose.
- Pass only relevant recent messages and a concise structured summary to the model,
  not an unbounded transcript.
- Keep retrieved references distinct from the profile, case facts, and generated
  interpretation. Use a source-appropriate corpus and jurisdiction filter.
- Keep dependencies such as safety policy, source index, model, and jurisdiction
  explicit and testable. Surface service and retrieval errors instead of returning
  success-shaped fallback answers.

## 9. Acceptance criteria

### Both modes

- Conversations retain relevant context within the correct session, with no cross-
  session or cross-mode leakage.
- The assistant asks one focused question when a material detail is missing, does
  not repeat answered questions, and preserves corrections and contradictions.
- Unknown information remains explicitly unknown; the system does not invent
  symptoms, history, or examination findings.
- Unsupported questions produce a clear evidence limitation rather than an
  unsupported medical claim.
- Reviewed escalation scenarios produce the approved behavior.

### Patient mode

- Replies are concise, empathetic, plain-language, and do not show citations unless
  requested.
- It does not present a definitive diagnosis, diagnostic certainty, or unvalidated
  numeric probabilities.
- When the conversation cannot safely resolve the concern, it explains uncertainty
  and offers clinician-reviewed care-navigation guidance rather than asking questions
  indefinitely.

### Doctor mode

- The profile distinguishes self-reported specialty from verified status.
- Scope feedback is clearly advisory and explains its basis and limitations.
- Medical claims have inspectable citations by default.
- Missing-information questions and investigation suggestions are tied to a clinical
  question and supporting evidence where available; they remain suggestions for
  clinician judgment.
- Numeric diagnostic probabilities are absent unless a separately validated,
  calibrated, applicable method has been approved and its limits are displayed.

### Release gates

- Tests cover mode separation, session isolation, context carryover, profile access,
  missing and contradictory details, citation behavior, unsupported questions, and
  reviewed escalation scenarios.
- Qualified clinician review is required for safety policies, clinical evaluation
  cases, and any diagnostic-support feature.
- Qualified Egyptian legal and clinical review is required before making claims of
  compliance or using the product with real patients or clinicians in Egypt.

## 10. Delivery order

1. Keep the current single-turn prototype clearly labeled as non-clinical and avoid
   claims of diagnosis or professional readiness.
2. Agree and document the precise patient-mode and doctor-mode interaction contracts.
3. **Implemented in the local prototype:** persist separate chat threads in SQLite,
   isolate each thread's context, keep recent turns, and summarize older turns for
   bounded model context. This does not yet establish production security or privacy.
4. Implement patient mode with clarifying questions, concise responses, citations on
   request, and clinician-reviewed escalation.
5. Implement doctor profiles with self-reported specialties and clear advisory scope
   feedback; add authentication before storing sensitive professional or case data.
6. Build and govern a versioned reference corpus suitable for doctor-mode retrieval;
   add citations by default and jurisdiction-aware filtering.
7. Evaluate doctor-mode reasoning support, missing-information prompts, and
   investigation suggestions with qualified clinicians.
8. Do not implement diagnostic percentages until a validated, calibrated,
   population-appropriate method and governance approval exist.
9. Complete Egyptian legal, privacy, security, clinical, and regulatory reviews
   before real-user deployment.

## 11. Current implementation status

The current local prototype has a browser chat interface, persistent SQLite
conversation threads, session-scoped recent-message context, and model-generated
summaries of older turns. It also retains the original single-turn `/api/ask`
endpoint, Qdrant retrieval, and Ollama answer generation. In the chat interface,
sources are hidden unless requested; the legacy endpoint still returns its source
metadata. It does not distinguish patient and doctor modes or implement doctor
profiles. It has no clinician-reviewed escalation policy, validated diagnostic
probability method, authentication, or Egypt-specific legal and clinical approval.
SQLite chat history is local and unencrypted. These requirements describe the target,
not clinical validation or regulatory approval.
