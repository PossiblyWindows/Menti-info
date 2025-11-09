# -*- coding: utf-8 -*-
"""Automates answering uzdevumi.lv tasks with the help of ChatGPT."""

import argparse
import queue
import random
import re
import sys
import threading
import time
from dataclasses import dataclass
from getpass import getpass
from typing import Callable, Dict, List, Optional

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@dataclass
class TaskOption:
    index: int
    text: str
    option_type: str
    input_element: object
    label_element: object


@dataclass
class TaskData:
    text: str
    options: List[TaskOption]
    points: str


Logger = Optional[Callable[[str], None]]


def log_message(message: str, logger: Logger = None) -> None:
    """Log a message to stdout and the optional callback."""
    print(message)
    if logger is not None:
        try:
            logger(message)
        except Exception:
            # Avoid propagating logging issues to the automation flow.
            pass


def w(driver, css, timeout=10):
    """Wait for a single element by CSS selector."""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css))
        )
    except TimeoutException:
        return None


def w_all(driver, css, timeout=10):
    """Wait for all matching elements by CSS selector."""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, css))
        )
    except TimeoutException:
        return []


def click(driver, element):
    """Scroll into view and click the element."""
    if element is None:
        return
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        element.click()
    except Exception:  # noqa: BLE001 - Selenium raises many exception types
        driver.execute_script("arguments[0].click();", element)


def clear_cookies(driver, logger: Logger = None) -> None:
    """Clear all cookies for the provided driver instance."""
    try:
        driver.delete_all_cookies()
        log_message("🧹  Notīrītas sīkdatnes", logger)
    except Exception:
        log_message("⚠  Neizdevās notīrīt sīkdatnes", logger)


def decline_cookies(driver, logger: Logger = None):
    try:
        button = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#CybotCookiebotDialogBodyButtonDecline"))
        )
    except TimeoutException:
        return
    click(driver, button)
    log_message("🍪  Sīkfaili noraidīti", logger)
    time.sleep(1)


def login(driver, user, password, logger: Logger = None):
    log_message("🔑  Notiek ieiešana…", logger)
    driver.get(
        "https://www.uzdevumi.lv/Sso/AuthRedirect/eklase?authAction=alor&rememberMe=False&isPopup=True"
    )
    time.sleep(3)
    decline_cookies(driver, logger)

    w(driver, "#UserName").send_keys(user)
    w(driver, "div.InputForm_Row:nth-child(2) > input:nth-child(1)").send_keys(password)
    click(driver, w(driver, "#cmdLogonUser"))
    time.sleep(5)

    profiles = w_all(driver, ".UserProfileSelector_Button")
    if profiles:
        click(driver, profiles[0])
        time.sleep(3)

    decline_cookies(driver, logger)
    log_message("✔  Ienākts", logger)


def select_task(driver, logger: Logger = None):
    log_message("📚  Meklē priekšmetu…", logger)
    driver.get("https://www.uzdevumi.lv/p")
    time.sleep(3)
    decline_cookies(driver, logger)

    subjects_list = w(driver, "ul.list-unstyled.thumbnails", 12)
    subjects = []
    if subjects_list is not None:
        candidates = subjects_list.find_elements(By.CSS_SELECTOR, "li.thumb.wide a[href]")
        subjects = [
            (anchor, anchor.text.replace("\n", " ").strip())
            for anchor in candidates
            if "Starpbrīdis" not in anchor.text and "Uzdevumi.lv konkursi" not in anchor.text
        ]

    if not subjects:
        raise RuntimeError("Nav piemērotu priekšmetu")

    anchor, title = subjects[0]
    log_message(f"➡  Priekšmets: {title}", logger)
    click(driver, anchor)
    time.sleep(3)
    decline_cookies(driver, logger)

    try:
        click(driver, driver.find_element(By.CSS_SELECTOR, ".ui-button"))
        time.sleep(1)
    except Exception:
        pass

    topics = [elem for elem in driver.find_elements(By.CSS_SELECTOR, "ol.list-unstyled a[href]") if elem.is_displayed()]
    if not topics:
        raise RuntimeError("Nav tēmu")

    chosen_topic = random.choice(topics)
    log_message(f"➡  Tēma: {chosen_topic.text.strip()}", logger)
    click(driver, chosen_topic)
    time.sleep(3)
    decline_cookies(driver, logger)

    container = None
    for selector in (
        "section.block:nth-child(2) > div:nth-child(2)",
        "section.block:nth-child(1) > div:nth-child(2)",
    ):
        container = w(driver, selector, 6)
        if container is not None:
            break

    if container is None:
        raise RuntimeError("Nav uzdevumu")

    tasks = [elem for elem in container.find_elements(By.CSS_SELECTOR, "a[href]") if elem.is_displayed()]
    selected_task = random.choice(tasks)
    log_message(f"➡  Uzdevums: {selected_task.text.strip()}", logger)
    click(driver, selected_task)
    time.sleep(4)
    decline_cookies(driver, logger)


def fetch_task(driver, logger: Logger = None) -> Optional[TaskData]:
    wrapper = w(driver, "#taskhtml > div", 10)
    if wrapper is None:
        return None

    text_content = wrapper.text.strip()
    summary = text_content.replace("\n", " ")
    if len(summary) > 120:
        summary = summary[:120] + "…"

    points = "0 p."
    points_element = driver.find_elements(By.CSS_SELECTOR, ".obj-points")
    if points_element:
        points = points_element[0].text.strip()

    media_elements = wrapper.find_elements(
        By.CSS_SELECTOR,
        "img,[style*='background-image'],.gxs-resource-image,.gxst-resource-image,.gxs-dnd-option,.answer-box,.ui-draggable",
    )
    if media_elements:
        log_message("⚠  Uzdevums ar bildēm / vilkšanu – izlaižam", logger)
        return "SKIP"

    option_items = wrapper.find_elements(By.CSS_SELECTOR, "ul.gxs-answer-select > li")
    options: List[TaskOption] = []
    for index, item in enumerate(option_items, start=1):
        try:
            input_element = item.find_element(By.CSS_SELECTOR, "input")
        except Exception:
            continue

        try:
            label_element = item.find_element(By.CSS_SELECTOR, "label")
            option_text = label_element.text.strip()
        except Exception:
            label_element = None
            option_text = item.text.strip()

        input_type = (input_element.get_attribute("type") or "").lower()
        options.append(
            TaskOption(
                index=index,
                text=option_text,
                option_type=input_type,
                input_element=input_element,
                label_element=label_element,
            )
        )

    log_message(f"📝  Teksts: {summary}", logger)
    log_message(f"⭐  Punkti: {points}", logger)
    return TaskData(text=text_content, options=options, points=points)


def build_prompt(task: TaskData) -> str:
    """Build a deterministic prompt for ChatGPT based on extracted task text."""
    instructions = [
        "Tu esi asistents, kas risina uzdevumi.lv testus un sniedz tikai galīgo atbildi.",
        "Tev tiek dota #taskhtml > div teksta satura kopija. Analizē to un sagatavo risinājumu.",
        "Atbildes formāts:",
        "- Ja piedāvāti varianti, uzraksti tikai pareizo variantu numurus (1, 2, 3, …), katru jaunā rindā.",
        "- Ja jāaizpilda teksti vai skaitļi, uzraksti katru gala vērtību atsevišķā rindā tādā secībā, kā jāievada.",
        "- Nelieto paskaidrojumus, papildu tekstu, ievadvārdus vai atvainošanos.",
        "- Nesūti vairākas ziņas. Atbildei jābūt vienā īsā sūtījumā ar tikai gala rezultātu.",
    ]

    prompt_parts = ["\n".join(instructions), "", "Uzdevuma teksts:", task.text]

    if task.options:
        options_lines = [f"{option.index}. {option.text}" for option in task.options]
        prompt_parts.extend(["", "Varianti:", "\n".join(options_lines)])

    return "\n".join(prompt_parts)


def ask_chatgpt(task: TaskData, logger: Logger = None):
    """Open ChatGPT, send the prompt, and retrieve the last response."""
    log_message("🤖  Atveru ChatGPT…", logger)
    options = uc.ChromeOptions()
    options.add_argument("--new-window")
    gpt_driver = uc.Chrome(options=options)
    clear_cookies(gpt_driver, logger)
    gpt_driver.get("https://chat.openai.com/")
    time.sleep(8)

    prompt = build_prompt(task)
    textarea = w(gpt_driver, "#prompt-textarea", 15)
    if textarea is None:
        gpt_driver.quit()
        raise RuntimeError("Nevar atrast ChatGPT ievades lauku")

    click(gpt_driver, textarea)
    time.sleep(0.2)

    textarea.send_keys(Keys.CONTROL, "a")
    textarea.send_keys(Keys.DELETE)

    lines = prompt.split("\n")
    ActionChains(gpt_driver).move_to_element(textarea).click().perform()
    time.sleep(0.05)
    for line_index, line in enumerate(lines):
        if line:
            for character in line:
                textarea.send_keys(character)
                time.sleep(0.02)
        if line_index < len(lines) - 1:
            ActionChains(gpt_driver).key_down(Keys.SHIFT, textarea).send_keys(Keys.ENTER).key_up(Keys.SHIFT, textarea).perform()
            time.sleep(0.05)
            ActionChains(gpt_driver).move_to_element(textarea).click().perform()
            time.sleep(0.05)

    typed_prompt = textarea.get_attribute("value") or ""
    if typed_prompt != prompt:
        gpt_driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', {bubbles: true}));",
            textarea,
            prompt,
        )

    time.sleep(0.4)

    send_button = w(gpt_driver, "#composer-submit-button")
    if send_button is None:
        gpt_driver.quit()
        raise RuntimeError("Nevar atrast sūtīšanas pogu")

    click(gpt_driver, send_button)
    log_message("📨  Sūtīts GPT", logger)

    # Wait for the message bubble to finish streaming.
    response_text = ""
    for _ in range(40):
        time.sleep(1.2)
        responses = gpt_driver.find_elements(
            By.CSS_SELECTOR,
            "div.markdown.prose.dark\\:prose-invert.w-full.break-words.dark.markdown-new-styling",
        )
        if responses:
            response_text = responses[-1].text.strip()
            if response_text and not response_text.endswith("…"):
                break

    log_message(
        "💬  GPT atbilde: " + response_text[:80] + ("…" if len(response_text) > 80 else ""),
        logger,
    )
    return response_text, gpt_driver


def parse_answer(answer: str, task: TaskData):
    if not answer:
        return {"mode": "empty", "values": []}

    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if not lines:
        return {"mode": "empty", "values": []}

    if task.options:
        option_map = {option.index: option for option in task.options}
        selected = []

        for line in lines:
            digits = re.findall(r"\d+", line)
            consumed_numeric = False
            for digit in digits:
                index = int(digit)
                if index in option_map and index not in selected:
                    selected.append(index)
                    consumed_numeric = True

            if consumed_numeric:
                continue

            normalized = line.lower()
            for option in task.options:
                if option.text.lower() == normalized and option.index not in selected:
                    selected.append(option.index)
                    break

        return {"mode": "select", "values": selected}

    stripped_lines = [re.sub(r"^\s*\d+[\)\.-:]*\s*", "", line) for line in lines]
    if not stripped_lines:
        stripped_lines = re.findall(r"-?\d+(?:\.\d+)?", answer)
    return {"mode": "text", "values": stripped_lines}


def fill_in_answers(driver, values, logger: Logger = None):
    inputs = driver.find_elements(
        By.CSS_SELECTOR,
        "input[type='text'],input[type='number'],textarea,input.gxs-answer-number",
    )
    if not inputs:
        log_message("⚠  Nav ievades lauku", logger)
        return

    for element, value in zip(inputs, values):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            element.clear()
            element.send_keys(str(value))
        except Exception:
            continue

    submit_button = w(driver, "#submitAnswerBtn")
    if submit_button is not None:
        click(driver, submit_button)
        log_message("✅  Iesniegts", logger)
    else:
        log_message("⚠  Nav pogas", logger)


def select_answers(driver, task: TaskData, indexes: List[int], logger: Logger = None):
    if not indexes:
        log_message("⚠  Nav izvēles atbilžu", logger)
        return

    options = {option.index: option for option in task.options}
    chosen = []
    for index in indexes:
        option = options.get(index)
        if option is None:
            continue

        target = option.label_element if option.label_element else option.input_element
        try:
            click(driver, target)
            chosen.append(index)
        except Exception:
            continue

    if chosen:
        log_message("➡  Atzīmēti varianti: " + ", ".join(str(i) for i in chosen), logger)
        submit_button = w(driver, "#submitAnswerBtn")
        if submit_button is not None:
            click(driver, submit_button)
            log_message("✅  Iesniegts", logger)
        else:
            log_message("⚠  Nav pogas", logger)
    else:
        log_message("⚠  Neizdevās atzīmēt variantus", logger)


def run_automation(user: str, password: str, logger: Logger = None) -> None:
    log_message("=== Uzdevumi.lv bots ===", logger)

    options = uc.ChromeOptions()
    options.add_argument("--incognito")
    driver = uc.Chrome(options=options)
    clear_cookies(driver, logger)

    gpt_driver = None
    try:
        login(driver, user, password, logger)
        select_task(driver, logger)

        task = fetch_task(driver, logger)
        while task == "SKIP":
            log_message("↻  Meklē citu uzdevumu…", logger)
            select_task(driver, logger)
            task = fetch_task(driver, logger)

        if task is None:
            log_message("⚠  Neizdevās iegūt uzdevumu", logger)
            return

        answer, gpt_driver = ask_chatgpt(task, logger)
        parsed = parse_answer(answer, task)

        if parsed["mode"] == "select":
            select_answers(driver, task, parsed["values"], logger)
        elif parsed["mode"] == "text" and parsed["values"]:
            log_message("➡  Ievadām: " + ", ".join(str(v) for v in parsed["values"]), logger)
            fill_in_answers(driver, parsed["values"], logger)
        else:
            log_message("⚠  GPT neatgrieza derīgas vērtības", logger)

        log_message("✅  Automatizācija pabeigta", logger)
    finally:
        try:
            clear_cookies(driver, logger)
        except Exception:
            pass
        driver.quit()
        if gpt_driver:
            try:
                clear_cookies(gpt_driver, logger)
            except Exception:
                pass
            gpt_driver.quit()


def detect_backends() -> Dict[str, object]:
    """Return a mapping of available GUI backend identifiers to their modules."""
    available: Dict[str, object] = {"console": True}

    try:
        import customtkinter as ctk  # type: ignore

        available["customtkinter"] = ctk
    except ImportError:
        pass

    try:
        import tkinter  # noqa: F401 - imported for availability check

        available.setdefault("tkinter", None)
    except ImportError:
        pass

    try:
        from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

        available["pyqt5"] = (QtWidgets, QtCore, QtGui)
    except ImportError:
        pass

    try:
        from PyQt6 import QtCore as QtCore6, QtGui as QtGui6, QtWidgets as QtWidgets6  # type: ignore

        available["pyqt6"] = (QtWidgets6, QtCore6, QtGui6)
    except ImportError:
        pass

    try:
        from PySide2 import QtCore as QtCoreS2, QtGui as QtGuiS2, QtWidgets as QtWidgetsS2  # type: ignore

        available["pyside2"] = (QtWidgetsS2, QtCoreS2, QtGuiS2)
    except ImportError:
        pass

    try:
        from PySide6 import QtCore as QtCoreS6, QtGui as QtGuiS6, QtWidgets as QtWidgetsS6  # type: ignore

        available["pyside6"] = (QtWidgetsS6, QtCoreS6, QtGuiS6)
    except ImportError:
        pass

    return available


def run_customtkinter_ui(
    ctk,
    backend_names: List[str],
    current_backend: str,
) -> Optional[str]:
    import tkinter.messagebox as messagebox

    app = ctk.CTk()
    app.title("Uzdevumi.lv bots")
    app.geometry("520x480")

    next_backend: Optional[str] = None
    running = False
    closing = False

    backend_var = ctk.StringVar(value=current_backend)

    app.grid_columnconfigure(0, weight=1)

    header = ctk.CTkLabel(app, text="Bot", font=("Arial", 20, "bold"))
    header.grid(row=0, column=0, pady=(12, 4))

    backend_frame = ctk.CTkFrame(app)
    backend_frame.grid(row=1, column=0, padx=12, pady=8, sticky="ew")
    backend_frame.grid_columnconfigure(1, weight=1)

    backend_label = ctk.CTkLabel(backend_frame, text="Saskarnes veids")
    backend_label.grid(row=0, column=0, padx=8, pady=8, sticky="w")

    backend_selector = ctk.CTkOptionMenu(
        backend_frame,
        values=backend_names,
        variable=backend_var,
    )
    backend_selector.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

    switch_button = ctk.CTkButton(
        backend_frame,
        text="Pārslēgt",
        command=lambda: request_switch(),
    )
    switch_button.grid(row=0, column=2, padx=8, pady=8)

    credentials = ctk.CTkFrame(app)
    credentials.grid(row=2, column=0, padx=12, pady=8, sticky="ew")
    credentials.grid_columnconfigure(1, weight=1)

    user_label = ctk.CTkLabel(credentials, text="Personas kods")
    user_label.grid(row=0, column=0, padx=8, pady=6, sticky="w")
    user_entry = ctk.CTkEntry(credentials)
    user_entry.grid(row=0, column=1, padx=8, pady=6, sticky="ew")

    password_label = ctk.CTkLabel(credentials, text="Parole")
    password_label.grid(row=1, column=0, padx=8, pady=6, sticky="w")
    password_entry = ctk.CTkEntry(credentials, show="*")
    password_entry.grid(row=1, column=1, padx=8, pady=6, sticky="ew")

    button_frame = ctk.CTkFrame(app)
    button_frame.grid(row=3, column=0, padx=12, pady=8, sticky="ew")

    start_button = ctk.CTkButton(button_frame, text="Sākt", command=lambda: start_automation())
    start_button.grid(row=0, column=0, padx=8, pady=8)

    stop_button = ctk.CTkButton(button_frame, text="Aizvērt", command=app.destroy)
    stop_button.grid(row=0, column=1, padx=8, pady=8)

    log_box = ctk.CTkTextbox(app, height=220)
    log_box.grid(row=4, column=0, padx=12, pady=(8, 12), sticky="nsew")
    app.grid_rowconfigure(4, weight=1)
    log_box.configure(state="disabled")

    log_queue: "queue.Queue[str]" = queue.Queue()

    def append_log(message: str) -> None:
        if closing:
            return
        log_queue.put(message)

    def process_queue() -> None:
        if closing or not log_box.winfo_exists():
            return
        try:
            while True:
                message = log_queue.get_nowait()
                log_box.configure(state="normal")
                log_box.insert("end", message + "\n")
                log_box.see("end")
                log_box.configure(state="disabled")
        except queue.Empty:
            pass
        if not closing:
            app.after(120, process_queue)

    def finish_run() -> None:
        nonlocal running
        running = False
        start_button.configure(state="normal")

    def safe_schedule(callback: Callable[[], None]) -> None:
        if closing:
            return
        try:
            app.after(0, callback)
        except Exception:
            pass

    def worker(user: str, password: str) -> None:
        try:
            run_automation(user, password, logger=append_log)
        except Exception as exc:  # noqa: BLE001
            append_log(f"❌ Kļūda: {exc}")
        finally:
            safe_schedule(finish_run)

    def start_automation() -> None:
        nonlocal running
        if running:
            return

        user = user_entry.get().strip()
        password = password_entry.get().strip()
        if not user or not password:
            messagebox.showerror("Kļūda", "Lūdzu ievadi gan personas kodu, gan paroli.")
            return

        running = True
        start_button.configure(state="disabled")
        threading.Thread(target=worker, args=(user, password), daemon=True).start()

    def request_switch() -> None:
        nonlocal next_backend
        chosen = backend_var.get()
        if chosen == current_backend:
            return
        next_backend = chosen
        on_close()

    def on_close() -> None:
        nonlocal closing
        if closing:
            return
        closing = True
        try:
            app.destroy()
        except Exception:
            pass

    app.protocol("WM_DELETE_WINDOW", lambda: on_close())
    app.after(120, process_queue)
    app.mainloop()
    return next_backend


def run_tkinter_ui(
    backend_names: List[str],
    current_backend: str,
) -> Optional[str]:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("Uzdevumi.lv bots")
    root.geometry("520x480")

    next_backend: Optional[str] = None
    running = False
    closing = False

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(4, weight=1)

    header = ttk.Label(root, text="Bot", font=("Arial", 18, "bold"))
    header.grid(row=0, column=0, pady=(12, 4))

    backend_frame = ttk.Frame(root)
    backend_frame.grid(row=1, column=0, padx=12, pady=8, sticky="ew")
    backend_frame.columnconfigure(1, weight=1)

    ttk.Label(backend_frame, text="Saskarnes veids").grid(row=0, column=0, padx=8, pady=8, sticky="w")

    backend_var = tk.StringVar(value=current_backend)
    backend_menu = ttk.Combobox(
        backend_frame,
        textvariable=backend_var,
        values=backend_names,
        state="readonly",
    )
    backend_menu.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

    def request_switch() -> None:
        nonlocal next_backend
        chosen = backend_var.get()
        if chosen == current_backend:
            return
        next_backend = chosen
        on_close()

    ttk.Button(backend_frame, text="Pārslēgt", command=request_switch).grid(row=0, column=2, padx=8, pady=8)

    credentials = ttk.Frame(root)
    credentials.grid(row=2, column=0, padx=12, pady=8, sticky="ew")
    credentials.columnconfigure(1, weight=1)

    ttk.Label(credentials, text="Personas kods").grid(row=0, column=0, padx=8, pady=6, sticky="w")
    user_entry = ttk.Entry(credentials)
    user_entry.grid(row=0, column=1, padx=8, pady=6, sticky="ew")

    ttk.Label(credentials, text="Parole").grid(row=1, column=0, padx=8, pady=6, sticky="w")
    password_entry = ttk.Entry(credentials, show="*")
    password_entry.grid(row=1, column=1, padx=8, pady=6, sticky="ew")

    button_frame = ttk.Frame(root)
    button_frame.grid(row=3, column=0, padx=12, pady=8)

    log_text = tk.Text(root, height=10, state="disabled")
    log_text.grid(row=4, column=0, padx=12, pady=(8, 12), sticky="nsew")

    log_queue: "queue.Queue[str]" = queue.Queue()

    def append_log(message: str) -> None:
        if closing:
            return
        log_queue.put(message)

    def process_queue() -> None:
        if closing or not log_text.winfo_exists():
            return
        try:
            while True:
                message = log_queue.get_nowait()
                log_text.configure(state="normal")
                log_text.insert("end", message + "\n")
                log_text.see("end")
                log_text.configure(state="disabled")
        except queue.Empty:
            pass
        if not closing:
            root.after(120, process_queue)

    def finish_run() -> None:
        nonlocal running
        running = False
        start_button.configure(state="normal")

    def safe_schedule(callback: Callable[[], None]) -> None:
        if closing:
            return
        try:
            root.after(0, callback)
        except Exception:
            pass

    def worker(user: str, password: str) -> None:
        try:
            run_automation(user, password, logger=append_log)
        except Exception as exc:  # noqa: BLE001
            append_log(f"❌ Kļūda: {exc}")
        finally:
            safe_schedule(finish_run)

    def start_automation() -> None:
        nonlocal running
        if running:
            return
        user = user_entry.get().strip()
        password = password_entry.get().strip()
        if not user or not password:
            messagebox.showerror("Kļūda", "Lūdzu ievadi gan personas kodu, gan paroli.")
            return
        running = True
        start_button.configure(state="disabled")
        threading.Thread(target=worker, args=(user, password), daemon=True).start()

    start_button = ttk.Button(button_frame, text="Sākt", command=start_automation)
    start_button.grid(row=0, column=0, padx=8, pady=8)
    ttk.Button(button_frame, text="Aizvērt", command=lambda: on_close()).grid(
        row=0, column=1, padx=8, pady=8
    )

    def on_close() -> None:
        nonlocal closing
        if closing:
            return
        closing = True
        try:
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(120, process_queue)
    root.mainloop()
    return next_backend


def run_pyqt_ui(
    modules,
    backend_names: List[str],
    current_backend: str,
) -> Optional[str]:
    QtWidgets, QtCore, _ = modules

    pyqt_signal = getattr(QtCore, "pyqtSignal", None)
    if pyqt_signal is None:
        pyqt_signal = getattr(QtCore, "Signal")

    class LogEmitter(QtCore.QObject):
        log_signal = pyqt_signal(str)
        done_signal = pyqt_signal()

    class MainWindow(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Uzdevumi.lv bots")
            self.resize(560, 500)
            self.running = False
            self.next_backend: Optional[str] = None

            layout = QtWidgets.QVBoxLayout(self)

            header = QtWidgets.QLabel("Bot")
            header_font = header.font()
            header_font.setPointSize(18)
            header_font.setBold(True)
            header.setFont(header_font)
            layout.addWidget(header)

            backend_layout = QtWidgets.QHBoxLayout()
            layout.addLayout(backend_layout)
            backend_label = QtWidgets.QLabel("Saskarnes veids")
            backend_layout.addWidget(backend_label)

            self.backend_combo = QtWidgets.QComboBox()
            self.backend_combo.addItems(backend_names)
            index = self.backend_combo.findText(current_backend)
            if index >= 0:
                self.backend_combo.setCurrentIndex(index)
            backend_layout.addWidget(self.backend_combo, 1)

            switch_button = QtWidgets.QPushButton("Pārslēgt")
            switch_button.clicked.connect(self.request_switch)
            backend_layout.addWidget(switch_button)

            form_layout = QtWidgets.QFormLayout()
            layout.addLayout(form_layout)

            self.user_edit = QtWidgets.QLineEdit()
            form_layout.addRow("Personas kods", self.user_edit)

            self.password_edit = QtWidgets.QLineEdit()
            self.password_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            form_layout.addRow("Parole", self.password_edit)

            button_layout = QtWidgets.QHBoxLayout()
            layout.addLayout(button_layout)

            self.start_button = QtWidgets.QPushButton("Sākt")
            self.start_button.clicked.connect(self.start_automation)
            button_layout.addWidget(self.start_button)

            close_button = QtWidgets.QPushButton("Aizvērt")
            close_button.clicked.connect(self.close)
            button_layout.addWidget(close_button)

            self.log_view = QtWidgets.QPlainTextEdit()
            self.log_view.setReadOnly(True)
            layout.addWidget(self.log_view, 1)

            self.emitter = LogEmitter()
            self.emitter.log_signal.connect(self.append_log)
            self.emitter.done_signal.connect(self.finish_run)

        def append_log(self, message: str) -> None:
            self.log_view.appendPlainText(message)
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

        def finish_run(self) -> None:
            self.running = False
            self.start_button.setEnabled(True)

        def request_switch(self) -> None:
            chosen = self.backend_combo.currentText()
            if chosen == current_backend:
                return
            self.next_backend = chosen
            self.close()

        def start_automation(self) -> None:
            if self.running:
                return
            user = self.user_edit.text().strip()
            password = self.password_edit.text().strip()
            if not user or not password:
                QtWidgets.QMessageBox.critical(self, "Kļūda", "Lūdzu ievadi gan personas kodu, gan paroli.")
                return
            self.running = True
            self.start_button.setEnabled(False)

            def worker() -> None:
                try:
                    run_automation(user, password, logger=self.emitter.log_signal.emit)
                except Exception as exc:  # noqa: BLE001
                    self.emitter.log_signal.emit(f"❌ Kļūda: {exc}")
                finally:
                    self.emitter.done_signal.emit()

            threading.Thread(target=worker, daemon=True).start()

    app = QtWidgets.QApplication(sys.argv or ["uzdevumi_bot"])
    window = MainWindow()
    window.show()
    exec_method = getattr(app, "exec", None)
    if exec_method is None:
        exec_method = getattr(app, "exec_")
    exec_method()
    return window.next_backend


def run_pyside_ui(
    modules,
    backend_names: List[str],
    current_backend: str,
) -> Optional[str]:
    QtWidgets, QtCore, _ = modules

    class LogEmitter(QtCore.QObject):
        log_signal = QtCore.Signal(str)
        done_signal = QtCore.Signal()

    class MainWindow(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Uzdevumi.lv bots")
            self.resize(560, 500)
            self.running = False
            self.next_backend: Optional[str] = None

            layout = QtWidgets.QVBoxLayout(self)

            header = QtWidgets.QLabel("Bot")
            header_font = header.font()
            header_font.setPointSize(18)
            header_font.setBold(True)
            header.setFont(header_font)
            layout.addWidget(header)

            backend_layout = QtWidgets.QHBoxLayout()
            layout.addLayout(backend_layout)
            backend_label = QtWidgets.QLabel("Saskarnes veids")
            backend_layout.addWidget(backend_label)

            self.backend_combo = QtWidgets.QComboBox()
            self.backend_combo.addItems(backend_names)
            index = self.backend_combo.findText(current_backend)
            if index >= 0:
                self.backend_combo.setCurrentIndex(index)
            backend_layout.addWidget(self.backend_combo, 1)

            switch_button = QtWidgets.QPushButton("Pārslēgt")
            switch_button.clicked.connect(self.request_switch)
            backend_layout.addWidget(switch_button)

            form_layout = QtWidgets.QFormLayout()
            layout.addLayout(form_layout)

            self.user_edit = QtWidgets.QLineEdit()
            form_layout.addRow("Personas kods", self.user_edit)

            self.password_edit = QtWidgets.QLineEdit()
            self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
            form_layout.addRow("Parole", self.password_edit)

            button_layout = QtWidgets.QHBoxLayout()
            layout.addLayout(button_layout)

            self.start_button = QtWidgets.QPushButton("Sākt")
            self.start_button.clicked.connect(self.start_automation)
            button_layout.addWidget(self.start_button)

            close_button = QtWidgets.QPushButton("Aizvērt")
            close_button.clicked.connect(self.close)
            button_layout.addWidget(close_button)

            self.log_view = QtWidgets.QPlainTextEdit()
            self.log_view.setReadOnly(True)
            layout.addWidget(self.log_view, 1)

            self.emitter = LogEmitter()
            self.emitter.log_signal.connect(self.append_log)
            self.emitter.done_signal.connect(self.finish_run)

        def append_log(self, message: str) -> None:
            self.log_view.appendPlainText(message)
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum()
            )

        def finish_run(self) -> None:
            self.running = False
            self.start_button.setEnabled(True)

        def request_switch(self) -> None:
            chosen = self.backend_combo.currentText()
            if chosen == current_backend:
                return
            self.next_backend = chosen
            self.close()

        def start_automation(self) -> None:
            if self.running:
                return
            user = self.user_edit.text().strip()
            password = self.password_edit.text().strip()
            if not user or not password:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Kļūda",
                    "Lūdzu ievadi gan personas kodu, gan paroli.",
                )
                return
            self.running = True
            self.start_button.setEnabled(False)

            def worker() -> None:
                try:
                    run_automation(user, password, logger=self.emitter.log_signal.emit)
                except Exception as exc:  # noqa: BLE001
                    self.emitter.log_signal.emit(f"❌ Kļūda: {exc}")
                finally:
                    self.emitter.done_signal.emit()

            threading.Thread(target=worker, daemon=True).start()

    app = QtWidgets.QApplication(sys.argv or ["uzdevumi_bot"])
    window = MainWindow()
    window.show()
    exec_method = getattr(app, "exec", None)
    if exec_method is None:
        exec_method = getattr(app, "exec_")
    exec_method()
    return window.next_backend


def run_console_ui(backend_names: List[str], current_backend: str) -> Optional[str]:
    print("=== Uzdevumi.lv bots (konsoles režīms) ===")
    print("Pieejamie saskarnes veidi:")
    for name in backend_names:
        marker = "*" if name == current_backend else "-"
        print(f"  {marker} {name}")

    while True:
        print(
            "\nIzvēlies darbību: [s]ākt, [p]ārslēgt saskarni, [q] iziet",
        )
        command = input("> ").strip().lower()

        if command in ("s", "start", "", "1"):
            user = input("Personas kods: ").strip()
            password = getpass("Parole: ")
            if not user or not password:
                print("⚠  Nepieciešams ievadīt gan personas kodu, gan paroli.")
                continue
            try:
                run_automation(user, password)
            except Exception as exc:  # noqa: BLE001
                print(f"❌ Kļūda: {exc}")
        elif command in ("p", "switch", "2"):
            target = input("Ievadi jauno saskarnes veidu: ").strip().lower()
            if not target or target == current_backend:
                print("⚠  Lūdzu izvēlies citu saskarni.")
                continue
            if target not in backend_names:
                print("⚠  Norādītā saskarne nav pieejama.")
                continue
            return target
        elif command in ("q", "quit", "exit", "3"):
            return None
        else:
            print("⚠  Neatpazīta komanda.")


def launch_gui(default_backend: Optional[str] = "customtkinter") -> None:
    available = detect_backends()
    if not available:
        raise RuntimeError("Nav pieejams neviens grafiskās saskarnes modulis.")

    order = ["customtkinter", "tkinter", "pyqt5", "pyqt6", "pyside6", "pyside2", "console"]
    backend_names = [candidate for candidate in order if candidate in available]

    backend = default_backend if (default_backend and default_backend in available) else None
    if backend is None:
        backend = backend_names[0] if backend_names else next(iter(available.keys()))

    if backend is None:
        backend = next(iter(available.keys()))

    while backend is not None:
        if backend == "customtkinter":
            modules = available.get("customtkinter")
            if modules is None:
                backend = "tkinter"
                continue
            backend = run_customtkinter_ui(modules, backend_names, backend) or None
        elif backend == "tkinter":
            backend = run_tkinter_ui(backend_names, backend) or None
        elif backend in ("pyqt5", "pyqt6"):
            modules = available.get(backend)
            if modules is None:
                backend = None
                continue
            backend = run_pyqt_ui(modules, backend_names, backend) or None
        elif backend in ("pyside2", "pyside6"):
            modules = available.get(backend)
            if modules is None:
                backend = None
                continue
            backend = run_pyside_ui(modules, backend_names, backend) or None
        elif backend == "console":
            backend = run_console_ui(backend_names, backend) or None
        else:
            backend = None


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Uzdevumi.lv bota palīgs")
    parser.add_argument(
        "--backend",
        choices=[
            "customtkinter",
            "tkinter",
            "pyqt5",
            "pyqt6",
            "pyside2",
            "pyside6",
            "console",
        ],
        help="Piespiedu grafiskās saskarnes izvēle, ja pieejama.",
    )
    args = parser.parse_args(argv)
    launch_gui(default_backend=args.backend or "customtkinter")


if __name__ == "__main__":
    main()
