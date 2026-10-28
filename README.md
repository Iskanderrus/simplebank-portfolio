# SimpleBank

A local banking API demo built with Django, Django REST Framework and PostgreSQL. It illustrates account registration, balance and transaction history, and transfers between accounts. This is a portfolio project for learning and evaluation; it is not a production banking service.

## Engineering choices

- Money is represented with decimal values and serialized as strings.
- Transfers update both accounts and their transaction records in one database transaction. Account rows are locked in a consistent order to manage concurrent transfers.
- Account numbers are unique text identifiers, preserving leading zeroes.
- A service layer separates transfer and registration logic from HTTP handling.
- The test suite includes HTTP flow and concurrent-transfer coverage against PostgreSQL.

## Business rules

- Registering opens one account and books a 10,000.00 welcome credit as a visible `CREDIT` transaction.
- A transfer debits the sender the amount plus a fee of 2.5% of the amount (rounded half up to the cent, minimum 5.00); the receiver gets the amount. The sender's balance cannot go negative.
- Amounts are positive, have at most two decimal places and are sent as JSON strings.

## Local setup

Requires Docker and Docker Compose:

```sh
docker compose up -d db
docker compose run --rm web python manage.py migrate
docker compose up -d web
```

The API runs at `http://localhost:8000`. Stop it with `docker compose down` (add `-v` to also delete the database volume). The Compose setup uses Django's development server, debug mode and a disposable development secret; use it locally only.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/v1/auth/register/` | Register an account |
| POST | `/api/v1/auth/login/` | Obtain an authentication token |
| GET | `/api/v1/account/` | Read the authenticated user's account |
| GET | `/api/v1/transactions/` | Read transaction history; optional `from` and `to` dates |
| POST | `/api/v1/transfers/` | Transfer to another account |

Authenticated requests use `Authorization: Token <token>`. See the tests for request and response examples. A quick walk-through:

```sh
curl -s -X POST localhost:8000/api/v1/auth/register/ -H 'Content-Type: application/json' \
  -d '{"email": "alice@example.com", "password": "<a strong password>"}'
curl -s -X POST localhost:8000/api/v1/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email": "alice@example.com", "password": "<a strong password>"}'   # {"token": "..."}
curl -s -X POST localhost:8000/api/v1/transfers/ -H 'Authorization: Token <token>' \
  -H 'Content-Type: application/json' -d '{"account_number": "<receiver>", "amount": "100.00"}'
```

## Tests

```sh
docker compose run --rm web pytest
```

The suite needs PostgreSQL (Compose starts the `db` service) and creates a separate test database. A full run took about three minutes in a clean checkout.

## Limitations

This demo has no idempotency key for transfers: retrying a successful request after a lost response can transfer funds twice. Tokens do not expire; history is not paginated; authenticated users can probe account numbers; and the default request parser has a deep-nesting hardening gap on authentication endpoints. The ledger is append-only at the application level, not immutable against direct database or bulk ORM changes. It has no production deployment configuration or CI workflow.
