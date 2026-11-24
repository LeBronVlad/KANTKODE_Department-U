import unittest

from src.analyzer import rule_issues, validate_ai_issue, analyze_vacancies


class AnalyzerTests(unittest.TestCase):
    def test_minimum_salary_is_not_flagged_for_missing_maximum(self):
        vacancy = {
            "id": "T1", "job-name": "Оператор", "salary_min": 35000,
            "salary_max": 0, "duty": "Ввод данных",
            "schedule": "5/2, 09:00–18:00",
            "employment": "Полная занятость",
            "requirement": {"qualification": "Внимательность"},
            "addresses": {"address": [{"location": "г. Калининград"}]},
        }
        issues = rule_issues(vacancy)
        self.assertFalse(any(x["topic"] == "Оплата" for x in issues))

    def test_remote_office_conflict_is_reported_once(self):
        vacancy = {
            "id": "T2", "job-name": "Оператор",
            "duty": "Работа полностью дистанционная из любого города.",
            "schedule": "5/2", "employment": "Полная занятость",
            "requirement": {"qualification": "Обязательное ежедневное присутствие в офисе."},
            "salary_min": 30000,
            "addresses": {"address": [{"location": "г. Калининград"}]},
        }
        issues = rule_issues(vacancy)
        matches = [x for x in issues if "дистанционная" in x["problem"] or "формат работы" in x["problem"]]
        self.assertEqual(len(matches), 1)

    def test_nested_address_is_read(self):
        vacancy = {
            "id": "T3", "job-name": "Библиотекарь",
            "duty": "Выдача книг", "schedule": "5/2",
            "employment": "Полная занятость", "salary_min": 30000,
            "requirement": {"qualification": "Среднее образование"},
            "addresses": {"address": [{"location": "г. Светлогорск, ул. Примерная, д. 3"}]},
        }
        issues = rule_issues(vacancy)
        self.assertFalse(any(x["topic"] == "Место работы" for x in issues))

    def test_ai_quote_must_exist_in_source(self):
        vacancy = {"job-name": "Бухгалтер", "duty": "Ведение первичной документации"}
        valid = {
            "topic": "Обязанности", "source_field": "duty",
            "quote": "Ведение первичной документации",
            "problem": "Не раскрыт объём документов",
            "recommendation": "Уточнить типы и объём документов"
        }
        invalid = dict(valid, quote="Работа с кассой")
        self.assertIsNotNone(validate_ai_issue(valid, vacancy))
        self.assertIsNone(validate_ai_issue(invalid, vacancy))

    def test_duplicate_ids_are_returned_once(self):
        raw = [
            {"vacancy": {"id": "D1", "job-name": "Кладовщик"}},
            {"vacancy": {"id": "D1", "job-name": "Кладовщик"}},
        ]
        report = analyze_vacancies(raw, use_ai=False)
        self.assertEqual(len(report["vacancies"]), 1)


if __name__ == "__main__":
    unittest.main()
