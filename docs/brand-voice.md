# Brand Voice And Humor Policy

Last reviewed: 2026-08-27

Query Doctor should read like a serious enterprise diagnostic tool. A little dry
engineering personality is allowed, but it must never compete with evidence,
safety, or trust.

Target balance:

```text
95% serious diagnostic product. 5% dry engineering wink.
```

## Core Position

The product voice is calm, technical, and conservative. Query Doctor can be
memorable around the edges, but diagnostic surfaces must stay factual and
evidence-bound.

Safe shorthand:

```text
Facts first. Drama never.
```

This is voice guidance, not a diagnostic claim.

## Allowed Surfaces

Small, dry humor is allowed only where it cannot be mistaken for evidence,
diagnosis, or safety behavior:

- public README and GitHub-facing copy;
- public release notes;
- community posts and demo talk tracks;
- dev-only documentation;
- optional CLI/help copy that does not report case facts;
- internal dev helper scripts and local maintainer notes.

Use it sparingly. One short line is usually enough.

## Disallowed Surfaces

Do not add humor, persona, parody, or playful language to:

- trusted reports;
- analyzer findings or analyzer-owned facts;
- diagnostic conclusions, root-cause wording, and evidence quality;
- score reasons, action candidates, and follow-up checks;
- report validation, optimizer validation, and trust markers;
- validation errors, safety warnings, and security/privacy guidance;
- browser-visible dynamic case details;
- Query Optimizer results and no-rewrite/recommendations-only outcomes;
- collector, metadata, metric, event, or runtime context status text.

If text could change how a user interprets diagnostic certainty, keep it plain.

## Style Rules

- Clarity wins over personality.
- Keep humor short, dry, technical, and secondary.
- Avoid political parody, public-persona imitation, sarcasm, memes, insults, or
  jokes at a user's expense.
- Do not joke about outages, data loss, production incidents, security, privacy,
  or failed validation.
- Do not use humor to soften unsupported claims. Say `unknown` when evidence is
  missing.
- Do not use runtime context or duration alone to imply a root cause.
- Do not expose or hint at raw SQL, raw profiles, raw metadata, hostnames,
  daemon ids, local paths, secrets, model/runtime internals, command output, or
  raw artifact filenames.

## Example Lines

These are suitable only for allowed outer surfaces:

- `Diagnosis before drama.`
- `Facts first. Drama never.`
- `No vibes-based root causes.`
- `Spill happens. We find out why.`
- `Python finds facts. LLM writes words. Nobody makes things up.`

Do not paste these into generated reports, diagnostic results, validation
messages, safety warnings, or analyzer output.

Avoid meme-like slogans in core project documentation, even when they are
technically safe. For example, `Make Queries Boring Again` may fit an informal
conference slide or private demo note, but not README, trusted reports, safety
docs, or diagnostic UI.

## Review Checklist

Before adding a line with personality, ask:

- Is this an allowed outer surface?
- Could a user mistake it for a diagnostic claim?
- Does it weaken a safety, privacy, or validation warning?
- Would it look unprofessional during a production incident?
- Does it stay raw-free and evidence-neutral?

If any answer is uncertain, remove the humor.
