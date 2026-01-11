# ai-neo — NEO Potentials Diagnostic System (MVP)

Этот репозиторий содержит структуру знаний, промпты и конфигурации для ИИ-диагностики по системе 9 потенциалов (матрица 3×3) с учетом:
- позиций потенциалов (в матрице и по рядам/столбцам),
- смещений (подсознательные программы/искажения),
- методологии проведения разбора (приближенно к мастер-разбору).

## Структура репозитория

```txt
ai-neo/
  app.py
  requirements.txt

  configs/
    diagnosis_config.json

  prompts/
    system.txt
    developer.txt

  knowledge/
    positions.md
    shifts.md
    methodology.md
    question_bank.md
    examples_transcripts.md

  reports/
    client_report.md
    master_report.md
    corporate_report.md
