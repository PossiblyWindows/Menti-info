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
from selenium.webdriver.support.select import Select

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
    "skip_task": "⚠ Uzdevums ar neatbalstītu interaktīvu saturu – izlaižam",
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
UNSUPPORTED_MARKERS = (
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
        return any(marker in html_lower for marker in UNSUPPORTED_MARKERS)


@dataclasses.dataclass(slots=True)
class TaskOption:
    element: Any
    title: str
    item_type: str
    completed: bool
    href: str


@dataclasses.dataclass(slots=True)
class AnswerField:
    kind: str
    element: Any
    name: str = ""
    options: List[Tuple[str, Any]] = dataclasses.field(default_factory=list)


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


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    concat_parts: List[str] = []
    for index, part in enumerate(parts):
        if part:
            concat_parts.append(f"'{part}'")
        if index != len(parts) - 1:
            concat_parts.append("\"'\"")
    return "concat(" + ", ".join(concat_parts) + ")"


def get_label_text(container, control) -> str:
    text = ""
    control_id = control.get_attribute("id") or ""
    if control_id:
        try:
            label = container.find_element(By.XPATH, f".//label[@for={xpath_literal(control_id)}]")
            text = label.text.strip()
        except NoSuchElementException:
            text = ""
    if not text:
        try:
            label = control.find_element(By.XPATH, "ancestor::label[1]")
            text = label.text.strip()
        except NoSuchElementException:
            text = ""
    if not text:
        text = (control.text or control.get_attribute("value") or "").strip()
    return text


def gather_answer_fields(driver: Chrome) -> List[AnswerField]:
    try:
        form = driver.find_element(By.CSS_SELECTOR, "form.taskForm")
    except NoSuchElementException:
        return []

    controls = form.find_elements(By.CSS_SELECTOR, "input,textarea,select")
    fields: List[AnswerField] = []
    seen_radio: Set[str] = set()
    seen_checkbox: Set[str] = set()

    for control in controls:
        if not control.is_displayed():
            continue
        tag = control.tag_name.lower()
        if tag == "select":
            options = []
            for option in control.find_elements(By.TAG_NAME, "option"):
                option_text = option.text.strip()
                if not option_text:
                    continue
                options.append((option_text, option))
            fields.append(
                AnswerField(
                    kind="select",
                    element=control,
                    name=control.get_attribute("name") or "",
                    options=options,
                )
            )
        elif tag == "textarea":
            fields.append(
                AnswerField(
                    kind="text", element=control, name=control.get_attribute("name") or ""
                )
            )
        elif tag == "input":
            input_type = (control.get_attribute("type") or "").lower()
            if input_type in {"text", "number", "email", "tel"}:
                fields.append(
                    AnswerField(
                        kind="text",
                        element=control,
                        name=control.get_attribute("name") or "",
                    )
                )
            elif input_type == "radio":
                group_name = control.get_attribute("name") or ""
                if group_name in seen_radio:
                    continue
                seen_radio.add(group_name)
                literal = xpath_literal(group_name)
                radios = form.find_elements(
                    By.XPATH, f".//input[@type='radio' and @name={literal}]"
                )
                options = []
                for radio in radios:
                    if not radio.is_displayed():
                        continue
                    label_text = get_label_text(form, radio)
                    options.append((label_text, radio))
                fields.append(
                    AnswerField(
                        kind="radio",
                        element=control,
                        name=group_name,
                        options=options,
                    )
                )
            elif input_type == "checkbox":
                group_name = control.get_attribute("name") or ""
                if group_name in seen_checkbox:
                    continue
                seen_checkbox.add(group_name)
                literal = xpath_literal(group_name)
                boxes = form.find_elements(
                    By.XPATH, f".//input[@type='checkbox' and @name={literal}]"
                )
                options = []
                for box in boxes:
                    if not box.is_displayed():
                        continue
                    label_text = get_label_text(form, box)
                    options.append((label_text, box))
                fields.append(
                    AnswerField(
                        kind="checkbox",
                        element=control,
                        name=group_name,
                        options=options,
                    )
                )

    return fields

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
        class_name = (section.get_attribute("class") or "").lower()
        heading = ""
        for selector in ("h2", "h3", "header h3", "header h2"):
            try:
                heading = section.find_element(By.CSS_SELECTOR, selector).text.strip()
            except NoSuchElementException:
                continue
            if heading:
                break
        heading_lower = heading.lower()
        item_type = "Tests" if "test" in heading_lower or "test" in class_name else "Uzdevums"

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
                    if row.find_elements(By.CSS_SELECTOR, ".svg-sprite-vs.top-point-full"):
                        completed = True
                    else:
                        earned = row.find_element(By.CSS_SELECTOR, ".points .earned").text.strip()
                        maximum = row.find_element(By.CSS_SELECTOR, ".points .max").text.strip()
                        if earned and maximum and earned == maximum:
                            completed = True
                except NoSuchElementException:
                    try:
                        if row.find_elements(By.CSS_SELECTOR, ".svg-sprite-vs.top-point-full"):
                            completed = True
                    except NoSuchElementException:
                        completed = False
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
    task_title: str,
    item_type: str,
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

    fields = gather_answer_fields(driver)
    answer_fields = len(fields)

    metadata = TaskMetadata(
        subject=subject,
        theme=theme,
        task_title=task_title,
        item_type=item_type,
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


def ensure_task_with_inputs(
    driver: Chrome, subject: str, theme: str, config: AutomationConfig
) -> Tuple[TaskMetadata, TaskOption]:
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
        metadata = extract_task_metadata(
            driver, subject, theme, selected_task.title, selected_task.item_type, config
        )
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
        return metadata, selected_task


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


def send_chatgpt_message(chat_driver: Chrome, message: str, config: AutomationConfig) -> str:
    try:
        textarea = wait_for(chat_driver, "#prompt-textarea", config.wait_timeout)
    except AutomationError as exc:
        raise AutomationError("Neizdevās atrast ChatGPT ievades lauku") from exc

    textarea.send_keys(Keys.CONTROL, "a")
    textarea.send_keys(Keys.DELETE)
    textarea.send_keys(message)
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


def obtain_answers_from_gpt(
    chat_driver: Chrome, html: str, expected_fields: int, config: AutomationConfig
) -> List[str]:
    answers = parse_answers(
        send_chatgpt_message(chat_driver, build_prompt(html), config), expected_fields
    )
    if answers_look_valid(answers, expected_fields):
        return answers

    for _ in range(1, config.gpt_retry_count):
        notify("gpt_retry")
        raw = send_chatgpt_message(
            chat_driver,
            "Lūdzu atkārto tikai ar atbildēm, katru jaunā rindā, bez paskaidrojumiem.",
            config,
        )
        answers = parse_answers(raw, expected_fields)
        if answers_look_valid(answers, expected_fields):
            return answers

    notify("gpt_failed")
    return []


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()) if value else ""


def split_multi_answer(value: str) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[;,/]+", value)
    return [part.strip() for part in parts if part.strip()]


def fill_answers(driver: Chrome, answers: Sequence[str], config: AutomationConfig) -> bool:
    fields = gather_answer_fields(driver)
    if not fields:
        notify("no_inputs")
        return False

    for field, answer in zip(fields, answers):
        if field.kind == "text":
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field.element)
                field.element.clear()
                field.element.send_keys(answer)
                time.sleep(0.3)
            except (JavascriptException, WebDriverException):
                continue
        elif field.kind == "select":
            selection = Select(field.element)
            normalized_answer = normalize_text(answer)
            matched = False
            for option_text, _ in field.options:
                if normalize_text(option_text) == normalized_answer:
                    selection.select_by_visible_text(option_text)
                    matched = True
                    break
            if not matched:
                for option_text, _ in field.options:
                    if normalized_answer and normalized_answer in normalize_text(option_text):
                        selection.select_by_visible_text(option_text)
                        matched = True
                        break
            if not matched and field.options:
                try:
                    selection.select_by_value(answer)
                    matched = True
                except Exception:
                    matched = False
            if not matched and field.options:
                selection.select_by_visible_text(field.options[0][0])
        elif field.kind == "radio":
            normalized_answer = normalize_text(answer)
            choice = None
            for option_text, option_element in field.options:
                if normalize_text(option_text) == normalized_answer:
                    choice = option_element
                    break
            if not choice:
                for option_text, option_element in field.options:
                    if normalized_answer and normalized_answer in normalize_text(option_text):
                        choice = option_element
                        break
            if not choice and field.options:
                choice = field.options[0][1]
            if choice:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", choice)
                    safe_click(driver, choice)
                    time.sleep(0.2)
                except (JavascriptException, WebDriverException):
                    continue
        elif field.kind == "checkbox":
            desired = {normalize_text(value) for value in split_multi_answer(answer)}
            if not desired and field.options:
                desired.add(normalize_text(field.options[0][0]))
            for option_text, option_element in field.options:
                normalized_option = normalize_text(option_text)
                should_select = normalized_option in desired or option_text in answers
                try:
                    already = option_element.is_selected()
                except WebDriverException:
                    already = False
                if should_select and not already:
                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", option_element
                        )
                        safe_click(driver, option_element)
                        time.sleep(0.2)
                    except (JavascriptException, WebDriverException):
                        continue
                if not should_select and already:
                    try:
                        safe_click(driver, option_element)
                    except (JavascriptException, WebDriverException):
                        continue

    try:
        submit_btn = wait_for(driver, "#submitAnswerBtn", config.wait_timeout, EC.element_to_be_clickable)
        safe_click(driver, submit_btn)
        notify("submitted")
        return True
    except AutomationError:
        notify("submit_missing")
        return False


def has_finish_block(driver: Chrome) -> bool:
    try:
        block = driver.find_element(By.CSS_SELECTOR, ".block.sm-easy-header")
    except NoSuchElementException:
        return False
    return bool(block.find_elements(By.CSS_SELECTOR, ".btn"))


def wait_for_next_question(driver: Chrome, previous_html: str, config: AutomationConfig) -> bool:
    deadline = time.time() + config.wait_timeout
    while time.time() < deadline:
        if has_finish_block(driver):
            return False
        try:
            element = driver.find_element(By.CSS_SELECTOR, "#taskhtml")
            current_html = element.get_attribute("innerHTML") or ""
            if current_html.strip() and current_html != previous_html:
                return True
        except NoSuchElementException:
            pass
        time.sleep(1)
    return False


def finalize_test_if_available(driver: Chrome, config: AutomationConfig) -> None:
    try:
        block = driver.find_element(By.CSS_SELECTOR, ".block.sm-easy-header")
    except NoSuchElementException:
        return
    buttons = block.find_elements(By.CSS_SELECTOR, "button.btn")
    target = None
    for button in buttons:
        classes = (button.get_attribute("class") or "").lower()
        if "primary" in classes:
            target = button
            break
    if not target and buttons:
        target = buttons[0]
    if target:
        try:
            safe_click(driver, target)
            time.sleep(2)
        except WebDriverException:
            pass


def solve_question(
    uzdevumi_driver: Chrome,
    chat_driver: Chrome,
    metadata: TaskMetadata,
    config: AutomationConfig,
) -> List[str]:
    answers = obtain_answers_from_gpt(chat_driver, metadata.html, metadata.answer_fields, config)
    if not answers_look_valid(answers, metadata.answer_fields):
        notify("invalid_answers")
        return []
    notify("filling", values=answers)
    submitted = fill_answers(uzdevumi_driver, answers, config)
    if not submitted:
        return []
    return answers


def solve_test_sequence(
    uzdevumi_driver: Chrome,
    chat_driver: Chrome,
    metadata: TaskMetadata,
    config: AutomationConfig,
) -> List[str]:
    all_answers: List[str] = []
    current_metadata = metadata
    question_index = 1

    while True:
        answers = obtain_answers_from_gpt(
            chat_driver, current_metadata.html, current_metadata.answer_fields, config
        )
        if not answers_look_valid(answers, current_metadata.answer_fields):
            notify("invalid_answers")
            break
        notify("filling", values=answers)
        submitted = fill_answers(uzdevumi_driver, answers, config)
        if not submitted:
            break
        all_answers.append(f"{question_index}. {' | '.join(answers)}")
        if not wait_for_next_question(uzdevumi_driver, current_metadata.html, config):
            finalize_test_if_available(uzdevumi_driver, config)
            break
        try:
            current_metadata = extract_task_metadata(
                uzdevumi_driver,
                metadata.subject,
                metadata.theme,
                metadata.task_title,
                metadata.item_type,
                config,
            )
            if current_metadata.should_skip:
                break
        except AutomationError:
            break
        question_index += 1

    return all_answers


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
        selected_task: Optional[TaskOption] = None
        while True:
            subject, theme = select_random_subject(
                uzdevumi_driver, config, excluded_combinations=exhausted_combinations
            )
            try:
                task_metadata, selected_task = ensure_task_with_inputs(
                    uzdevumi_driver, subject, theme, config
                )
                break
            except NoValidTaskError:
                exhausted_combinations.add((subject, theme))
                notify("no_valid_tasks")
                time.sleep(1)
                continue

        if selected_task is None:
            raise AutomationError("Neizdevās atlasīt uzdevumu")

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

        if selected_task.item_type == "Tests":
            answers = solve_test_sequence(uzdevumi_driver, chat_driver, task_metadata, config)
            if not answers:
                return
            log_result(config, task_metadata, answers)
        else:
            answers = solve_question(uzdevumi_driver, chat_driver, task_metadata, config)
            if not answers:
                return
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


