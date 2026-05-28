# Ограничения счетчиков профиля Impala

Last reviewed: 2026-05-26

Язык: [English](../../impala-profile-counter-caveats.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме будущего контракта по профилям Impala.

## Что важно

Профили Impala отличаются по версии, формату и доступным счетчикам. Query
Doctor должен явно определять диалект входного профиля и осторожно работать с
частично разобранными или экспериментальными форматами.

Будущие диалекты профиля:

- `classic_text_profile`;
- `classic_json_profile`;
- `classic_thrift_profile`;
- `experimental_profile_v2`;
- `unknown`.

Неизвестный или экспериментальный диалект должен давать ограниченный анализ
или parse-only режим, а не новые root-cause заявления.

## Стабильность счетчиков

Impala предоставляет метки стабильности счетчиков через `/profile_docs/?json`,
когда этот endpoint доступен; HTML `/profile_docs` остается compatibility
fallback. Это полезный машинно-читаемый сигнал, но не самостоятельное
доказательство причины.

Ожидаемое правило для будущей реализации:

- `STABLE_HIGH` может быть сильным профильным доказательством только при
  query-specific сигнале и детерминированной интерпретации analyzer;
- `STABLE_LOW` может быть средним или поддерживающим доказательством;
- `UNSTABLE` и `DEBUG` не должны сами повышать finding до root-cause;
- отсутствующие или немаркированные счетчики получают `UNKNOWN`;
- стабильность счетчика не заменяет пороги, deterministic analyzer logic и
  дополнительные query-specific сигналы, где они нужны.

Доверенные отчеты не должны показывать raw counter dumps. В будущем они могут
показывать безопасные резюме вроде "stable profile evidence" или
"unknown-stability supporting signal", если такие факты появятся в analyzer.

## Совместимость версий

Query Doctor должен иметь version-aware registry для счетчиков и aliases,
потому что имена счетчиков могут меняться между версиями Impala. Если live
использование `/profile_docs/?json` или HTML fallback недоступно либо не дает
метку для интерпретируемого счетчика, нужен bundled/versioned registry или
`UNKNOWN` stability.

## Resource trace

Текущий analyzer уже умеет разбирать allowlisted CPU, диск и сеть из
resource-trace samples в профиле Impala и превращать их в безопасные агрегаты.
Эти факты остаются `context_only`: отсутствие трасс считается `unknown`, общий
throughput хоста не доказывает причину сам по себе, а raw Per Node Profiles
rows и host identifiers не должны попадать в UI или trusted reports.
