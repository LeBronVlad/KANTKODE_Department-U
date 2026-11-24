
import logging
import re
from difflib import SequenceMatcher

from src.ollama_client import ask_ollama


def get_path(data, *path):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(as_text(v) for v in value.values() if as_text(v))
    if isinstance(value, list):
        return " ".join(as_text(v) for v in value if as_text(v))
    return str(value).strip()


def normalize_text(value):
    return re.sub(r"\s+", " ", as_text(value)).strip().casefold()


def address_text(value):
    """Извлекает человекочитаемые адреса из вложенной структуры API."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("location"):
                found.append(as_text(node["location"]))
            else:
                for child in node.values():
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, str) and node.strip():
            found.append(node.strip())

    walk(value)
    return "; ".join(dict.fromkeys(x for x in found if x))


def salary_values(vacancy):
    salary = vacancy.get("salary")
    if salary not in (None, "", 0, "0"):
        return True, as_text(salary)

    minimum = vacancy.get("salary_min")
    maximum = vacancy.get("salary_max")
    min_valid = minimum not in (None, "", 0, "0", 0.0)
    max_valid = maximum not in (None, "", 0, "0", 0.0)

    if min_valid and max_valid:
        return True, f"{minimum} - {maximum}"
    if min_valid:
        return True, f"От {minimum}"
    if max_valid:
        return True, f"До {maximum}"
    return False, ""


def add_issue(issues, topic, field, quote, problem, recommendation):
    candidate = {
        "topic": topic,
        "source_field": field,
        "quote": quote or "",
        "problem": problem,
        "recommendation": recommendation,
    }

    key = (
        normalize_text(candidate["topic"]),
        normalize_text(candidate["source_field"]),
        normalize_text(candidate["problem"]),
    )

    for old in issues:
        old_key = (
            normalize_text(old.get("topic")),
            normalize_text(old.get("source_field")),
            normalize_text(old.get("problem")),
        )
        if key == old_key:
            return

    issues.append(candidate)


def rule_issues(v):
    issues = []

    title = as_text(v.get("job-name"))
    duty = as_text(v.get("duty"))
    schedule = as_text(v.get("schedule"))
    employment = as_text(v.get("employment"))
    address = address_text(v.get("addresses"))

    qualification = as_text(get_path(v, "requirement", "qualification"))
    experience = get_path(v, "requirement", "experience")

    # 1. Название должности.
    if not title:
        add_issue(
            issues,
            "Название должности",
            "job-name",
            "",
            "В вакансии не указано название должности.",
            "Добавить конкретное название должности."
        )
    elif normalize_text(title) in {
        "специалист", "работник", "сотрудник"
    }:
        add_issue(
            issues,
            "Название должности",
            "job-name",
            title,
            "Название слишком общее и не раскрывает специализацию.",
            "Уточнить направление работы и специализацию должности."
        )

    # 2. Обязанности.
    if not duty:
        add_issue(
            issues,
            "Обязанности",
            "duty",
            "",
            "В вакансии отсутствует описание обязанностей.",
            "Добавить перечень основных рабочих задач."
        )
    else:
        vague_phrases = (
            "различных поручений",
            "другие задачи по необходимости",
            "иные поручения",
            "различные задачи",
        )

        if any(p in normalize_text(duty) for p in vague_phrases):
            add_issue(
                issues,
                "Обязанности",
                "duty",
                duty,
                "Обязанности описаны слишком общими формулировками.",
                "Перечислить конкретные задачи и ожидаемые результаты работы."
            )

    # 3. Требования.
    # Проверяем оба поля отдельно, чтобы заглушка в одном поле
    # не скрывала реальные требования из другого.
    requirement_values = [
        normalize_text(as_text(v.get("requirement"))),
        normalize_text(as_text(v.get("requirements")))
    ]

    placeholders = {
        "не указано",
        "не заполнено",
        "нет данных",
        "отсутствует"
    }

    meaningful_values = [
        value
        for value in requirement_values
        if value and value not in placeholders
    ]

    if not meaningful_values:
        add_issue(
            issues,
            "Требования",
            "requirement / requirements",
            "",
            "В вакансии не раскрыты требования к кандидату.",
            "Указать необходимые навыки, квалификацию или опыт, если они требуются."
        )

    # 4. Оплата.
    # Не требуем верхнюю границу, если указана минимальная зарплата.
    salary_ok, salary_text = salary_values(v)

    if not salary_ok:
        add_issue(
            issues,
            "Оплата",
            "salary_min / salary_max / salary",
            "",
            "Размер заработной платы не указан.",
            "Указать размер оплаты или диапазон заработной платы."
        )

    # 5. График работы.
    schedule_norm = normalize_text(schedule)
    qualification_norm = normalize_text(qualification)

    fixed_time = bool(
        re.search(r"\b\d{1,2}[:.]\d{2}\b", qualification_norm)
    )

    fixed_days = any(
        x in qualification_norm
        for x in (
            "пятиднев",
            "5/2",
            "понедельник",
            "рабочая неделя"
        )
    )

    has_fixed_details_elsewhere = fixed_time or fixed_days

    if not schedule:
        add_issue(
            issues,
            "График работы",
            "schedule",
            "",
            "Не указан график работы.",
            "Указать рабочие дни, часы и продолжительность смены."
        )

    elif "гибкий график" in schedule_norm:
        if has_fixed_details_elsewhere:
            add_issue(
                issues,
                "График работы",
                "schedule / requirement.qualification",
                f"schedule: {schedule}; qualification: {qualification}",
                "Гибкий график одновременно описан фиксированными днями или часами.",
                "Уточнить, какой режим действует: гибкий или фиксированный."
            )
        else:
            add_issue(
                issues,
                "График работы",
                "schedule",
                schedule,
                "Указан гибкий график, но правила его организации не раскрыты.",
                "Уточнить обязательные часы присутствия, рабочие дни и порядок согласования времени."
            )

    elif "сменн" in schedule_norm:
        has_shift_pattern = bool(
            re.search(r"\b\d+\s*/\s*\d+\b", schedule_norm)
        )

        has_shift_hours = bool(
            re.search(r"\b\d{1,2}[:.]\d{2}\b", schedule_norm)
        )

        if not (has_shift_pattern and has_shift_hours):
            add_issue(
                issues,
                "График работы",
                "schedule",
                schedule,
                "Указан сменный график, но не полностью раскрыт режим смен.",
                "Указать чередование смен и их продолжительность."
            )

    # 6. Противоречие формата работы.
    duty_norm = normalize_text(duty)

    remote_phrases = (
        "удаленно",
        "удалённо",
        "дистанционно",
        "полностью дистанционная",
        "работа из любого города",
        "работа вне офиса",
    )

    office_phrases = (
        "присутствие в офисе",
        "ежедневное присутствие",
        "обязательное посещение офиса",
        "работать в офисе",
        "в офисе в калининграде",
    )

    remote_found = any(x in duty_norm for x in remote_phrases)
    office_found = any(x in qualification_norm for x in office_phrases)

    if remote_found and office_found:
        add_issue(
            issues,
            "Противоречие в формате работы",
            "duty / requirement.qualification",
            f"duty: {duty}; qualification: {qualification}",
            "В одном поле указана дистанционная работа, в другом — обязательное присутствие в офисе.",
            "Уточнить фактический формат работы и указать единые условия во всех полях."
        )

    # 7. Неопределённый формат рабочего места.
    unclear_format = (
        "формат рабочего места уточняется",
        "формат работы уточняется",
        "формат и адрес рабочего места уточняются",
        "формат работы обсуждается",
    )

    if any(x in qualification_norm for x in unclear_format):
        add_issue(
            issues,
            "Формат рабочего места",
            "requirement.qualification",
            qualification,
            "Не определено, предполагается офисная, удалённая или гибридная работа.",
            "Указать конкретный формат рабочего места."
        )

    # 8. Противоречие опыта в структурированном поле и тексте.
    if experience is not None and str(experience).strip() in {"0", "0.0"}:
        match = re.search(
            r"(?:не менее|от)\s*(\d+)\s*лет?",
            qualification_norm
        )

        if match:
            years = match.group(1)

            add_issue(
                issues,
                "Требования",
                "requirement.experience / requirement.qualification",
                f"experience: {experience}; qualification: {qualification}",
                f"В структурированном поле указан опыт {experience} лет, но в тексте требуется не менее {years} лет.",
                "Проверить и согласовать требования к опыту работы."
            )

    # 9. Место работы.
    if not address:
        add_issue(
            issues,
            "Место работы",
            "addresses",
            "",
            "Не указано место работы.",
            "Указать населённый пункт или адрес рабочего места."
        )

    elif normalize_text(address) in {
        "калининградская область",
        "россия"
    }:
        add_issue(
            issues,
            "Место работы",
            "addresses",
            address,
            "Указан только регион или страна без населённого пункта.",
            "Уточнить город или населённый пункт рабочего места."
        )

    # 10. Тип занятости.
    if not employment:
        add_issue(
            issues,
            "Тип занятости",
            "employment",
            "",
            "Не указан тип занятости.",
            "Указать тип занятости: полная, частичная, временная или иной."
        )

    return issues


def _field_values(vacancy, source_field):
    """Возвращает исходные значения полей, на которые ссылается ИИ."""

    aliases = {
        "salary": ("salary", "salary_min", "salary_max"),
        "addresses": ("addresses",),
        "requirement": ("requirement",),
    }

    values = []

    parts = [
        p.strip()
        for p in re.split(r"\s*/\s*", source_field)
        if p.strip()
    ]

    for part in parts:
        if part in aliases:
            paths = [(p,) for p in aliases[part]]
        else:
            paths = [tuple(part.split("."))]

        for path in paths:
            value = get_path(vacancy, *path)

            if value not in (None, "", [], {}):
                values.append(as_text(value))

    return [x for x in values if x]


def validate_ai_issue(issue, vacancy):
    required = (
        "topic",
        "source_field",
        "quote",
        "problem",
        "recommendation"
    )

    if not isinstance(issue, dict):
        return None

    normalized = {
        key: str(issue.get(key, "") or "").strip()
        for key in required
    }

    if not all(
        normalized[k]
        for k in ("topic", "source_field", "problem", "recommendation")
    ):
        return None

    source_values = _field_values(
        vacancy,
        normalized["source_field"]
    )

    quote = normalized["quote"]

    if quote:
        quote_norm = normalize_text(quote)
        combined = normalize_text(" ".join(source_values))

        if not source_values or quote_norm not in combined:
            logging.warning(
                "Отклонено замечание ИИ: цитата не найдена в исходных полях %s",
                normalized["source_field"]
            )
            return None

    elif source_values:
        logging.warning(
            "Отклонено замечание ИИ: пустая цитата для заполненного поля %s",
            normalized["source_field"]
        )
        return None

    return normalized


def is_duplicate(issue, existing):
    issue_topic = normalize_text(issue.get("topic"))
    issue_problem = normalize_text(issue.get("problem"))
    issue_quote = normalize_text(issue.get("quote"))

    issue_fields = set(
        x.strip()
        for x in re.split(
            r"\s*/\s*",
            issue.get("source_field", "").casefold()
        )
        if x.strip()
    )

    for old in existing:
        old_topic = normalize_text(old.get("topic"))
        old_problem = normalize_text(old.get("problem"))
        old_quote = normalize_text(old.get("quote"))

        old_fields = set(
            x.strip()
            for x in re.split(
                r"\s*/\s*",
                old.get("source_field", "").casefold()
            )
            if x.strip()
        )

        same_quote = bool(
            issue_quote and old_quote and issue_quote == old_quote
        )

        similar_problem = bool(
            issue_problem
            and old_problem
            and SequenceMatcher(
                None,
                issue_problem,
                old_problem
            ).ratio() >= 0.88
        )

        same_topic_and_field = bool(
            issue_topic == old_topic
            and issue_fields & old_fields
        )

        if same_quote and (same_topic_and_field or similar_problem):
            return True

        if same_topic_and_field and similar_problem:
            return True

    return False


def analyze_vacancies(raw_vacancies, use_ai=True, ollama_config=None):
    ollama_config = ollama_config or {}

    result = []
    seen = set()

    for index, item in enumerate(raw_vacancies, 1):
        vacancy = (
            item.get("vacancy", item)
            if isinstance(item, dict)
            else {}
        )

        if not isinstance(vacancy, dict):
            logging.warning(
                "Пропущена запись %d: некорректная структура",
                index
            )
            continue

        vacancy_id = str(
            vacancy.get("id") or f"unknown-{index}"
        )

        if vacancy_id in seen:
            continue

        seen.add(vacancy_id)

        issues = rule_issues(vacancy)

        if use_ai:
            try:
                ai_issues = ask_ollama(
                    vacancy,
                    ollama_config
                )

                if isinstance(ai_issues, list):
                    for raw_issue in ai_issues:
                        checked = validate_ai_issue(
                            raw_issue,
                            vacancy
                        )

                        if checked and not is_duplicate(checked, issues):
                            issues.append(checked)

            except Exception as exc:
                logging.warning(
                    "ИИ-анализ вакансии %s не удался: %s. Оставлены результаты правил.",
                    vacancy_id,
                    exc
                )

        result.append({
            "id": vacancy_id,
            "url": vacancy.get("vac_url") or vacancy.get("url") or "",
            "issues": issues,
        })

        logging.info(
            "Обработана вакансия %d/%d: %s",
            index,
            len(raw_vacancies),
            vacancy_id
        )

    return {"vacancies": result}
