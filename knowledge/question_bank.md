### ID: q_name
intent: ask_name
stage: stage0_intake
type: text
column: null
weight: 1.0

Вопрос:
Как тебя зовут?


### ID: q_request
intent: ask_request
stage: stage0_intake
type: text
column: null
weight: 1.0

Вопрос:
С каким запросом ты пришёл(пришла) на диагностику? Что сейчас хочется понять или изменить?


### ID: q_now_state
intent: current_state
stage: stage1_now
type: text
column: ВОСПРИЯТИЕ
weight: 1.1

Вопрос:
Если коротко: что сейчас в жизни больше всего не устраивает или забирает энергию?


### ID: q_energy_source
intent: energy_source
stage: stage1_now
type: text
column: МОТИВАЦИЯ
weight: 1.2

Вопрос:
А что, наоборот, в последнее время хоть немного наполняет или даёт ощущение «живу»?


### ID: q_childhood
intent: childhood_pattern
stage: stage2_childhood
type: text
column: МОТИВАЦИЯ
weight: 1.2

Вопрос:
В детстве (примерно 7–12 лет): чем ты мог(могла) заниматься часами и не уставать?


### ID: q_proud
intent: strength_validation
stage: stage3_hypothesis_checks
type: text
column: ИНСТРУМЕНТ
weight: 1.3

Вопрос:
За что тебя чаще всего хвалят или ценят другие люди?


### ID: q_avoid
intent: antipattern
stage: stage3_hypothesis_checks
type: text
column: ИНСТРУМЕНТ
weight: 1.2

Вопрос:
Какие задачи ты стабильно откладываешь или делаешь только «через надо»?


### ID: q_shift
intent: shift_probe
stage: stage4_shifts
type: text
column: null
weight: 1.3

Вопрос:
Бывает ли ощущение, что ты живёшь «не совсем свою жизнь» — делаешь многое из долга, а не из желания?


### ID: q_wrap
intent: wrap
stage: stage5_wrap
type: text
column: null
weight: 0.8

Вопрос:
Если представить, что через 3 месяца стало лучше — что именно изменилось бы в первую очередь?