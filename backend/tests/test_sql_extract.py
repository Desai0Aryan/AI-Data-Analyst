import pytest

from app.sql_extract import extract_sql


@pytest.mark.parametrize("reply, expected", [
    ("```sql\nSELECT 1\n```", "SELECT 1"),
    ("Here you go:\n```sql\nSELECT 1;\n```\nHope it helps", "SELECT 1"),
    ("```SQL\nSELECT 1\n```", "SELECT 1"),
    ("```postgresql\nSELECT 1\n```", "SELECT 1"),
    ("```\nSELECT 1\n```", "SELECT 1"),
    ("```sql\nSELECT 1", "SELECT 1"),                       # truncated, unclosed fence
    ("SELECT 1;", "SELECT 1"),                              # bare SQL, no fence
    ("WITH a AS (SELECT 1) SELECT * FROM a", "WITH a AS (SELECT 1) SELECT * FROM a"),
    ("```sql\nSELECT 1\n```\nActually:\n```sql\nSELECT 2\n```", "SELECT 2"),   # last block wins
])
def test_extracts_sql(reply, expected):
    assert extract_sql(reply).sql == expected


def test_cannot_answer():
    p = extract_sql("CANNOT_ANSWER: There is no weather data in this schema.")
    assert p.sql is None and p.cannot_answer_reason == "There is no weather data in this schema."


@pytest.mark.parametrize("reply", ["", "I think the answer is 42.", "Sorry, I can't help"])
def test_no_sql(reply):
    p = extract_sql(reply)
    assert p.sql is None and p.cannot_answer_reason is None
