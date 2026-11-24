import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.api import fetch_vacancies
from src.analyzer import analyze_vacancies
from src.config import load_config
from src.report import save_report, load_local_json

BASE_DIR = Path(__file__).resolve().parent


def configure_logging(config):
    log_path = BASE_DIR / config.get("logging", {}).get("file", "logs/app.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    console_handler = logging.StreamHandler()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler],
                        force=True)


def main():
    parser = argparse.ArgumentParser(
        description="Прозрачная вакансия — анализ понятности условий вакансий"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--api", action="store_true",
                       help="Загрузить вакансии из API региона 39")
    group.add_argument("--input", type=str,
                       help="Проверочный режим: путь к локальному JSON")
    parser.add_argument("--limit", type=int,
                        help="Максимальное число вакансий (переопределяет config.json)")
    parser.add_argument("--no-ai", action="store_true",
                        help="Отключить Ollama; выполнить только проверки правилами")
    args = parser.parse_args()

    config = load_config(BASE_DIR / "config.json")
    configure_logging(config)

    try:
        if args.input:
            input_path = Path(args.input)
            if not input_path.is_absolute():
                input_path = BASE_DIR / input_path
            logging.info("Проверочный режим: %s", input_path)
            raw_vacancies = load_local_json(input_path)
        else:
            max_vacancies = args.limit if args.limit is not None else config["max_vacancies"]
            if max_vacancies <= 0:
                raise ValueError("--limit и max_vacancies должны быть больше нуля")
            raw_vacancies = fetch_vacancies(
                config["api_url"],
                max_vacancies=max_vacancies,
                page_size=config["page_size"],
                timeout=config["request_timeout"],
            )

        if not raw_vacancies:
            logging.warning(
                "Источник не вернул вакансий. Последний успешный отчёт не изменён."
            )
            return

        ai_enabled = not args.no_ai and config.get("ollama", {}).get("enabled", True)
        if ai_enabled:
            logging.info("ИИ-анализ включён: модель %s",
                         config.get("ollama", {}).get("model", "не указана"))
        else:
            logging.info("ИИ-анализ отключён; используются только правила")

        report = analyze_vacancies(
            raw_vacancies,
            use_ai=ai_enabled,
            ollama_config=config.get("ollama", {}),
        )

        if not report.get("vacancies"):
            raise RuntimeError(
                "Не удалось сформировать ни одной записи. Предыдущий отчёт сохранён."
            )

        out = BASE_DIR / config["report_path"]
        save_report(report, out)
        logging.info(
            "Готово. Уникальных вакансий: %d. Отчёт: %s",
            len(report["vacancies"]), out
        )

    except Exception:
        logging.exception(
            "Обработка завершилась ошибкой. Предыдущий успешный отчёт сохранён, если он был."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
