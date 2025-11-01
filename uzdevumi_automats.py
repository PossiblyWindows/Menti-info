# -*- coding: utf-8 -*-
"""Modernizēts Uzdevumi.lv automatizācijas skripts.

Šis skripts atkārto oriģinālās funkcionalitātes, bet to dara modulārāk, ar
papildu kļūdu apstrādi un atkārtojumiem. Galvenie soļi:

1. Ieiešana Uzdevumi.lv ar E-klases SSO.
2. Pirmā profila izvēle.
3. Nejauša priekšmeta/tēmas/uzdevuma izvēle (izlaižot aizliegtos).
4. Uzdevuma HTML satura iegūšana, nevēlamo elementu atpazīšana un izlaišana.
5. Uzdevuma sūtīšana ChatGPT caur oficiālo tīmekļa interfeisu.
6. Atbilžu parsēšana un ievietošana Uzdevumi.lv laukos.
7. Rezultāta iesniegšana un izvēles žurnāla rakstīšana.

Papildu iespējas:
- Galviņas režīma pārslēgšana (headless) un starpniekservera atbalsts.
- Atkārtojumi, ja GPT atbilde nav izmantojama.
- Noturīgāka gaidīšana un kļūdu apstrāde.
- (Neobligāti) vienkārša Tkinter GUI palaišanai.

Autors: ChatGPT (gpt-5-codex modelis, OpenAI)
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as _dt
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Sequence, Set, Tuple

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    JavascriptException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:  # Tkinter ir neobligāts – ja nav pieejams, GUI režīms tiek atspējots.
    import tkinter as tk
    from tkinter import messagebox

    TK_AVAILABLE = True
except Exception:  # pragma: no cover - Tk nav svarīgs testēšanai
    TK_AVAILABLE = False


LATVIAN_MESSAGES = {
    "banner": "=== Uzdevumi.lv Automāts ===",
    "login": "🔑 Ieiešana…",
    "login_ok": "✔ Ienākts",
    "cookies_declined": "🍪 Sīkfaili noraidīti",
    "subject_search": "📚 Meklē priekšmetu…",
    "subject_selected": "➡ Priekšmets: {subject}",
    "theme_selected": "➡ Tēma: {theme}",
    "task_selected": "➡ Uzdevums: {task}",
    "task_kind": "📂 Veids: {kind}",
    "task_text": "📝 Teksts: {text}",
    "points": "⭐ Punkti: {points}",
    "skip_task": "⚠ Uzdevums ar bildēm / vilkšanu – izlaižam",
    "retry_task": "↻ Meklē citu uzdevumu…",
    "open_chatgpt": "🤖 Atveru ChatGPT…",
    "prompt_sent": "📨 Sūtīts GPT",
    "show_more": "🔽 Izvērsta pilna atbilde",
    "gpt_reply": "💬 GPT atbilde: {preview}",
    "filling": "➡ Ievadām: {values}",
    "submitted": "✅ Iesniegts",
    "no_inputs": "⚠ Nav ievades lauku",
    "submit_missing": "⚠ Nav pogas",
    "invalid_answers": "⚠ GPT neatgrieza derīgas vērtības",
    "gpt_retry": "↻ GPT atbilde neskaidra – mēģinu vēlreiz",
    "gpt_failed": "❌ Neizdevās iegūt lietojamu atbildi no GPT",
    "no_valid_tasks": "⚠ Nav derīgu uzdevumu šajā tēmā – izvēlos citu priekšmetu/tēmu",
}

EXCLUDED_SUBJECTS = {"Starpbrīdis", "Uzdevumi.lv konkursi"}
EXCLUDED_SUBJECT_THEMES = {
    "Matemātika": {"Gatavošanās matemātikas olimpiādēm"},
}
SKIP_MARKERS = (
    "<img",
    "background-image",
    "gxs-resource-image",
    "gxst-resource-image",
    "gxs-dnd-option",
    "ui-draggable",
    "answer-box",
    "drag-container",
    "data-drag",
)


class AutomationError(RuntimeError):
    """Specifiska kļūda automatizācijas procesam."""


class NoValidTaskError(AutomationError):
    """Nav atrasts derīgs uzdevums izvēlētajā tēmā."""


@dataclasses.dataclass(slots=True)
class AutomationConfig:
    """Konfigurācija pārlūka iestatījumiem un uzvedībai."""

    headless: bool = False
    proxy: Optional[str] = None
    uzdevumi_profile_dir: str = "./uzdevumi_profils"
    chatgpt_profile_dir: str = "./chatgpt_profils"
    page_load_timeout: int = 45
    wait_timeout: int = 15
    gpt_retry_count: int = 3
    log_file: Optional[Path] = Path("results.log")


@dataclasses.dataclass(slots=True)
class TaskMetadata:
    subject: str
    theme: str
    task_title: str
    item_type: str
    html: str
    text_preview: str
    points: str
    answer_fields: int

    @property
    def should_skip(self) -> bool:
        html_lower = (self.html or "").lower()
        if not html_lower.strip():
            return True
        return any(marker in html_lower for marker in SKIP_MARKERS)


@dataclasses.dataclass(slots=True)
class TaskOption:
    element: Any
    title: str
    item_type: str
    completed: bool
    href: str


def task_option_key(option: TaskOption) -> str:
    href = option.href or ""
    if href:
        return href
    try:
        element_id = option.element.id  # type: ignore[attr-defined]
    except Exception:
        element_id = id(option.element)
    return f"webelement:{element_id}"


def notify(key: str, **kwargs: object) -> None:
    """Vienots paziņojumu formatētājs latviešu valodā."""

    message = LATVIAN_MESSAGES.get(key)
    if not message:
        return
    if kwargs:
        try:
            message = message.format(**kwargs)
        except Exception:
            pass
    print(message)


def wait_for(
    driver: Chrome,
    css: str,
    timeout: int,
    condition=EC.presence_of_element_located,
):
    """Droša gaidīšana ar izņēmumu apstrādi."""

    try:
        return WebDriverWait(driver, timeout).until(condition((By.CSS_SELECTOR, css)))
    except TimeoutException as exc:  # pragma: no cover - lietotājs redzēs kļūdu logā
        raise AutomationError(f"Nebija iespējams atrast elementu: {css}") from exc


def wait_for_all(driver: Chrome, css: str, timeout: int) -> List:
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, css))
        )
    except TimeoutException:
        return []


def create_driver(profile_dir: str, config: AutomationConfig) -> Chrome:
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=lv-LV")
    if config.headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    if config.proxy:
        options.add_argument(f"--proxy-server={config.proxy}")

    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(config.page_load_timeout)
    return driver


def safe_click(driver: Chrome, element) -> None:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        element.click()
    except (ElementClickInterceptedException, WebDriverException):
        driver.execute_script("arguments[0].click();", element)


def decline_cookies(driver: Chrome, timeout: int) -> None:
    try:
        button = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#CybotCookiebotDialogBodyButtonDecline"))
        )
        safe_click(driver, button)
        notify("cookies_declined")
        time.sleep(1)
    except TimeoutException:
        return


def login_via_eklase(driver: Chrome, username: str, password: str, config: AutomationConfig) -> None:
    notify("login")
    driver.get(
        "https://www.uzdevumi.lv/Sso/AuthRedirect/eklase?authAction=alor&rememberMe=False&isPopup=True"
    )
    time.sleep(2)
    decline_cookies(driver, config.wait_timeout)

    user_field = wait_for(driver, "#UserName", config.wait_timeout)
    pass_field = wait_for(driver, "div.InputForm_Row:nth-child(2) > input:nth-child(1)", config.wait_timeout)

    user_field.clear()
    user_field.send_keys(username)
    pass_field.clear()
    pass_field.send_keys(password)
    safe_click(driver, wait_for(driver, "#cmdLogonUser", config.wait_timeout, EC.element_to_be_clickable))

    time.sleep(5)
    profiles = wait_for_all(driver, ".UserProfileSelector_Button", config.wait_timeout)
    if profiles:
        safe_click(driver, profiles[0])
        time.sleep(3)
    decline_cookies(driver, config.wait_timeout)
    notify("login_ok")


def select_random_subject(
    driver: Chrome,
    config: AutomationConfig,
    excluded_combinations: Optional[Set[Tuple[str, str]]] = None,
) -> Tuple[str, str]:
    excluded_combinations = excluded_combinations or set()
    blocked_subjects: Set[str] = set()

    while True:
        notify("subject_search")
        driver.get("https://www.uzdevumi.lv/p")
        time.sleep(2)
        decline_cookies(driver, config.wait_timeout)

        subject_container = wait_for(driver, "ul.list-unstyled.thumbnails", config.wait_timeout)
        all_subjects = subject_container.find_elements(By.CSS_SELECTOR, "li.thumb.wide a[href]")
        candidates = [
            (element, element.text.replace("\n", " ").strip())
            for element in all_subjects
            if element.is_displayed()
        ]

        filtered = [entry for entry in candidates if entry[1] not in EXCLUDED_SUBJECTS]
        available = [entry for entry in filtered if entry[1] not in blocked_subjects]
        if not available:
            if blocked_subjects:
                raise AutomationError("Nav tēmu")
            raise AutomationError("Nav piemērotu priekšmetu")

        element, subject_text = random.choice(available)
        notify("subject_selected", subject=subject_text)
        safe_click(driver, element)
        time.sleep(2)
        decline_cookies(driver, config.wait_timeout)

        try:
            overlay_button = driver.find_element(By.CSS_SELECTOR, ".ui-button")
            safe_click(driver, overlay_button)
            time.sleep(1)
        except NoSuchElementException:
            pass

        themes: List[Tuple[Any, str]] = []
        for elem in driver.find_elements(By.CSS_SELECTOR, "ol.list-unstyled a[href]"):
            if not elem.is_displayed():
                continue
            theme_text = elem.text.strip()
            excluded_for_subject = EXCLUDED_SUBJECT_THEMES.get(subject_text, set())
            if not theme_text or theme_text in excluded_for_subject:
                continue
            if (subject_text, theme_text) in excluded_combinations:
                continue
            themes.append((elem, theme_text))

        if themes:
            selected_theme, theme_text = random.choice(themes)
            notify("theme_selected", theme=theme_text)
            safe_click(driver, selected_theme)
            time.sleep(2)
            decline_cookies(driver, config.wait_timeout)
            return subject_text, theme_text

        blocked_subjects.add(subject_text)
        time.sleep(1)


def collect_available_tasks(driver: Chrome) -> List[TaskOption]:
    options: List[TaskOption] = []
    seen_hrefs: Set[str] = set()

    sections = driver.find_elements(By.CSS_SELECTOR, "section.block")
    for section in sections:
        try:
            heading = section.find_element(By.CSS_SELECTOR, "h2").text.strip()
        except NoSuchElementException:
            heading = ""
        heading_lower = heading.lower()
        item_type = "Tests" if "test" in heading_lower else "Uzdevums"

        rows = section.find_elements(By.CSS_SELECTOR, "table.exercise-table tbody tr")
        if rows:
            for row in rows:
                try:
                    link = row.find_element(By.CSS_SELECTOR, "a[href]")
                except NoSuchElementException:
                    continue
                href = link.get_attribute("href") or ""
                if href in seen_hrefs:
                    continue
                title = link.text.strip()
                if not title:
                    continue
                seen_hrefs.add(href)
                completed = False
                try:
                    earned = row.find_element(By.CSS_SELECTOR, ".points .earned").text.strip()
                    maximum = row.find_element(By.CSS_SELECTOR, ".points .max").text.strip()
                    if earned and maximum and earned == maximum:
                        completed = True
                except NoSuchElementException:
                    pass
                options.append(TaskOption(link, title, item_type, completed, href))
            continue

        body_links = section.find_elements(By.CSS_SELECTOR, "div:nth-child(2) a[href]")
        if not body_links:
            body_links = section.find_elements(By.CSS_SELECTOR, "a[href]")
        for link in body_links:
            if not link.is_displayed():
                continue
            href = link.get_attribute("href") or ""
            if href in seen_hrefs:
                continue
            title = link.text.strip()
            if not title:
                continue
            seen_hrefs.add(href)
            options.append(TaskOption(link, title, item_type, False, href))

    return options


def open_random_task(
    driver: Chrome, config: AutomationConfig, attempted: Set[str]
) -> TaskOption:
    options = collect_available_tasks(driver)
    remaining = [option for option in options if task_option_key(option) not in attempted]
    if not remaining:
        raise NoValidTaskError("Nav derīgu uzdevumu")

    incomplete = [option for option in remaining if not option.completed]
    selection = random.choice(incomplete or remaining)
    notify("task_selected", task=selection.title)
    notify("task_kind", kind=selection.item_type)
    safe_click(driver, selection.element)
    time.sleep(3)
    decline_cookies(driver, config.wait_timeout)
    return selection


def extract_task_metadata(
    driver: Chrome,
    subject: str,
    theme: str,
    selected_task: TaskOption,
    config: AutomationConfig,
) -> TaskMetadata:
    try:
        html_element = wait_for(driver, "#taskhtml", config.wait_timeout)
    except AutomationError as exc:
        raise AutomationError("Neizdevās nolasīt uzdevuma saturu") from exc

    html_content = html_element.get_attribute("innerHTML") or ""
    raw_text = html_element.text.strip().replace("\n", " ")
    preview = (raw_text[:120] + "…") if len(raw_text) > 120 else raw_text

    try:
        points = driver.find_element(By.CSS_SELECTOR, ".obj-points").text.strip()
    except NoSuchElementException:
        points = "0 p."

    inputs = driver.find_elements(
        By.CSS_SELECTOR,
        "input[type='text'],input[type='number'],textarea,input.gxs-answer-number",
    )
    answer_fields = sum(1 for element in inputs if element.is_displayed())

    metadata = TaskMetadata(
        subject=subject,
        theme=theme,
        task_title=selected_task.title,
        item_type=selected_task.item_type,
        html=html_content,
        text_preview=preview,
        points=points,
        answer_fields=answer_fields,
    )

    if metadata.should_skip:
        notify("skip_task")
    else:
        notify("task_text", text=preview)
        notify("points", points=points)

    return metadata


def ensure_task_with_inputs(driver: Chrome, subject: str, theme: str, config: AutomationConfig) -> TaskMetadata:
    """Atrod derīgu uzdevumu; ja nepieciešams, izvēlas citu."""

    theme_url = driver.current_url
    attempted: Set[str] = set()

    while True:
        try:
            selected_task = open_random_task(driver, config, attempted)
        except NoValidTaskError:
            driver.get(theme_url)
            time.sleep(2)
            raise
        attempted.add(task_option_key(selected_task))
        metadata = extract_task_metadata(driver, subject, theme, selected_task, config)
        if metadata.should_skip:
            notify("retry_task")
            driver.back()
            time.sleep(2)
            try:
                wait_for(driver, "section.block", config.wait_timeout)
            except AutomationError:
                driver.get(theme_url)
                time.sleep(2)
            continue
        if metadata.answer_fields == 0:
            notify("no_inputs")
            notify("retry_task")
            driver.back()
            time.sleep(2)
            try:
                wait_for(driver, "section.block", config.wait_timeout)
            except AutomationError:
                driver.get(theme_url)
                time.sleep(2)
            continue
        return metadata


def build_prompt(html: str) -> str:
    return (
        "Tu risini Uzdevumi.lv testu. Šeit ir pilns uzdevuma HTML.\n\n"
        "Tava atbilde:\n"
        "- Tikai pareizās vērtības rindās (viena vērtība katrā rindā)\n"
        "- Nekādas paskaidrošanas vai formatēšanas\n"
        "- Matemātikai – skaitļi, tekstam – vārdi\n"
        "- Ja nav iespējams atrisināt, neatbildi vispār\n\n"
        "HTML:\n" + html
    )


def send_to_chatgpt(chat_driver: Chrome, html: str, config: AutomationConfig) -> str:
    prompt = build_prompt(html)
    try:
        textarea = wait_for(chat_driver, "#prompt-textarea", config.wait_timeout)
    except AutomationError as exc:
        raise AutomationError("Neizdevās atrast ChatGPT ievades lauku") from exc

    textarea.send_keys(Keys.CONTROL, "a")
    textarea.send_keys(Keys.DELETE)
    textarea.send_keys(prompt)
    time.sleep(1)
    safe_click(chat_driver, wait_for(chat_driver, "#composer-submit-button", config.wait_timeout, EC.element_to_be_clickable))
    notify("prompt_sent")

    response_text = ""
    for _ in range(60):
        time.sleep(1.5)
        answers = chat_driver.find_elements(
            By.CSS_SELECTOR,
            "div.markdown.prose.dark\\:prose-invert.w-full.break-words.dark.markdown-new-styling",
        )
        if answers:
            candidate = answers[-1].text.strip()
            if candidate:
                response_text = candidate
        pending = chat_driver.find_elements(By.CSS_SELECTOR, "button[data-testid='stop-button']")
        if not pending and response_text:
            break

    try:
        more_links = chat_driver.find_elements(By.CSS_SELECTOR, "a.text-token-text-secondary")
        for link in more_links:
            safe_click(chat_driver, link)
            notify("show_more")
            time.sleep(1)
    except WebDriverException:
        pass

    if response_text:
        preview = response_text[:80] + ("…" if len(response_text) > 80 else "")
        notify("gpt_reply", preview=preview)
    return response_text


ANSWER_LINE_RE = re.compile(r"^\s*(\d+[\)\.:\-]\s*)?(?P<value>.+?)\s*$")
NUMBER_RE = re.compile(r"-?\d+(?:[\.,]\d+)?")


def parse_answers(raw_answer: str, expected_fields: int) -> List[str]:
    if not raw_answer.strip():
        return []

    lines = [line for line in raw_answer.splitlines() if line.strip()]
    parsed: List[str] = []

    for line in lines:
        match = ANSWER_LINE_RE.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        value = value.replace("·", ".").replace(",", ".") if NUMBER_RE.fullmatch(value) else value
        parsed.append(value)

    if not parsed:
        parsed = NUMBER_RE.findall(raw_answer)

    if expected_fields and len(parsed) > expected_fields:
        parsed = parsed[:expected_fields]

    return parsed


def answers_look_valid(answers: Sequence[str], expected_fields: int) -> bool:
    if not answers:
        return False
    if expected_fields and len(answers) != expected_fields:
        return False
    for value in answers:
        if any(keyword in value.lower() for keyword in ("drag", "vilkt", "nav", "nevar")):
            return False
    return True


def fill_answers(driver: Chrome, answers: Sequence[str], config: AutomationConfig) -> None:
    inputs = [
        element
        for element in driver.find_elements(
            By.CSS_SELECTOR,
            "input[type='text'],input[type='number'],textarea,input.gxs-answer-number",
        )
        if element.is_displayed()
    ]

    if not inputs:
        notify("no_inputs")
        return

    for field, answer in zip(inputs, answers):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field)
            field.clear()
            field.send_keys(answer)
            time.sleep(0.3)
        except (JavascriptException, WebDriverException):
            continue

    try:
        submit_btn = wait_for(driver, "#submitAnswerBtn", config.wait_timeout, EC.element_to_be_clickable)
        safe_click(driver, submit_btn)
        notify("submitted")
    except AutomationError:
        notify("submit_missing")


def log_result(config: AutomationConfig, task: TaskMetadata, answers: Sequence[str]) -> None:
    if not config.log_file:
        return
    try:
        timestamp = _dt.datetime.now().isoformat(timespec="seconds")
        entry = (
            f"{timestamp}\t{task.subject}\t{task.theme}\t{task.task_title}\t{task.item_type}\t"
            f"{task.points}\t{' | '.join(answers)}\n"
        )
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        with config.log_file.open("a", encoding="utf-8") as handle:
            handle.write(entry)
    except OSError:
        # Žurnāls nav kritisks – ja neizdodas, turpinām darbu.
        pass


def automation_flow(username: str, password: str, config: AutomationConfig) -> None:
    notify("banner")
    with contextlib.ExitStack() as stack:
        uzdevumi_driver = create_driver(config.uzdevumi_profile_dir, config)
        stack.callback(uzdevumi_driver.quit)

        login_via_eklase(uzdevumi_driver, username, password, config)

        exhausted_combinations: Set[Tuple[str, str]] = set()
        while True:
            subject, theme = select_random_subject(
                uzdevumi_driver, config, excluded_combinations=exhausted_combinations
            )
            try:
                task_metadata = ensure_task_with_inputs(uzdevumi_driver, subject, theme, config)
                break
            except NoValidTaskError:
                exhausted_combinations.add((subject, theme))
                notify("no_valid_tasks")
                time.sleep(1)
                continue

        # Mēģinām noskaidrot tēmas nosaukumu pēc navigācijas ceļa
        try:
            breadcrumb = uzdevumi_driver.find_element(By.CSS_SELECTOR, "ol.breadcrumb li.active")
            task_metadata.theme = breadcrumb.text.strip() or task_metadata.theme
        except Exception:
            pass

        notify("open_chatgpt")
        chat_driver = create_driver(config.chatgpt_profile_dir, config)
        stack.callback(chat_driver.quit)
        chat_driver.get("https://chat.openai.com/")
        time.sleep(6)

        answers: List[str] = []
        for attempt in range(1, config.gpt_retry_count + 1):
            raw_answer = send_to_chatgpt(chat_driver, task_metadata.html, config)
            answers = parse_answers(raw_answer, task_metadata.answer_fields)
            if answers_look_valid(answers, task_metadata.answer_fields):
                break
            if attempt < config.gpt_retry_count:
                notify("gpt_retry")
                followup = "Lūdzu atkārto tikai ar atbildēm, katru jaunā rindā, bez paskaidrojumiem."
                textarea = wait_for(chat_driver, "#prompt-textarea", config.wait_timeout)
                textarea.send_keys(Keys.CONTROL, "a")
                textarea.send_keys(Keys.DELETE)
                textarea.send_keys(followup)
                time.sleep(1)
                safe_click(chat_driver, wait_for(chat_driver, "#composer-submit-button", config.wait_timeout, EC.element_to_be_clickable))
                time.sleep(3)
            else:
                notify("gpt_failed")

        if not answers_look_valid(answers, task_metadata.answer_fields):
            notify("invalid_answers")
            return

        notify("filling", values=answers)
        fill_answers(uzdevumi_driver, answers, config)
        log_result(config, task_metadata, answers)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Uzdevumi.lv automatizācijas skripts")
    parser.add_argument("username", nargs="?", help="Personas kods vai lietotājvārds")
    parser.add_argument("password", nargs="?", help="Parole")
    parser.add_argument("--headless", action="store_true", help="Palaiž pārlūku headless režīmā")
    parser.add_argument("--proxy", help="HTTP/HTTPS starpniekserveris", default=None)
    parser.add_argument("--no-log", action="store_true", help="Neveidot results.log ierakstus")
    parser.add_argument("--gui", action="store_true", help="Palaiž Tkinter GUI (ja pieejams)")
    return parser.parse_args(argv)


def run_from_cli(args: argparse.Namespace) -> None:
    config = AutomationConfig(
        headless=args.headless,
        proxy=args.proxy,
        log_file=None if args.no_log else Path("results.log"),
    )

    if args.gui:
        if not TK_AVAILABLE:
            raise AutomationError("Tkinter nav pieejams, GUI režīmu nevar palaist")
        launch_gui(config)
        return

    username = args.username or input("👤 Personas kods: ")
    if args.password:
        password = args.password
    else:
        from getpass import getpass

        password = getpass("🔒 Parole: ")

    automation_flow(username, password, config)


def launch_gui(config: AutomationConfig) -> None:
    if not TK_AVAILABLE:
        raise AutomationError("GUI nav pieejams šajā vidē")

    root = tk.Tk()
    root.title("Uzdevumi.lv Automāts")
    root.geometry("360x240")

    tk.Label(root, text="Personas kods").pack(pady=(10, 0))
    username_var = tk.StringVar()
    username_entry = tk.Entry(root, textvariable=username_var)
    username_entry.pack(fill="x", padx=20)

    tk.Label(root, text="Parole").pack(pady=(10, 0))
    password_var = tk.StringVar()
    password_entry = tk.Entry(root, textvariable=password_var, show="*")
    password_entry.pack(fill="x", padx=20)

    status_var = tk.StringVar(value=LATVIAN_MESSAGES["banner"])
    status_label = tk.Label(root, textvariable=status_var, wraplength=320, justify="left")
    status_label.pack(pady=10)

    running = {"thread": None}

    def set_status(message: str) -> None:
        status_var.set(message)

    def worker() -> None:
        try:
            automation_flow(username_var.get(), password_var.get(), config)
            set_status("✅ Darbs pabeigts")
        except Exception as exc:  # pragma: no cover - GUI kļūdas
            set_status(f"❌ Kļūda: {exc}")

    def start_automation() -> None:
        if running["thread"] and running["thread"].is_alive():
            messagebox.showinfo("Automāts", "Process jau darbojas")
            return
        set_status("🚀 Starts…")
        running["thread"] = threading.Thread(target=worker, daemon=True)
        running["thread"].start()

    tk.Button(root, text="Start", command=start_automation).pack(pady=5)

    def on_close() -> None:
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        run_from_cli(arguments)
    except AutomationError as error:
        print(f"❌ {error}")
        sys.exit(1)


