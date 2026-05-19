# Brand Voice And Humor Policy

Last reviewed: 2026-05-19

Язык: [English](../../brand-voice.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
правила тона для безопасных внешних поверхностей Query Doctor.

Query Doctor должен звучать как серьезный enterprise diagnostic tool. Небольшая
сухая инженерная интонация допустима на внешних и dev-only поверхностях, но не
должна конкурировать с evidence, safety или trust boundary.

Ориентир:

```text
95% serious diagnostic product. 5% dry engineering wink.
```

## Основная позиция

Тон продукта спокойный, технический и консервативный. Query Doctor может быть
запоминающимся по краям, но диагностические поверхности должны оставаться
фактическими и evidence-bound.

Короткая безопасная формула:

```text
Facts first. Drama never.
```

Это guideline по голосу продукта, а не diagnostic claim.

## Где допустима легкая интонация

Короткий сухой юмор допустим только там, где его нельзя принять за evidence,
diagnosis или safety behavior:

- public README и GitHub-facing copy;
- public release notes;
- community posts и demo talk tracks;
- dev-only documentation;
- optional CLI/help copy, которая не сообщает case facts;
- internal dev helper scripts и local maintainer notes.

Использовать редко. Обычно достаточно одной короткой строки.

## Где юмор запрещен

Не добавлять humor, persona, parody или playful language в:

- trusted reports;
- analyzer findings и analyzer-owned facts;
- diagnostic conclusions, root-cause wording и evidence quality;
- score reasons, action candidates и follow-up checks;
- report validation, optimizer validation и trust markers;
- validation errors, safety warnings и security/privacy guidance;
- browser-visible dynamic case details;
- Query Optimizer results и no-rewrite/recommendations-only outcomes;
- collector, metadata, metric, event или runtime context status text.

Если текст может изменить восприятие diagnostic certainty, оставлять его
простым и нейтральным.

## Правила стиля

- Clarity важнее personality.
- Humor должен быть коротким, сухим, техническим и вторичным.
- Избегать political parody, public-persona imitation, sarcasm, memes,
  insults или jokes at a user's expense.
- Не шутить про outages, data loss, production incidents, security, privacy или
  failed validation.
- Не использовать humor, чтобы смягчить unsupported claims. Если evidence нет,
  писать `unknown`.
- Не использовать runtime context или duration alone как root-cause hint.
- Не раскрывать и не намекать на raw SQL, raw profiles, raw metadata,
  hostnames, daemon ids, local paths, secrets, model/runtime internals, command
  output или raw artifact filenames.

## Примеры строк

Эти строки подходят только для разрешенных outer surfaces:

- `Diagnosis before drama.`
- `Facts first. Drama never.`
- `No vibes-based root causes.`
- `Spill happens. We find out why.`
- `Python finds facts. LLM writes words. Nobody makes things up.`

Не вставлять их в generated reports, diagnostic results, validation messages,
safety warnings или analyzer output.

Meme-like slogans не нужны в core project documentation, даже если они
формально безопасны. Например, `Make Queries Boring Again` может подойти для
informal conference slide или private demo note, но не для README, trusted
reports, safety docs или diagnostic UI.

## Review checklist

Перед добавлением строки с personality проверить:

- Это allowed outer surface?
- Пользователь может принять строку за diagnostic claim?
- Она ослабляет safety, privacy или validation warning?
- Она выглядела бы профессионально во время production incident?
- Она остается raw-free и evidence-neutral?

Если есть сомнение, убрать humor.
