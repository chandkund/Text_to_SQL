"""Evaluate Gemini-generated SQL against the hand-written Pagila answers."""

import json
import argparse
import time
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp

import main

TESTS_PATH = Path(__file__).with_name("tests.json")
RESULTS_PATH = Path(__file__).with_name("eval_results.json")
PAUSE_SECONDS = 2


def run_query(sql: str, connection=None):
    """Run one query with the same timeout used by the API."""
    close_connection = connection is None
    connection = connection or main.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute(sql)
            rows = [tuple(row) for row in cursor.fetchall()]
        connection.commit()
        return rows
    except Exception:
        connection.rollback()
        raise
    finally:
        if close_connection:
            connection.close()


def has_order_by(sql: str) -> bool:
    parsed = sqlglot.parse_one(sql, read="postgres")
    return isinstance(parsed, exp.Expression) and parsed.find(exp.Order) is not None


def normalize(value):
    """Make supported database values comparable and JSON serializable."""
    return main.json_value(value)


def result_key(row):
    return json.dumps([normalize(value) for value in row], sort_keys=True, default=str)


def results_match(generated_rows, gold_rows, ordered):
    generated = [tuple(normalize(value) for value in row) for row in generated_rows]
    gold = [tuple(normalize(value) for value in row) for row in gold_rows]
    if ordered:
        return generated == gold
    return Counter(result_key(row) for row in generated) == Counter(result_key(row) for row in gold)


def check_gold_queries(tests):
    """Check every reference query before spending time on LLM evaluations."""
    failures = []
    connection = main.get_connection()
    try:
        for test in tests:
            try:
                run_query(test["gold_sql"], connection)
                print(f"PASS (gold SQL): {test['question']}")
            except Exception as exc:
                failures.append((test["question"], str(exc)))
                print(f"FAIL (gold SQL): {test['question']} - {exc}")
    finally:
        connection.close()
    print(f"Gold SQL check: {len(tests) - len(failures)}/{len(tests)} passed")
    return failures


def main_eval(check_gold_only=False):
    test_data = json.loads(TESTS_PATH.read_text(encoding="utf-8"))
    tests = test_data["tests"]
    off_topic_tests = test_data["off_topic_tests"]
    if check_gold_only:
        failures = check_gold_queries(tests)
        return 1 if failures else 0

    # Initialize schema prompt and Gemini client for direct function calls.
    main.load_schema_and_client()
    database_details = []
    database_passed = 0

    for index, test in enumerate(tests):
        question = test["question"]
        generated_sql = ""
        status = "FAIL"
        error = None
        connection = None
        try:
            generated = main.generate_sql(question)
            generated_sql = generated["sql"]
            if not generated_sql:
                raise ValueError("Model marked this Pagila question as off-topic")
            generated_sql = main.validate_sql(generated["sql"])
            connection = main.get_connection()
            generated_rows = run_query(generated_sql, connection)
            gold_rows = run_query(test["gold_sql"], connection)
            if results_match(generated_rows, gold_rows, has_order_by(test["gold_sql"])):
                status = "PASS"
                database_passed += 1
        except Exception as exc:
            error = str(exc)
        finally:
            if connection is not None:
                connection.close()

        print(f"{status}: {question}")
        result = {
            "question": question,
            "generated_sql": generated_sql,
            "gold_sql": test["gold_sql"],
            "result": status,
        }
        if error:
            result["error"] = error
        database_details.append(result)

        # Pause between all LLM calls so consecutive requests do not hit rate limits.
        if index < len(tests) - 1 or off_topic_tests:
            time.sleep(PAUSE_SECONDS)

    off_topic_details = []
    off_topic_passed = 0
    for index, test in enumerate(off_topic_tests):
        question = test["question"]
        generated_sql = None
        off_topic = None
        status = "FAIL"
        error = None
        try:
            generated = main.generate_sql(question)
            generated_sql = generated["sql"]
            off_topic = not generated_sql
            if off_topic == test["expected_off_topic"]:
                status = "PASS"
                off_topic_passed += 1
        except Exception as exc:
            error = str(exc)

        print(f"{status}: {question}")
        result = {
            "question": question,
            "generated_sql": generated_sql,
            "expected_off_topic": test["expected_off_topic"],
            "off_topic": off_topic,
            "result": status,
        }
        if error:
            result["error"] = error
        off_topic_details.append(result)

        if index < len(off_topic_tests) - 1:
            time.sleep(PAUSE_SECONDS)

    database_accuracy = (database_passed / len(tests) * 100) if tests else 0
    off_topic_accuracy = (off_topic_passed / len(off_topic_tests) * 100) if off_topic_tests else 0
    RESULTS_PATH.write_text(
        json.dumps({
            "database_tests": database_details,
            "off_topic_tests": off_topic_details,
            "database_accuracy": database_accuracy,
            "off_topic_accuracy": off_topic_accuracy,
        }, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Database accuracy: {database_accuracy:.1f}% ({database_passed}/{len(tests)})")
    print(f"Off-topic accuracy: {off_topic_accuracy:.1f}% ({off_topic_passed}/{len(off_topic_tests)})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-gold", action="store_true",
        help="Run the reference SQL queries against the database without calling Gemini",
    )
    args = parser.parse_args()
    raise SystemExit(main_eval(check_gold_only=args.check_gold) or 0)
