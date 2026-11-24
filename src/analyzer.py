
import logging
import re

from src.ollama_client import ask_ollama


def get_path(data, *path):
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(as_text(x) for x in value.values())
    if isinstance(value, list):
        return " ".join(as_text(x) for x in value)
    return str(value).strip()


def first_value(vac, *paths):
    for path in paths:
        value = get_path(vac, *path)
        if value not in (None, "", [], {}):
            return value
    return None


def add_issue(issues, topic, field, quote, problem, recommendation):
    issues.append({
        "topic": topic,
        "source_field": field,
        "quote": quote,
        "problem": problem,
        "recommendation": recommendation
    })


def salary_values(v):
    minimum = v.get("salary_min")
    maximum = v.get("salary_max")
    salary = v.get("salary")

    if salary not in (None, "", 0, "0"):
        return True, as_text(salary)

    min_valid = minimum not in (None, "", 0, "0")
    max_valid = maximum not in (None, "", 0, "0")

    if min_valid and max_valid:
        return True, f"{minimum} - {maximum}"

    if min_valid:
        return True, f"От {minimum}; верхняя граница не указана"

    if max_valid:
        return True, f"До {maximum}; нижняя граница не указана"

    return False, ""


def rule_issues(v):
    issues = []

    # 1. Проверка основных полей
    title = as_text(v.get("job-name"))
    duty = as_text(v.get("duty"))
    schedule = as_text(v.get("schedule"))
    employment = as_text(v.get("employment"))
    address = as_text(v.get("addresses"))

    requirement = as_text(v.get("requirement"))
    requirements = as_text(v.get("requirements"))

    if not title:
        add_issue(
            issues, "Название должности", "job-name", "",
            "В вакансии не указано название должности.",
            "Добавить конкретное название должности."
        )
    elif title.lower() in ("специалист", "работник", "сотрудник"):
        add_issue(
            issues, "Название должности", "job-name", title,
            "Название слишком общее и не раскрывает специализацию.",
            "Уточнить направление работы и специализацию должности."
        )

    if not duty:
        add_issue(
            issues, "Обязанности", "duty", "",
            "В вакансии отсутствует описание обязанностей.",
            "Добавить перечень основных рабочих задач."
        )

    # Учитываем оба поля требований
    requirement_text = " ".join(x for x in [requirement, requirements] if x)

    if not requirement_text:
        add_issue(
            issues, "Требования", "requirement", "",
            "В вакансии не указаны требования к кандидату.",
            "Добавить требования к образованию, опыту и навыкам."
        )

    # 2. Проверка зарплаты
    salary_ok, salary_text = salary_values(v)

    if not salary_ok:
        add_issue(
            issues, "Оплата", "salary", "",
            "Размер заработной платы не указан или указан нулевым значением.",
            "Указать размер оплаты или диапазон заработной платы."
        )
    elif "верхняя граница не указана" in salary_text:
        add_issue(
            issues, "Оплата", "salary", salary_text,
            "Указана только минимальная зарплата, верхняя граница отсутствует.",
            "Уточнить максимальный размер заработной платы."
        )

    # 3. Проверка графика
    if not schedule:
        add_issue(
            issues, "График работы", "schedule", "",
            "Не указан график работы.",
            "Указать рабочие дни, часы и продолжительность смены."
        )
    elif "гибкий график" in schedule.lower():
        add_issue(
            issues, "График работы", "schedule", schedule,
            "Указан гибкий график, но конкретные дни и часы не раскрыты.",
            "Уточнить рабочие дни, продолжительность смены и время начала работы."
        )
    elif "сменный" in schedule.lower():
        if not re.search(r"\b\d+\s*/\s*\d+\b", schedule):
            add_issue(
                issues, "График работы", "schedule", schedule,
                "Указан сменный график, но порядок чередования смен не раскрыт.",
                "Указать режим сменности и продолжительность каждой смены."
            )

    # 4. Проверка обязанностей на общие формулировки
    vague_duty = [
        "различных поручений",
        "другие задачи по необходимости",
        "иные поручения",
        "различные задачи"
    ]

    for phrase in vague_duty:
        if phrase in duty.lower():
            add_issue(
                issues, "Обязанности", "duty", duty,
                "Обязанности описаны слишком общими формулировками.",
                "Перечислить конкретные задачи и ожидаемые результаты работы."
            )
            break

    # 5. Проверка опыта на противоречия
    experience = get_path(v, "requirement", "experience")
    qualification = as_text(
        get_path(v, "requirement", "qualification")
    )

    if experience is not None:
        match = re.search(
            r"(?:не менее|от)\s*(\d+)\s*лет?",
            qualification.lower()
        )

        if match and str(experience).strip() in ("0", "0.0"):
            years = match.group(1)

            add_issue(
                issues,
                "Требования",
                "requirement.experience / requirement.qualification",
                f"experience: {experience}; qualification: {qualification}",
                f"В структурированном поле указан опыт {experience} лет, "
                f"но в описании требуется не менее {years} лет.",
                "Проверить и согласовать требования к опыту работы."
            )

    # 6. Проверка удалённой работы и присутствия в офисе
    duty_lower = duty.lower()
    qualification_lower = qualification.lower()

    remote_words = ("удаленно", "удалённо", "дистанционно")
    office_words = ("присутствие в офисе", "ежедневное присутствие",
                    "обязательно в офисе")

    remote_found = any(x in duty_lower for x in remote_words)
    office_found = any(x in qualification_lower for x in office_words)

    if remote_found and office_found:
        add_issue(
            issues,
            "Место работы",
            "duty / requirement.qualification",
            f"duty: {duty}; qualification: {qualification}",
            "Описание удалённой работы противоречит требованию "
            "обязательного присутствия в офисе.",
            "Уточнить фактический формат работы: удалённый, офисный или гибридный."
        )
    
    # 6.1 Расширенная проверка удаленной работы и офиса
    qualification_lower = qualification.lower()

    remote_phrases = (
        "удаленно",
        "удалённо",
        "дистанционно",
        "полностью дистанционная",
        "работа из любого города",
        "работа вне офиса"
    )

    office_phrases = (
        "присутствие в офисе",
        "ежедневное присутствие",
        "обязательное посещение офиса",
        "работать в офисе",
        "в офисе в калининграде"
    )

    remote_found = any(x in duty_lower for x in remote_phrases)
    office_found = any(x in qualification_lower for x in office_phrases)

    if remote_found and office_found:
        add_issue(
            issues,
            "Противоречие в формате работы",
            "duty / requirement.qualification",
            f"duty: {duty}; qualification: {qualification}",
            "В описании указана дистанционная работа, "
            "но одновременно требуется присутствие в офисе.",
            "Уточнить фактический формат работы."
        )

    # 6.2 Проверка неопределенного формата рабочего места
    work_format_phrases = (
        "формат рабочего места уточняется",
        "формат работы уточняется",
        "формат и адрес рабочего места уточняются",
        "формат работы обсуждается"
    )

    if any(x in qualification_lower for x in work_format_phrases):
        add_issue(
            issues,
            "Формат рабочего места",
            "requirement.qualification",
            qualification,
            "Не определено, предполагается офисная, удаленная или гибридная работа.",
            "Указать конкретный формат рабочего места."
        )


    # 7. Проверка места работы
    if not address:
        add_issue(
            issues, "Место работы", "addresses", "",
            "Не указано место работы.",
            "Указать населённый пункт и адрес рабочего места."
        )
    elif address.lower() in ("калининградская область",):
        add_issue(
            issues, "Место работы", "addresses", address,
            "Указан только регион без конкретного населённого пункта.",
            "Уточнить город или населённый пункт и адрес рабочего места."
        )

    # 8. Проверка типа занятости
    if not employment:
        add_issue(
            issues, "Тип занятости", "employment", "",
            "Не указан тип занятости.",
            "Указать полную, частичную или временную занятость."
        )

    # 9. Проверка противоречия в графике
    if "гибкий график" in schedule.lower():
        if ("09:00" in qualification or "18:00" in qualification):
            add_issue(
                issues,
                "График работы",
                "schedule / requirement.qualification",
                f"schedule: {schedule}; qualification: {qualification}",
                "Гибкий график не согласуется с указанным фиксированным "
                "временем работы.",
                "Уточнить, является ли график фиксированным или гибким."
            )

    return issues


def normalize_ai_issue(issue):
    required = (
        "topic", "source_field", "quote",
        "problem", "recommendation"
    )

    if not isinstance(issue, dict):
        return None

    return {
        key: str(issue.get(key, "") or "")
        for key in required
    }


def is_duplicate(issue, existing):
    field = issue.get("source_field", "").lower()
    topic = issue.get("topic", "").lower()
    problem = issue.get("problem", "").lower()

    keywords = (
        "не указан",
        "отсутствует",
        "не указаны",
        "нет информации"
    )

    for old in existing:
        old_field = old.get("source_field", "").lower()
        old_topic = old.get("topic", "").lower()
        old_problem = old.get("problem", "").lower()

        same_field = field == old_field
        same_topic = topic == old_topic

        if same_field and same_topic:
            if any(word in problem for word in keywords) and any(
                word in old_problem for word in keywords
            ):
                return True

            if problem == old_problem:
                return True

    return False


def analyze_vacancies(raw_vacancies, use_ai=True, ollama_config=None):
    ollama_config = ollama_config or {}

    result = []
    seen = set()

    for index, item in enumerate(raw_vacancies, 1):
        v = item.get("vacancy", item) if isinstance(item, dict) else {}

        vid = str(v.get("id") or f"unknown-{index}")

        if vid in seen:
            continue

        seen.add(vid)

        issues = rule_issues(v)

        if use_ai:
            try:
                ai_issues = ask_ollama(v, ollama_config)

                if isinstance(ai_issues, list):
                    for ai_issue in ai_issues:
                        normalized = normalize_ai_issue(ai_issue)

                        if normalized and not is_duplicate(normalized, issues):
                            issues.append(normalized)

            except Exception as exc:
                logging.warning(
                    "ИИ-анализ вакансии %s не удался: %s. "
                    "Оставлены результаты правил.",
                    vid, exc
                )

        result.append({
            "id": vid,
            "url": v.get("vac_url") or v.get("url") or "",
            "issues": issues
        })

        logging.info(
            "Обработана вакансия %d/%d: %s",
            index, len(raw_vacancies), vid
        )

    return {"vacancies": result}
