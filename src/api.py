
import logging
import requests


def fetch_vacancies(
    api_url,
    max_vacancies=200,
    page_size=100,
    timeout=30
):
    """Загружает вакансии из API постранично."""

    if max_vacancies <= 0:
        return []

    page_size = min(max(1, page_size), 100)

    all_items = []
    offset = 0

    session = requests.Session()
    session.headers.update({
        "User-Agent": "TransparentVacancy/1.0"
    })

    while len(all_items) < max_vacancies:

        limit = min(
            page_size,
            max_vacancies - len(all_items)
        )

        response = session.get(
            api_url,
            params={
                "limit": limit,
                "offset": offset
            },
            timeout=timeout
        )

        response.raise_for_status()

        payload = response.json()

        if str(payload.get("status", "200")) != "200":
            raise RuntimeError(
                f"API вернул ошибку: {payload.get('meta', {})}"
            )

        page = (
            payload.get("results", {})
            .get("vacancies", [])
        )

        if not isinstance(page, list):
            raise ValueError(
                "Некорректный формат API: "
                "results.vacancies должен быть списком"
            )

        if not page:
            break

        all_items.extend(page)

        logging.info(
            "Получена страница %d: %d вакансий, всего %d",
            offset + 1,
            len(page),
            len(all_items)
        )

        if len(page) < limit:
            break

        # Переход к следующей странице
        offset += 1

    # Удаляем дубли по ID
    unique = {}

    for item in all_items:
        vacancy = item.get("vacancy", item)
        vid = str(vacancy.get("id", ""))

        if vid:
            unique[vid] = item

    return list(unique.values())[:max_vacancies]

