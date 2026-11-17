# Engineering Onboarding Guide

Welcome to Fernhill Labs engineering. This guide covers your first two weeks.

## First Week

### Accounts and Access

On day one, IT gives you access to GitHub, Linear, Slack, and the AWS console
(read-only). Request production access later through the `#access-requests`
Slack channel once you complete the security training.

### Development Environment

Clone the `platform` monorepo and run `make bootstrap`. This installs the pinned
toolchain via mise and starts local dependencies in Docker. If bootstrap fails,
post the error in `#dev-help` rather than debugging alone for hours.

### Your Onboarding Buddy

Every new engineer is paired with a buddy from another team for their first
month. Your buddy is your first stop for "where do I find..." questions and
will pair with you on your first ticket.

## Code Review

All changes go through pull requests and need one approval. Changes to payment
or authentication code need two approvals, one from the owning team listed in
`CODEOWNERS`. Reviewers should respond within one business day. Keep pull
requests under 400 changed lines where possible.

## Deployments

We deploy `main` to production continuously. Merging a pull request triggers a
deploy within about 15 minutes. Deploys are frozen from December 15 to January 2
except for incident fixes approved by the on-call lead.

## On-Call

Engineers join the on-call rotation after three months. A rotation lasts one
week, from Monday 10:00 to the following Monday 10:00. On-call engineers
receive a stipend of $400 per week and a replacement day off for any public
holiday worked. Page acknowledgement is expected within 15 minutes.
