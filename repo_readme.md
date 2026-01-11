# AI-NEO — Adaptive Diagnostic System for Human Potentials

AI-NEO is an adaptive, interview-based AI diagnostic system built on the NEO Potentials Methodology.  
It replicates the logic of a deep 1–1.5 hour master diagnostic session using structured knowledge, adaptive questioning, and evidence-based reasoning.

The system is designed to:
- identify natural human potentials,
- detect energy sources, restoration zones, and weaknesses,
- reveal hidden shifts (biases, distortions),
- generate clear, practical reports for both client and master.

---

## 🧠 Core Concept

The system operates on a 3×3 matrix:

### Energy Rows
- Row 1 — Strengths (natural development, energy gain)
- Row 2 — Energy / Resource (restoration, hobbies, balance)
- Row 3 — Weaknesses (energy drain, delegation zones)

### Application Columns
- Material sphere
- Emotional sphere
- Meaning / Cognitive sphere

Their intersections form 9 core potentials (defined in `knowledge/positions.md`).

---

## 📁 Repository Structure
ai-neo/
│
├─ prompts/
│   └─ system.txt              # Main AI system prompt (interviewer logic)
│
├─ knowledge/
│   ├─ positions.md            # 9 potentials + row/column meanings
│   ├─ shifts.md               # Shift types, bias patterns, distortions
│   ├─ methodology.md          # Diagnostic logic & decision rules
│   ├─ question_bank.md        # Allowed questions ONLY (no invention)
│   └─ examples_transcripts.md # Real master-style interview examples
│
├─ configs/
│   └─ diagnosis_config.json   # Thresholds, limits, confidence rules
│
├─ reports/
│   ├─ client_report.md        # Client-facing report template
│   ├─ master_report.md        # Practitioner report template
│   └─ corporate_report.md     # (optional) Team / HR usage
│
├─ app.py                      # Application entry point (Streamlit / API)
├─ requirements.txt            # Python dependencies
└─ repo_readme.md              # This file
---

## 🔒 Design Rules (Very Important)

1. No invented questions
   - AI may ask ONLY questions that exist verbatim in question_bank.md.
   - Adaptive logic decides *which* question to ask next, not *how to rewrite it*.

2. One question at a time
   - Interview format, not a static survey.
   - Mimics real master diagnostics.

3. Evidence-based reasoning
   - Every conclusion must be supported by:
     - answers,
     - behavioral markers,
     - childhood signals,
     - shift checks.

4. Shift awareness
   - If a shift is detected (social desirability, survival strategy, trauma compensation),
     confidence is reduced and clarified via additional questions.

5. Early stop logic
   - The system stops once confidence thresholds are reached,
     or maximum question count is exceeded.

---

## 🧩 Outputs

The AI produces three synchronized outputs:

### 1. Client Report
- Recognition (“this is you”)
- Strengths, energy sources, weak zones
- Practical life & realization hints
- Gentle guidance (no overload, no therapy)

### 2. Master Report
- Full matrix placement
- Evidence mapping (answer → potential)
- Contradictions and resolution logic
- Shift analysis
- Confidence scores

### 3. Scores Matrix
- 3×3 table with short rationales per potential

---

## 🎯 Use Cases

- Individual self-development
- Coaching & mentoring
- Career and realization diagnostics
- Long-term personal programs (3–6 months)
- Team and corporate profiling (future extension)

---

## 🚀 Philosophy

AI-NEO is not a quiz.  
It is a thinking diagnostic system that behaves like a trained master:
- listening,
- narrowing,
- validating,
- correcting biases,
- and leading a person back to their natural strengths.

---

## 🛠 Status

Current focus:
- Finalizing knowledge base integrity
- Ensuring adaptive interview logic
- Stabilizing confidence and shift handling

Next stages:
- UI polishing
- Telegram / app integration
- Paid extended reports & programs

---

Created as a foundation for a scalable ecosystem of personal transformation tools.
