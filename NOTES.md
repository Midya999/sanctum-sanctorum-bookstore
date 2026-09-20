# Submission Notes

## Implementation Summary

Completed the missing and incomplete bookstore backend functionality described in
`SPEC.md`.

The implementation covers:

- Book creation, ISBN-13 validation and normalization
- Duplicate ISBN handling
- Book updates and listing
- Book filtering, sorting and pagination
- Member creation and email normalization
- Duplicate member email handling
- Membership tier rules
- Order creation and pricing
- Tier and bulk discounts
- Stock reservation and restoration
- Order payment and cancellation
- Library loans and borrowing restrictions
- Loan limits and overdue handling
- Returns and late-fee calculation
- Member statistics
- Top-selling book reports

## Architecture

The application keeps the FastAPI routers thin and places business rules
inside the service layer.

- `app/routers/` handles HTTP requests, dependencies and response models.
- `app/services/` contains business logic and database operations.
- `app/schemas.py` contains request/response validation and serialization rules.
- `app/models.py` contains SQLAlchemy ORM models.

This separation makes the business rules easier to test independently from
the HTTP layer.

## Validation and Data Integrity

Field-level validation is handled by Pydantic schemas where appropriate.
For example, ISBN-13 values are normalized and their checksum is validated
before reaching the service layer.

Database uniqueness violations are translated into HTTP `409 Conflict`
responses rather than exposing raw database exceptions.

Order creation validates all required conditions before modifying stock so
that an unsuccessful order does not leave partially reserved inventory.

Loan and order status transitions are also validated in the service layer.

## Time Handling

The application uses the provided `get_now` dependency for current time
instead of calling `datetime.now()` directly. This keeps time-dependent
behaviour deterministic and testable.

## Testing

The complete test suite passes:

    202 passed, 2 warnings

The warnings originate from dependency deprecations involving the test
client and are not application test failures.

## AI Usage

AI assistance was used during development for:

- Understanding the existing project structure and requirements
- Interpreting failing tests
- Explaining FastAPI, Pydantic and SQLAlchemy behaviour
- Suggesting implementation approaches for incomplete service functions
- Reviewing implementation logic and debugging test failures
- Explaining why particular validation and transaction-handling approaches
  were appropriate

All generated suggestions were reviewed, implemented, and verified against
the project tests. The final code was tested locally with the provided
test suite.

One important part of the development process was validating suggestions
against the actual tests and project specification rather than assuming
that an AI-generated implementation was correct.

## Git History

The provided project copy did not contain a `.git` directory, and no Git
repository was found in the parent directories. Therefore the original
starter Git history was not available to preserve.

A new Git repository was initialized locally and the completed project was
committed as:

    Complete bookstore backend implementation

## Deployment

Public deployment URL:

> To be added after deployment.