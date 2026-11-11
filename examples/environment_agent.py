"""Exercise a real per-attempt SQLite environment without a hosted service.

Run ``python -m examples.environment_agent --attempts 3`` from the checkout.
Add ``--timeout-seconds 5`` to use a fresh deadline worker for every case.
The database starts with a deliberately dirty row: reset clears it before the
factory runs. The same database spans both conversation turns, and cleanup closes
its connection and removes its temporary directory, including after agent errors.
The external handle itself is never included in reports.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from thadam import FixtureAgent, FixtureTools, JSONValue, load_suite, run_repeated
from thadam.environment import EnvironmentHooks
from thadam.models import ExecutionLimits
from thadam.repetition_reporting import repeated_to_dict


@dataclass
class DatabaseEnvironment:
    """Trusted runtime handle; it is neither suite data nor report evidence."""

    directory: TemporaryDirectory
    connection: sqlite3.Connection


def setup() -> DatabaseEnvironment:
    """Allocate a database, releasing partial resources if setup fails."""
    directory = TemporaryDirectory(prefix="thadam-environment-")
    connection = None
    try:
        connection = sqlite3.connect(Path(directory.name) / "ledger.sqlite")
        connection.execute("CREATE TABLE refunds (order_id TEXT PRIMARY KEY, amount INTEGER)")
        connection.execute("INSERT INTO refunds VALUES ('dirty-before-reset', 999)")
        connection.commit()
        return DatabaseEnvironment(directory, connection)
    except BaseException:
        if connection is not None:
            connection.close()
        directory.cleanup()
        raise


def reset(environment: DatabaseEnvironment) -> None:
    """Clear external rows before this attempt's agent is constructed."""
    environment.connection.execute("DELETE FROM refunds")
    environment.connection.commit()


def cleanup(environment: DatabaseEnvironment) -> None:
    """Release the connection and directory even if closing the connection fails."""
    try:
        environment.connection.close()
    finally:
        environment.directory.cleanup()


def create(tools: FixtureTools):
    """Return a controlled conversation agent using this attempt's database."""
    environment = tools.environment
    if not isinstance(environment, DatabaseEnvironment):
        raise TypeError("Expected a SQLite environment")
    connection = environment.connection

    def agent(request: JSONValue) -> JSONValue:
        if not isinstance(request, dict):
            raise TypeError("Expected a conversation request")
        if request["turn_id"] == "inspect-reset":
            count = connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
            return {"refund_count": count}
        case_input = request["case_input"]
        connection.execute(
            "INSERT INTO refunds VALUES (?, ?)",
            (case_input["order_id"], case_input["amount_cents"]),
        )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
        # The explicit JSON state is observable evidence, independent of the
        # trusted database handle and its lifecycle.
        tools.state.write({"refund_count": count})
        return {"refund_count": count, "amount_cents": case_input["amount_cents"]}

    return agent


environment = EnvironmentHooks(setup, reset, cleanup)
AGENT = FixtureAgent(create, environment=environment)


def main() -> int:
    """Run the controlled suite repeatedly, optionally in deadline workers."""
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float)
    arguments = parser.parse_args()
    cases = load_suite(Path(__file__).with_name("environment_cases.json"))
    limits = (
        ExecutionLimits(timeout_seconds=arguments.timeout_seconds)
        if arguments.timeout_seconds is not None
        else None
    )
    report = run_repeated(AGENT, cases, attempts=arguments.attempts, limits=limits)
    print(json.dumps(repeated_to_dict(report), indent=2))
    return int(report.has_failures)


if __name__ == "__main__":
    raise SystemExit(main())
