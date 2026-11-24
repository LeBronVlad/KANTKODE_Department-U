import unittest
from unittest.mock import patch

from src.api import fetch_vacancies


class FakeResponse:
    def __init__(self, items):
        self.items = items

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": "200", "results": {"vacancies": self.items}}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params, timeout):
        self.calls.append(params.copy())
        offset = params["offset"]
        if offset == 0:
            return FakeResponse([{"vacancy": {"id": "A"}}, {"vacancy": {"id": "B"}}])
        return FakeResponse([{"vacancy": {"id": "C"}}])


class ApiTests(unittest.TestCase):
    def test_offset_advances_by_number_of_received_records(self):
        session = FakeSession()
        with patch("src.api.requests.Session", return_value=session):
            result = fetch_vacancies("https://example.invalid", 3, 2, 5)
        self.assertEqual([x["vacancy"]["id"] for x in result], ["A", "B", "C"])
        self.assertEqual([call["offset"] for call in session.calls], [0, 2])


if __name__ == "__main__":
    unittest.main()
