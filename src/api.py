
import logging
import time
import requests


def fetch_vacancies(
    api_url,
    max_vacancies=200,
    page_size=100,
    timeout=30,
    max_attempts=4,
    retry_delay=2,
):
    """Загружает вакансии постранично с повторными попытками при сбоях API."""

    if max_vacancies <= 0:
        raise ValueError("max_vacancies должен быть положительным числом")
    if page_size <= 0:
        raise ValueError("page_size должен быть положительным числом")

    page_size = min(page_size, 100)
    all_items = []
    offset = 0
    page_number = 0

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "TransparentVacancy/1.1"
        })

        while len(all_items) < max_vacancies:
            limit = min(page_size, max_vacancies - len(all_items))

            # Повторяем запрос при временных ошибках сервера или сети.
            response = None

            for attempt in range(1, max_attempts + 1):
                try:
                    response = session.get(
                        api_url,
                        params={
                            "limit": limit,
                            "offset": offset
                        },
                        timeout=timeout,
                    )
                    response.raise_for_status()
                    break

                except requests.HTTPError as exc:
                    status_code = exc.response.status_code

                    if status_code not in (429, 500, 502, 503, 504):
                        raise

                    if attempt == max_attempts:
                        raise

                    delay = retry_delay * (2 ** (attempt - 1))

                    logging.warning(
                        "Ошибка HTTP %s при загрузке страницы %d. "
                        "Попытка %d/%d. Повтор через %d сек.",
                        status_code,
                        page_number + 1,
                        attempt,
                        max_attempts,
                        delay,
                    )

                    time.sleep(delay)

                except (requests.Timeout, requests.ConnectionError):
                    if attempt == max_attempts:
                        raise

                    delay = retry_delay * (2 ** (attempt - 1))

                    logging.warning(
                        "Ошибка соединения при загрузке страницы %d. "
                        "Попытка %d/%d. Повтор через %d сек.",
                        page_number + 1,
                        attempt,
                        max_attempts,
                        delay,
                    )

                    time.sleep(delay)

            payload = response.json()

            if not isinstance(payload, dict):
                raise ValueError(
                    "Некорректный ответ API: ожидался JSON-объект"
                )

            status = str(payload.get("status", "200"))

            if status != "200":
                raise RuntimeError(
                    f"API вернул статус {status}: {payload.get('meta', {})}"
                )

            results = payload.get("results") or {}

            page = (
                results.get("vacancies", [])
                if isinstance(results, dict)
                else None
            )

            if not isinstance(page, list):
                raise ValueError(
                    "Некорректный формат API: "
                    "results.vacancies должен быть списком"
                )

            if not page:
                break

            page_number += 1
            all_items.extend(page)

            logging.info(
                "Получена страница %d: %d записей; всего загружено %d",
                page_number,
                len(page),
                len(all_items),
            )

            # offset — количество пропускаемых записей.
            offset += 1

            if len(page) < limit:
                break

    # Дедупликация по ID.
    unique = {}

    for item in all_items:
        vacancy = (
            item.get("vacancy", item)
            if isinstance(item, dict)
            else {}
        )

        if not isinstance(vacancy, dict):
            continue

        vacancy_id = str(vacancy.get("id") or "").strip()

        if vacancy_id and vacancy_id not in unique:
            unique[vacancy_id] = item

    return list(unique.values())[:max_vacancies]

