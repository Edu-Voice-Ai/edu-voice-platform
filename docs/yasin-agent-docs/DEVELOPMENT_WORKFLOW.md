# Edu-Voice-Ai — Development Workflow

## Branching

```text
main
└── develop
    ├── feature/frontend/<task>
    ├── feature/backend/<task>
    ├── feature/ai/<task>
    └── feature/devops/<task>
```

## Standard Task Flow

1. Pull latest `develop`.
2. Create a feature branch.
3. Inspect relevant existing code and documentation.
4. Define the smallest coherent change.
5. Implement.
6. Run relevant tests/checks.
7. Inspect `git diff`.
8. Commit with a clear message.
9. Push feature branch.
10. Open PR into `develop`.
11. Address review feedback.
12. Merge only after checks/review pass.

## Commit Principles

Commits should:
- be focused
- describe the change
- avoid unrelated formatting/refactors
- not contain secrets

## Pull Requests

A PR should explain:
- what changed
- why
- affected modules
- tests run
- configuration changes
- database migrations
- API contract changes
- known limitations

## Cross-Team Changes

Coordinate when changing:
- API contracts
- database schemas
- shared types
- authentication behavior
- tenant isolation
- infrastructure interfaces
- AI/voice interfaces

## Environment Rules

Use environment variables for secrets and environment-specific configuration.

Never commit real:
- API keys
- passwords
- tokens
- AWS credentials
- Exotel credentials
- provider secrets

Keep `.env.example` safe and non-secret.

## Agent Completion Report

Every coding agent should report:
- branch
- files changed
- implementation summary
- tests/checks run
- assumptions
- cross-team impacts
- unresolved issues
