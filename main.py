
import argparse
import json
import logging
from pathlib import Path

from src.api import fetch_vacancies
from src.analyzer import analyze_vacancies
from src.config import load_config
from src.report import save_report, load_local_json

BASE_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Прозрачная вакансия — анализ условий вакансий")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--api", action="store_true", help="Загрузить вакансии из API региона 39")
    group.add_argument("--input", type=str, help="Проверочный режим: путь к локальному JSON")
    parser.add_argument("--limit", type=int, help="Максимальное число вакансий (переопределяет config.json)")
    parser.add_argument("--no-ai", action="store_true", help="Отключить Ollama (только правила, для быстрой проверки)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = load_config(BASE_DIR / "config.json")

    try:
        if args.input:
            logging.info("Проверочный режим: %s", args.input)
            raw_vacancies = load_local_json(Path(args.input))
        else:
            max_vacancies = args.limit or config["max_vacancies"]
            raw_vacancies = fetch_vacancies(
                config["api_url"],
                max_vacancies=max_vacancies,
                page_size=config["page_size"],
                timeout=config["request_timeout"]
            )

        if not raw_vacancies:
            logging.warning("Источник не вернул вакансий. Пустой отчёт не перезаписывает последний успешный.")
            return

        report = analyze_vacancies(
            raw_vacancies,
            use_ai=not args.no_ai and config.get("ollama", {}).get("enabled", True),
            ollama_config=config.get("ollama", {})
        )

        if len(report.get("vacancies", [])) != len(raw_vacancies):
            raise RuntimeError(
                f"Количество вакансий не совпадает: "
                f"загружено {len(raw_vacancies)}, "
                f"обработано {len(report.get('vacancies', []))}. "
                "Предыдущий отчёт не будет перезаписан."
            )

        out = BASE_DIR / config["report_path"]
        save_report(report, out)
        logging.info("Готово. Обработано вакансий: %s. Отчёт: %s", len(report["vacancies"]), out)

    except Exception as exc:
        logging.exception("Обработка завершилась ошибкой: %s", exc)
        logging.error("Предыдущий успешный отчёт сохранён, если он существовал.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
