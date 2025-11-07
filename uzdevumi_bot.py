# -*- coding: utf-8 -*-
"""Automates answering uzdevumi.lv tasks with the help of ChatGPT."""

import random
import re
import sys
import time
from getpass import getpass

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


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


def decline_cookies(driver):
    try:
        button = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#CybotCookiebotDialogBodyButtonDecline"))
        )
    except TimeoutException:
        return
    click(driver, button)
    print("🍪  Sīkfaili noraidīti")
    time.sleep(1)


def login(driver, user, password):
    print("🔑  Ieiešana…")
    driver.get(
        "https://www.uzdevumi.lv/Sso/AuthRedirect/eklase?authAction=alor&rememberMe=False&isPopup=True"
    )
    time.sleep(3)
    decline_cookies(driver)

    w(driver, "#UserName").send_keys(user)
    w(driver, "div.InputForm_Row:nth-child(2) > input:nth-child(1)").send_keys(password)
    click(driver, w(driver, "#cmdLogonUser"))
    time.sleep(5)

    profiles = w_all(driver, ".UserProfileSelector_Button")
    if profiles:
        click(driver, profiles[0])
        time.sleep(3)

    decline_cookies(driver)
    print("✔  Ienākts")


def select_task(driver):
    print("📚  Meklē priekšmetu…")
    driver.get("https://www.uzdevumi.lv/p")
    time.sleep(3)
    decline_cookies(driver)

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
        sys.exit("Nav piemērotu priekšmetu")

    anchor, title = subjects[0]
    print(f"➡  Priekšmets: {title}")
    click(driver, anchor)
    time.sleep(3)
    decline_cookies(driver)

    try:
        click(driver, driver.find_element(By.CSS_SELECTOR, ".ui-button"))
        time.sleep(1)
    except Exception:
        pass

    topics = [elem for elem in driver.find_elements(By.CSS_SELECTOR, "ol.list-unstyled a[href]") if elem.is_displayed()]
    if not topics:
        sys.exit("Nav tēmu")

    chosen_topic = random.choice(topics)
    print(f"➡  Tēma: {chosen_topic.text.strip()}")
    click(driver, chosen_topic)
    time.sleep(3)
    decline_cookies(driver)

    container = None
    for selector in (
        "section.block:nth-child(2) > div:nth-child(2)",
        "section.block:nth-child(1) > div:nth-child(2)",
    ):
        container = w(driver, selector, 6)
        if container is not None:
            break

    if container is None:
        sys.exit("Nav uzdevumu")

    tasks = [elem for elem in container.find_elements(By.CSS_SELECTOR, "a[href]") if elem.is_displayed()]
    selected_task = random.choice(tasks)
    print(f"➡  Uzdevums: {selected_task.text.strip()}")
    click(driver, selected_task)
    time.sleep(4)
    decline_cookies(driver)


def fetch_task(driver):
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
        print("⚠  Uzdevums ar bildēm / vilkšanu – izlaižam")
        return "SKIP"

    option_items = wrapper.find_elements(By.CSS_SELECTOR, "ul.gxs-answer-select > li")
    options = []
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

        input_type = input_element.get_attribute("type") or ""
        options.append(
            {
                "index": index,
                "text": option_text,
                "type": input_type.lower(),
                "input": input_element,
                "label": label_element,
            }
        )

    print(f"📝  Teksts: {summary}")
    print(f"⭐  Punkti: {points}")
    return {
        "text": text_content,
        "options": options,
        "points": points,
    }


def build_prompt(task):
    """Build a deterministic prompt for ChatGPT based on extracted task text."""
    base = [
        "Tu esi asistents, kas risina uzdevumi.lv testus un sniedz tikai galīgo atbildi.",
        "Tev tiek dota #taskhtml > div teksta satura kopija. Analizē to un sagatavo risinājumu.",
        "Atbildes formāts:",
        "- Ja piedāvāti varianti, atgriez to numurus (1, 2, 3, …) pareizajā secībā, katru jaunā rindā.",
        "- Ja jāaizpilda teksts vai skaitļi, atgriez katru vērtību atsevišķā rindā.",
        "- Ja nevari noteikt atbildi, neatbildi vispār.",
        "- Nekādu paskaidrojumu, ievada vai papildteksta — tikai rezultāts.",
        "- Sniedz atbildi vienā sūtījumā bez turpinājumiem vai paskaidrojumiem.",
    ]

    prompt = "\n".join(base)
    prompt += "\n\nUzdevuma teksts:\n"
    prompt += task["text"]

    if task["options"]:
        options_lines = [
            f"{option['index']}. {option['text']}"
            for option in task["options"]
        ]
        prompt += "\n\nVarianti:\n" + "\n".join(options_lines)

    prompt += "\n"
    return prompt


def ask_chatgpt(task):
    """Open ChatGPT, send the prompt, and retrieve the last response."""
    print("🤖  Atveru ChatGPT…")
    options = uc.ChromeOptions()
    options.add_argument("--user-data-dir=./chatgpt_profils")
    options.add_argument("--new-window")
    gpt_driver = uc.Chrome(options=options)
    gpt_driver.get("https://chat.openai.com/")
    time.sleep(8)

    prompt = build_prompt(task)
    textarea = w(gpt_driver, "#prompt-textarea", 15)
    if textarea is None:
        gpt_driver.quit()
        sys.exit("Nevar atrast ChatGPT ievades lauku")

    textarea.send_keys(Keys.CONTROL, "a")
    textarea.send_keys(Keys.DELETE)
    textarea.send_keys(prompt)
    time.sleep(1)
    click(gpt_driver, w(gpt_driver, "#composer-submit-button"))
    print("📨  Sūtīts GPT")

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

    print("💬  GPT atbilde:", response_text[:80] + ("…" if len(response_text) > 80 else ""))
    return response_text, gpt_driver


def parse_answer(answer, task):
    if not answer:
        return {"mode": "empty", "values": []}

    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if not lines:
        return {"mode": "empty", "values": []}

    if task["options"]:
        option_map = {option["index"]: option for option in task["options"]}
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
            for option in task["options"]:
                if option["text"].lower() == normalized and option["index"] not in selected:
                    selected.append(option["index"])
                    break

        return {"mode": "select", "values": selected}

    stripped_lines = [re.sub(r"^\s*\d+[\)\.-:]*\s*", "", line) for line in lines]
    if not stripped_lines:
        stripped_lines = re.findall(r"-?\d+(?:\.\d+)?", answer)
    return {"mode": "text", "values": stripped_lines}


def fill_in_answers(driver, values):
    inputs = driver.find_elements(
        By.CSS_SELECTOR,
        "input[type='text'],input[type='number'],textarea,input.gxs-answer-number",
    )
    if not inputs:
        print("⚠  Nav ievades lauku")
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
        print("✅  Iesniegts")
    else:
        print("⚠  Nav pogas")


def select_answers(driver, task, indexes):
    if not indexes:
        print("⚠  Nav izvēles atbilžu")
        return

    options = {option["index"]: option for option in task["options"]}
    chosen = []
    for index in indexes:
        option = options.get(index)
        if option is None:
            continue

        target = option["label"] if option["label"] else option["input"]
        try:
            click(driver, target)
            chosen.append(index)
        except Exception:
            continue

    if chosen:
        print("➡  Atzīmēti varianti:", ", ".join(str(i) for i in chosen))
        submit_button = w(driver, "#submitAnswerBtn")
        if submit_button is not None:
            click(driver, submit_button)
            print("✅  Iesniegts")
        else:
            print("⚠  Nav pogas")
    else:
        print("⚠  Neizdevās atzīmēt variantus")


def main():
    print("=== Uzdevumi.lv Automāts ===")
    user = input("👤 Personas kods: ")
    password = getpass("🔒 Parole: ")

    options = uc.ChromeOptions()
    options.add_argument("--user-data-dir=./uzdevumi_profils")
    driver = uc.Chrome(options=options)

    gpt_driver = None
    try:
        login(driver, user, password)
        select_task(driver)

        task = fetch_task(driver)
        while task == "SKIP":
            print("↻  Meklē citu uzdevumu…")
            select_task(driver)
            task = fetch_task(driver)

        if task is None:
            print("⚠  Neizdevās iegūt uzdevumu")
            return

        answer, gpt_driver = ask_chatgpt(task)
        parsed = parse_answer(answer, task)

        if parsed["mode"] == "select":
            select_answers(driver, task, parsed["values"])
        elif parsed["mode"] == "text" and parsed["values"]:
            print("➡  Ievadām:", parsed["values"])
            fill_in_answers(driver, parsed["values"])
        else:
            print("⚠  GPT neatgrieza derīgas vērtības")

        input("\nEnter — aizvērt pārlūkus…")
    finally:
        driver.quit()
        if gpt_driver:
            gpt_driver.quit()


if __name__ == "__main__":
    main()
