import argparse
import json
import os
import queue
import random
import re
import sys
import threading
import time
import hashlib
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

I18N_URL = {
    "lv": "https://www.google.com/intl/lv/chrome/",
    "en": "https://www.google.com/chrome/",
    "ru": "https://www.google.com/intl/ru/chrome/",
}
CHROME_PATH = Path(r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
DEFAULT_LANG = "lv"

if not CHROME_PATH.exists():
    sys.exit(
        "❗ "
        + {
            "lv": "Nepieciešams Google Chrome! Lejupielādē no:",
            "en": "Google Chrome is required! Download from:",
            "ru": "Требуется Google Chrome! Скачайте по ссылке:",
        }[DEFAULT_LANG]
        + f" {I18N_URL[DEFAULT_LANG]}"
    )


import requests
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchWindowException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select

# ----------------------- CONFIG -----------------------

KEYSYS_BASE = "https://keysys.djcookfan61.workers.dev"
KEYSYS_VALIDATE = KEYSYS_BASE + "/validate"

REG_PATH = r"Software\\Keysys\\UzdevumiBot"
TRIAL_MINUTES = 120
CONFIG_PATH = Path.home() / ".uzdevumi_bot" / "credentials.json"

# ----------------------- i18n -------------------------

I18N = {
    "lv": {
        # Titles / generic
        "title": "Uzdevumi.lv Bots",
        "status": "Statuss",
        "info": "Informācija",
        # Auth / site flow
        "login_start": "Notiek ieiešana…",
        "cookies_declined": "Sīkfaili noraidīti",
        "logged_in": "Ienākts",
        "find_subject": "Meklē priekšmetu…",
        "subject": "Priekšmets: {x}",
        "topic": "Tēma: {x}",
        "task": "Uzdevums: {x}",
        "text": "Teksts: {x}",
        "points": "Punkti: {x}",
        "img_task_skip": "Uzdevums ar bildēm vai vilkšanu – wtf",
        "open_gpt": "Atveru ChatGPT…",
        "sent_gpt": "Sūtīts GPT",
        "gpt_ans": "GPT atbilde: {x}",
        "marked": "Atzīmēti varianti: {x}",
        "submitted": "Iesniegts",
        "no_inputs": "Nav ievades lauku",
        "no_btn": "Nav pogas",
        "no_valid": "GPT neatgrieza derīgas vērtības",
        "done": "Automatizācija pabeigta",
        "debug_keep": "Pārlūki paliek atvērti",
        "cycle": "Cikls #{x}",
        "points_val": "Uzdevuma punktu vērtība (etikete): {x}",
        "top_start": "Sākuma Top punkti: {a}{b}",
        "top_target": "→ mērķis: {t}",
        "top_now": "Pašreizējie Top punkti: {x}",
        "top_reached": "Sasniegts mērķis: {a} ≥ {b}",
        "retry": "Mēģinājums {a}/{b}…",
        # UI
        "ui_username": "Personas kods",
        "ui_password": "Parole",
        "ui_debug": "Atstāt pārlūkus atvērtus",
        "ui_until": "--until-top (piem., 1600)",
        "ui_gain": "--gain (piem., 25)",
        "ui_start": "Sākt",
        "ui_close": "Aizvērt",
        "ui_error_need_creds": "Lūdzu ievadi gan personas kodu, gan paroli.",
        "ui_lang": "Valoda",
        # License UI
        "ui_license": "Licence",
        "ui_license_user": "Licences lietotājvārds",
        "ui_license_key": "Licences atslēga",
        "ui_license_user_ph": "Jūsu lietotājvārds",
        "ui_license_key_ph": "XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX",
        "ui_check_license": "Pārbaudīt licenci",
        "ui_end_trial": "Beigt izmēģinājumu un izmantot licenci",
        "ui_trial_left": "Atlicis izmēģinājuma laiks: {h}:{m:02d}:{s:02d}",
        "ui_trial_expired": "Izmēģinājums beidzies — nepieciešama licence.",
        "ui_licensed": "Licencēts: {u}",
        "ui_popup_title": "Licence",
        "ui_popup_msg": "Ievadi lietotājvārdu un licences atslēgu:",
        "ui_popup_btn_ok": "Apstiprināt",
        "ui_popup_btn_cancel": "Atcelt",
        # Prompt for ChatGPT
        "p1": "Tu esi asistents, kas risina uzdevumi.lv testus un sniedz tikai galīgo atbildi.",
        "p2": "Tev tiek dota #taskhtml > div teksta satura kopija. Analizē to un sagatavo risinājumu.",
        "p3": "Atbildes formāts:",
        "p4": "- Izvēles varianti: raksti tikai numurus vai burtus (1/A, 2/B, …), katru jaunā rindā.",
        "p5": "- Vairāki ievades lauki: katru rezultātu jaunā rindā tādā pašā secībā.",
        "p6": "- Dropdowniem: katrai rindai izvēlies vienu (burts A/B/C… vai teksts).",
        "p7": "- Bez paskaidrojumiem. Viena īsa atbilde ar tikai gala rezultātu.",
        "p8": "Uzdevuma teksts:",
        "p_radio_hdr": "Varianti (radio/checkbox):",
        "p_drop_hdr": "Varianti (dropdown):",
        # License logs
        "lic_start_trial": "Sākta izmēģinājuma versija (120 min).",
        "lic_trial_left": "Atlikušas izmēģinājuma minūtes: {m}",
        "lic_trial_expired": "Izmēģinājuma laiks beidzies. Nepieciešama licence.",
        "lic_valid": "Licence derīga. Lietotājs: {u}",
        "lic_revoked": "Licence atsaukta: {r}",
        "lic_invalid": "Nederīga licence.",
        "lic_hwid_mismatch": "HWID neatbilst šai ierīcei.",
        "lic_error": "Licence servera kļūda: {e}",
        "lic_burned": "Izmēģinājums ir beigts.",
        "cli_need_key": "Aktīvs licences režīms — norādi --license-user un --license.",
        "save_success": "Pieteikšanās dati saglabāti.",
        "load_success": "Atrasti saglabātie pieteikšanās dati.",
        "load_missing": "Saglabāti pieteikšanās dati nav atrasti.",
        "driver_restart": "Pārlūks restartēts kļūdas dēļ.",
        "send_retry": "Sūtīšana neizdevās, mēģinu vēlreiz…",
    },
    "en": {
        "title": "Uzdevumi.lv bot",
        "status": "Status",
        "info": "Info",
        "login_start": "Logging in…",
        "cookies_declined": "Cookies declined",
        "logged_in": "Logged in",
        "find_subject": "Picking a subject…",
        "subject": "Subject: {x}",
        "topic": "Topic: {x}",
        "task": "Task: {x}",
        "text": "Text: {x}",
        "points": "Points: {x}",
        "img_task_skip": "Image or drag task — skipping",
        "open_gpt": "Opening ChatGPT…",
        "sent_gpt": "Sent to GPT",
        "gpt_ans": "GPT answer: {x}",
        "marked": "Marked options: {x}",
        "submitted": "Submitted",
        "no_inputs": "No input fields",
        "no_btn": "No submit button",
        "no_valid": "GPT returned no valid values",
        "done": "Automation done",
        "debug_keep": "Keeping browsers open",
        "cycle": "Cycle #{x}",
        "points_val": "Task points (label): {x}",
        "top_start": "Starting Top points: {a}{b}",
        "top_target": "→ target: {t}",
        "top_now": "Current Top points: {x}",
        "top_reached": "Target reached: {a} ≥ {b}",
        "retry": "Retry {a}/{b}…",
        "ui_username": "User ID",
        "ui_password": "Password",
        "ui_debug": "Keep browsers open",
        "ui_until": "--until-top (e.g., 1600)",
        "ui_gain": "--gain (e.g., 25)",
        "ui_start": "Start",
        "ui_close": "Close",
        "ui_error_need_creds": "Please enter both user ID and password.",
        "ui_lang": "Language",
        "ui_license": "License",
        "ui_license_user": "License username",
        "ui_license_key": "License key",
        "ui_license_user_ph": "Your username",
        "ui_license_key_ph": "XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX",
        "ui_check_license": "Check license",
        "ui_end_trial": "End trial and use license",
        "ui_trial_left": "Trial time left: {h}:{m:02d}:{s:02d}",
        "ui_trial_expired": "Trial expired — license required.",
        "ui_licensed": "Licensed: {u}",
        "ui_popup_title": "License",
        "ui_popup_msg": "Enter username and license key:",
        "ui_popup_btn_ok": "Confirm",
        "ui_popup_btn_cancel": "Cancel",
        "p1": "You are an assistant solving uzdevumi.lv tasks and you must output only the final answer.",
        "p2": "You are given the text content of #taskhtml > div. Analyze and produce the solution.",
        "p3": "Answer format:",
        "p4": "- Multiple choice: write only numbers or letters (1/A, 2/B, …), each on a new line.",
        "p5": "- Several input fields: write each final value on a new line in the same order.",
        "p6": "- Dropdowns: for each line choose one (letter A/B/C… or visible text).",
        "p7": "- No explanations. One short message with only the final result.",
        "p8": "Task text:",
        "p_radio_hdr": "Options (radio/checkbox):",
        "p_drop_hdr": "Options (dropdown):",
        "lic_start_trial": "Trial started (120 min).",
        "lic_trial_left": "Trial minutes left: {m}",
        "lic_trial_expired": "Trial expired. License required.",
        "lic_valid": "License valid. User: {u}",
        "lic_revoked": "License revoked: {r}",
        "lic_invalid": "Invalid license.",
        "lic_hwid_mismatch": "HWID mismatch for this device.",
        "lic_error": "License server error: {e}",
        "lic_burned": "Trial has ended.",
        "cli_need_key": "License mode active — provide --license-user and --license.",
        "save_success": "Credentials saved.",
        "load_success": "Saved credentials found.",
        "load_missing": "Saved credentials not found.",
        "driver_restart": "Browser restarted after an error.",
        "send_retry": "Send failed, retrying…",
    },
    "ru": {
        "title": "Uzdevumi.lv bot",
        "status": "Статус",
        "info": "Информация",
        "login_start": "Вход…",
        "cookies_declined": "Куки отклонены",
        "logged_in": "Вошли",
        "find_subject": "Выбор предмета…",
        "subject": "Предмет: {x}",
        "topic": "Тема: {x}",
        "task": "Задание: {x}",
        "text": "Текст: {x}",
        "points": "Баллы: {x}",
        "img_task_skip": "Задание с картинками или перетаскиванием — херню эту делать не буду.",
        "open_gpt": "Открываю ChatGPT…",
        "sent_gpt": "Отправлено в GPT",
        "gpt_ans": "Ответ GPT: {x}",
        "marked": "Отмеченные варианты: {x}",
        "submitted": "Отправлено",
        "no_inputs": "Нет полей ввода",
        "no_btn": "Нет кнопки отправки",
        "no_valid": "GPT не вернул корректных значений",
        "done": "Готово",
        "debug_keep": "браузеры остаются открыты",
        "cycle": "Цикл #{x}",
        "points_val": "Баллы задания (этикетка): {x}",
        "top_start": "Стартовые Top баллы: {a}{b}",
        "top_target": "→ цель: {t}",
        "top_now": "Текущие Top баллы: {x}",
        "top_reached": "Цель достигнута: {a} ≥ {b}",
        "retry": "Повтор {a}/{b}…",
        "ui_username": "Идентификатор",
        "ui_password": "Пароль",
        "ui_debug": "Держать браузеры открытыми",
        "ui_until": "--until-top (напр., 1600)",
        "ui_gain": "--gain (напр., 25)",
        "ui_start": "Старт",
        "ui_close": "Закрыть",
        "ui_error_need_creds": "Введите идентификатор и пароль.",
        "ui_lang": "Язык",
        "ui_license": "Лицензия",
        "ui_license_user": "Имя пользователя лицензии",
        "ui_license_key": "Ключ лицензии",
        "ui_license_user_ph": "Ваш логин",
        "ui_license_key_ph": "XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX-XXXXXX",
        "ui_check_license": "Проверить лицензию",
        "ui_end_trial": "Завершить пробный период и использовать лицензию",
        "ui_trial_left": "Осталось времени пробного периода: {h}:{m:02d}:{s:02d}",
        "ui_trial_expired": "Пробный период истёк — требуется лицензия.",
        "ui_licensed": "Лицензировано: {u}",
        "ui_popup_title": "Лицензия",
        "ui_popup_msg": "Введите имя пользователя и ключ лицензии:",
        "ui_popup_btn_ok": "Подтвердить",
        "ui_popup_btn_cancel": "Отмена",
        "p1": "Вы — ассистент, решающий задания uzdevumi.lv, выводите только окончательный ответ.",
        "p2": "Дан текст содержимого #taskhtml > div. Проанализируйте и дайте решение.",
        "p3": "Формат ответа:",
        "p4": "- Выбор: только номера или буквы (1/A, 2/B, …), по одной строке.",
        "p5": "- Несколько полей ввода: каждое значение с новой строки в том же порядке.",
        "p6": "- Выпадающие списки: для каждой строки выберите одно (буква A/B/C… либо видимый текст).",
        "p7": "- Без пояснений. Одно короткое сообщение только с итогом.",
        "p8": "Текст задания:",
        "p_radio_hdr": "Варианты (radio/checkbox):",
        "p_drop_hdr": "Варианты (dropdown):",
        "lic_start_trial": "Пробный период запущен (120 мин).",
        "lic_trial_left": "Осталось минут пробного периода: {m}",
        "lic_trial_expired": "Пробный период истёк. Нужна лицензия.",
        "lic_valid": "Лицензия валидна. Пользователь: {u}",
        "lic_revoked": "Лицензия отозвана: {r}",
        "lic_invalid": "Неверная лицензия.",
        "lic_hwid_mismatch": "Несовпадение HWID.",
        "lic_error": "Ошибка сервера лицензий: {e}",
        "lic_burned": "Пробный период завершён.",
        "cli_need_key": "Активен режим лицензии — укажите --license-user и --license.",
        "save_success": "Данные сохранены.",
        "load_success": "Найдены сохранённые данные.",
        "load_missing": "Сохранённых данных не найдено.",
        "driver_restart": "Браузер перезапущен после ошибки.",
        "send_retry": "Отправка не удалась, повторяю…",
    },
}


def T(lang: str, key: str, **kwargs) -> str:
    pack = I18N.get(lang, I18N["lv"])
    s = pack.get(key, key)
    return s.format(**kwargs) if kwargs else s

# ----------------------- Data classes -------------------

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
    points_label: str
    dropdown_texts: List[List[str]]
    dropdown_ids: List[Optional[str]]

Logger = Optional[Callable[[str], None]]

# ----------------------- Credentials persistence --------

def _ensure_config_dir() -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

def load_saved_credentials(logger: Logger = None, lang: str = "lv") -> Dict[str, str]:
    if not CONFIG_PATH.exists():
        log_message(T(lang, "load_missing"), logger)
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        log_message(T(lang, "load_success"), logger)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log_message(f"⚠ {exc}", logger)
        return {}

def save_credentials(data: Dict[str, Optional[str]], logger: Logger = None, lang: str = "lv") -> None:
    payload = {k: v for k, v in data.items() if v}
    if not payload:
        return
    try:
        _ensure_config_dir()
        CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log_message(T(lang, "save_success"), logger)
    except Exception as exc:
        log_message(f"⚠ {exc}", logger)

# ----------------------- Logging & waits -----------------

def log_message(message: str, logger: Logger = None) -> None:
    print(message)
    if logger:
        try: logger(message)
        except Exception: pass

# ...

def w(driver, css, timeout=7, cond="present"):
    try:
        cond_map = {
            "present": EC.presence_of_element_located,
            "visible": EC.visibility_of_element_located,
            "clickable": EC.element_to_be_clickable,
        }
        return WebDriverWait(driver, timeout).until(cond_map[cond]((By.CSS_SELECTOR, css)))
    except TimeoutException:
        return None


def w_all(driver, css, timeout=7, visible_only=False):
    try:
        elements = WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, css)))
        if visible_only:
            elements = [e for e in elements if e.is_displayed()]
        return elements
    except TimeoutException:
        return []


def js_click(driver, element):
    if element is None:
        return
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        element.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
        except Exception:
            pass


def clear_cookies(driver) -> None:
    try:
        driver.delete_all_cookies()
    except Exception:
        pass


def build_fast_driver(incognito=True, new_window=False, block_images=True, retries: int = 3):
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        options = uc.ChromeOptions()
        if incognito:
            options.add_argument("--incognito")
        if new_window:
            options.add_argument("--new-window")
        options.page_load_strategy = "eager"
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-features=PrivacySandboxAdsAPIs,HeavyAdIntervention,Translate")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-client-side-phishing-detection")
        options.add_argument("--remote-allow-origins=*")
        if block_images:
            prefs = {"profile.managed_default_content_settings.images": 2}
            options.add_experimental_option("prefs", prefs)
        try:
            driver = uc.Chrome(options=options)
            try:
                driver.set_page_load_timeout(30)
                driver.set_window_size(1280, 900)
            except Exception:
                pass
            return driver
        except Exception as exc:
            last_exc = exc
            time.sleep(min(2 * attempt, 6))
    if last_exc:
        raise RuntimeError(f"Failed to start Chrome: {last_exc}")
    raise RuntimeError("Failed to start Chrome")


def with_resilience(step_fn: Callable[[], None], recreate_fn: Callable[[], None], lang: str, logger: Logger = None, retries: int = 2):
    attempt = 0
    while True:
        try:
            return step_fn()
        except (NoSuchWindowException, WebDriverException, StaleElementReferenceException) as e:
            attempt += 1
            if attempt <= retries:
                log_message(T(lang, "retry", a=attempt, b=retries), logger)
                recreate_fn()
                continue
            raise


# ----------------------- Points helpers ------------------

def parse_points_label(label: str) -> float:
    if not label:
        return 0.0
    m = re.search(r"(\d+[.,]?\d*)", label)
    if not m:
        return 0.0
    return float(m.group(1).replace(",", "."))


def read_top_points(driver) -> Optional[int]:
    try:
        el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.top-points")))
        txt = el.text.strip()
        m = re.search(r"\d+", txt.replace(" ", ""))
        if m:
            return int(m.group(0))
    except Exception:
        return None
    return None


# ----------------------- Cosmetic: hide media ------------

HIDE_MEDIA_CSS = """
* { image-rendering: auto !important; }
img, .gxs-resource-image, .gxst-resource-image, .gxs-dnd-option,
[style*="background-image"], .answer-box, .ui-draggable, .taskhtmlwrapper .image, .taskhtmlwrapper figure {
  display: none !important;
}
"""


def apply_hide_media_css(driver):
    try:
        driver.execute_script(
            """
            (function(css){
                const id='__hide_media_style__';
                if(document.getElementById(id)) return;
                const s=document.createElement('style'); s.id=id; s.type='text/css'; s.appendChild(document.createTextNode(css));
                document.head.appendChild(s);
            })(arguments[0]);
        """,
            HIDE_MEDIA_CSS,
        )
    except Exception:
        pass


# ----------------------- Registry / HWID -----------------

def is_windows() -> bool:
    return platform.system().lower() == "windows"


def get_hwid() -> str:
    base = ""
    if is_windows():
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | 0x0100,
            )
            base, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
        except Exception:
            base = ""
    if not base:
        base = f"{platform.node()}|{platform.platform()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest().upper()[:32]


def reg_read(name: str) -> Optional[str]:
    if not is_windows():
        return None
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return str(val)
    except Exception:
        return None


def reg_write(name: str, value: str) -> None:
    if not is_windows():
        return
    try:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
    except Exception:
        pass


def reg_delete(name: str) -> None:
    if not is_windows():
        return
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, name)
        winreg.CloseKey(key)
    except Exception:
        pass


# ----------------------- Licensing -----------------------


class LicenseManager:
    def __init__(self, lang: str, logger: Logger = None):
        self.lang = lang
        self.logger = logger

    def _trial_seconds_left(self) -> int:
        if not is_windows():
            return 0
        if reg_read("TrialBurned") == "1":
            return 0
        start_epoch = reg_read("TrialStartEpoch")
        if not start_epoch:
            reg_write("TrialStartEpoch", str(time.time()))
            log_message(T(self.lang, "lic_start_trial"), self.logger)
            return TRIAL_MINUTES * 60
        try:
            used = time.time() - float(start_epoch)
        except Exception:
            used = TRIAL_MINUTES * 60 + 1
        left = int(max(0, TRIAL_MINUTES * 60 - used))
        if left > 0:
            log_message(T(self.lang, "lic_trial_left", m=int(left / 60)), self.logger)
        else:
            log_message(T(self.lang, "lic_trial_expired"), self.logger)
        return left

    def burn_trial(self):
        if not is_windows():
            return
        reg_write("TrialBurned", "1")
        reg_write("TrialStartEpoch", "0")
        log_message(T(self.lang, "lic_burned"), self.logger)

    def _stored(self):
        return (
            reg_read("LicenseUser") or "",
            reg_read("LicenseKey") or "",
            reg_read("LicenseHWID") or "",
        )

    def validate_and_store(self, ks_user: str, ks_key: str) -> Tuple[bool, str]:
        """Validate via Keysys POST /validate (bind HWID on first success). Requires user+key."""
        if not ks_user or not ks_key:
            msg = T(self.lang, "lic_invalid")
            log_message(msg, self.logger)
            return False, msg
        hwid = reg_read("LicenseHWID") or get_hwid()
        try:
            res = requests.post(
                KEYSYS_VALIDATE,
                json={"user": ks_user, "key": ks_key, "hwid": hwid},
                timeout=12,
            )
            js = res.json()
            if js.get("valid"):
                reg_write("LicenseUser", ks_user)
                reg_write("LicenseKey", ks_key)
                reg_write("LicenseHWID", js.get("hwid") or hwid)
                self.burn_trial()
                log_message(T(self.lang, "lic_valid", u=js.get("user", ks_user)), self.logger)
                return True, js.get("user", ks_user)
            if js.get("revoked"):
                msg = T(self.lang, "lic_revoked", r=js.get("reason", ""))
                log_message(msg, self.logger)
                return False, msg
            message = (js.get("message") or "").lower()
            if "hwid mismatch" in message:
                msg = T(self.lang, "lic_hwid_mismatch")
                log_message(msg, self.logger)
                return False, msg
            if "not bound" in message:
                res2 = requests.post(
                    KEYSYS_VALIDATE,
                    json={"user": ks_user, "key": ks_key, "hwid": hwid},
                    timeout=12,
                )
                js2 = res2.json()
                if js2.get("valid"):
                    reg_write("LicenseUser", ks_user)
                    reg_write("LicenseKey", ks_key)
                    reg_write("LicenseHWID", js2.get("hwid") or hwid)
                    self.burn_trial()
                    log_message(T(self.lang, "lic_valid", u=js2.get("user", ks_user)), self.logger)
                    return True, js2.get("user", ks_user)
            msg = T(self.lang, "lic_invalid")
            log_message(msg, self.logger)
            return False, msg
        except Exception as e:
            msg = T(self.lang, "lic_error", e=str(e))
            log_message(msg, self.logger)
            return False, msg

    def status(self) -> Dict[str, Optional[str]]:
        """Returns dict: state in {'licensed','trial','expired'}, 'user', 'left_seconds'."""
        ks_user, ks_key, ks_hwid = self._stored()
        if ks_user and ks_key:
            try:
                q = {"user": ks_user, "key": ks_key}
                q["hwid"] = ks_hwid or get_hwid()
                r = requests.get(KEYSYS_VALIDATE, params=q, timeout=8)
                js = r.json()
                if js.get("valid"):
                    if js.get("hwid"):
                        reg_write("LicenseHWID", js["hwid"])
                    return {"state": "licensed", "user": js.get("user") or ks_user, "left_seconds": None}
                if js.get("revoked"):
                    reg_delete("LicenseUser")
                    reg_delete("LicenseKey")
                    reg_delete("LicenseHWID")
                else:
                    if (js.get("message") or "").lower().find("mismatch") >= 0:
                        pass
                    reg_delete("LicenseUser")
                    reg_delete("LicenseKey")
            except Exception:
                return {"state": "licensed", "user": ks_user or "unknown", "left_seconds": None}

        left = self._trial_seconds_left()
        if left > 0:
            return {"state": "trial", "user": None, "left_seconds": left}
        return {"state": "expired", "user": None, "left_seconds": 0}

    def ensure_for_cli(
        self,
        use_keysys_flag: bool,
        license_user_arg: Optional[str],
        license_key_arg: Optional[str],
    ):
        """CLI gating. '--keysys' burns trial immediately and requires user+key to validate."""
        if use_keysys_flag:
            self.burn_trial()
            if not license_user_arg or not license_key_arg:
                raise RuntimeError(T(self.lang, "cli_need_key"))
            ok, msg = self.validate_and_store(license_user_arg, license_key_arg)
            if not ok:
                raise RuntimeError(msg)
            return

        st = self.status()
        if st["state"] == "licensed":
            return
        if st["state"] == "trial":
            return
        if license_user_arg and license_key_arg:
            ok, msg = self.validate_and_store(license_user_arg, license_key_arg)
            if not ok:
                raise RuntimeError(msg)
            return
        raise RuntimeError(T(self.lang, "lic_trial_expired"))


# ----------------------- Site flow ----------------------

EXCLUDE_SUBJECTS = {
    "Vizuālā māksla (Skola2030), 5. klase",
    "Vizuālā māksla, 5. klase",
    "Mūzika (Skola2030), 5. klase",
    "Starpbrīdis, Svētku testi",
    "Starpbrīdis, Izglītojošie testi",
    "Starpbrīdis, Darba lapas",
    "Starpbrīdis, Ralfs mācās ar Uzdevumi.lv",
    "Uzdevumi.lv konkursi, 2025. gads (Matemātika)",
    "Uzdevumi.lv konkursi, 2024. gads (Matemātika)",
    "Uzdevumi.lv konkursi, 2023. gads (Matemātika)",
    "Uzdevumi.lv konkursi, 2023. gads (Ķīmija)",
}


def decline_cookies(driver, lang, logger: Logger = None):
    try:
        btn = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#CybotCookiebotDialogBodyButtonDecline"))
        )
        js_click(driver, btn)
        log_message(T(lang, "cookies_declined"), logger)
    except TimeoutException:
        pass
    apply_hide_media_css(driver)


def login(driver, user, password, lang, logger: Logger = None):
    log_message(T(lang, "login_start"), logger)
    driver.get("https://www.uzdevumi.lv/Sso/AuthRedirect/eklase?authAction=alor&rememberMe=False&isPopup=True")
    decline_cookies(driver, lang, logger)
    u = w(driver, "#UserName", 10, "visible")
    p = w(driver, "div.InputForm_Row:nth-child(2) > input:nth-child(1)", 10, "visible")
    if not u or not p:
        raise RuntimeError("Login fields not found")
    u.send_keys(user)
    p.send_keys(password)
    js_click(driver, w(driver, "#cmdLogonUser", 8, "clickable"))
    try:
        prof = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".UserProfileSelector_Button")))
        js_click(driver, prof)
    except TimeoutException:
        pass
    decline_cookies(driver, lang, logger)
    log_message(T(lang, "logged_in"), logger)


# ...

def select_task(driver, lang, logger: Logger = None):
    log_message(T(lang, "find_subject"), logger)
    driver.get("https://www.uzdevumi.lv/p")
    apply_hide_media_css(driver)
    decline_cookies(driver, lang, logger)
    subjects_list = w(driver, "ul.list-unstyled.thumbnails", 10)
    if not subjects_list:
        raise RuntimeError("Subjects list missing")
    candidates = subjects_list.find_elements(By.CSS_SELECTOR, "li.thumb.wide a[href]")
    subjects = []
    for anchor in candidates:
        if not anchor.is_displayed():
            continue
        title = anchor.text.replace("\n", " ").strip()
        if not title:
            continue
        tnorm = title.lower()
        if title in EXCLUDE_SUBJECTS or "starpbrīdis" in tnorm or "konkurs" in tnorm:
            continue
        subjects.append((anchor, title))
    if not subjects:
        raise RuntimeError("No suitable subjects")
    anchor, title = random.choice(subjects)
    log_message(T(lang, "subject", x=title), logger)
    js_click(driver, anchor)
    apply_hide_media_css(driver)
    decline_cookies(driver, lang, logger)
    try:
        js_click(driver, driver.find_element(By.CSS_SELECTOR, ".ui-button"))
    except Exception:
        pass
    topics = [e for e in w_all(driver, "ol.list-unstyled a[href]", 10) if e.is_displayed()]
    if not topics:
        raise RuntimeError("No topics")
    chosen_topic = random.choice(topics)
    log_message(T(lang, "topic", x=chosen_topic.text.strip()), logger)
    js_click(driver, chosen_topic)
    apply_hide_media_css(driver)
    decline_cookies(driver, lang, logger)
    container = None
    for selector in (
        "section.block:nth-child(2) > div:nth-child(2)",
        "section.block:nth-child(1) > div:nth-child(2)",
    ):
        container = w(driver, selector, 8, "visible")
        if container:
            break
    if not container:
        raise RuntimeError("No tasks container")
    tasks = [e for e in container.find_elements(By.CSS_SELECTOR, "a[href]") if e.is_displayed()]
    if not tasks:
        raise RuntimeError("No task links")
    selected_task = random.choice(tasks)
    log_message(T(lang, "task", x=selected_task.text.strip()), logger)
    js_click(driver, selected_task)
    apply_hide_media_css(driver)
    decline_cookies(driver, lang, logger)


def fetch_task(driver, lang, logger: Logger = None) -> Optional[TaskData]:
    wrapper = w(driver, "#taskhtml > div", 10, "visible")
    if wrapper is None:
        return None
    text_content = wrapper.text.strip()
    summary = (
        text_content.replace("\n", " ")[:120] + "…"
        if len(text_content) > 120
        else text_content.replace("\n", " ")
    )
    points_label = "0 p."
    pts_el = driver.find_elements(By.CSS_SELECTOR, ".obj-points")
    if pts_el:
        points_label = pts_el[0].text.strip()
    media = wrapper.find_elements(
        By.CSS_SELECTOR,
        "img,[style*='background-image'],.gxs-resource-image,.gxst-resource-image,.gxs-dnd-option,.answer-box,.ui-draggable",
    )
    if media:
        log_message(T(lang, "img_task_skip"), logger)
        return "SKIP"
    options: List[TaskOption] = []
    for idx, item in enumerate(wrapper.find_elements(By.CSS_SELECTOR, "ul.gxs-answer-select > li"), start=1):
        try:
            input_el = item.find_element(By.CSS_SELECTOR, "input")
        except Exception:
            continue
        try:
            label_el = item.find_element(By.CSS_SELECTOR, "label")
            option_text = label_el.text.strip()
        except Exception:
            label_el, option_text = None, item.text.strip()
        input_type = (input_el.get_attribute("type") or "").lower()
        options.append(TaskOption(idx, option_text, input_type, input_el, label_el))
    dropdown_texts: List[List[str]] = []
    dropdown_ids: List[Optional[str]] = []
    selects = wrapper.find_elements(By.CSS_SELECTOR, "select.gxs-answer-dropdown")
    for sel in selects:
        try:
            sid = sel.get_attribute("id") or None
            select_obj = Select(sel)
            texts = []
            for opt in select_obj.options:
                txt = (opt.text or "").strip()
                if txt == "":
                    continue
                texts.append(txt)
            dropdown_texts.append(texts)
            dropdown_ids.append(sid)
        except Exception:
            continue
    log_message(T(lang, "text", x=summary), logger)
    log_message(T(lang, "points", x=points_label), logger)
    return TaskData(
        text=text_content,
        options=options,
        points_label=points_label,
        dropdown_texts=dropdown_texts,
        dropdown_ids=dropdown_ids,
    )


# ----------------------- GPT session --------------------


class ChatGPTSession:
    def __init__(self, lang: str, logger: Logger = None):
        self.lang = lang
        self.logger = logger
        self.msg_count = 0
        self.driver = None
        self._build_driver()

    # --- helpers ---
    def _build_driver(self):
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        finally:
            self.driver = build_fast_driver(incognito=True, new_window=True, block_images=False)
        try:
            self.driver.set_page_load_timeout(30)
        except Exception:
            pass
        self.driver.get("https://chat.openai.com/")
        self._dismiss_small_button()
        self._maybe_click_radix_link()

    def restart(self):
        self.msg_count = 0
        self._build_driver()

    def _dismiss_small_button(self):
        try:
            small_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.text-sm:nth-child(2)"))
            )
            js_click(self.driver, small_btn)
            time.sleep(0.2)
        except TimeoutException:
            pass
        except Exception:
            pass

    def _maybe_click_radix_link(self):
        try:
            el = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#radix-_r_10_ > div > div > a"))
            )
            js_click(self.driver, el)
        except TimeoutException:
            pass
        except Exception:
            pass

    def _ensure_alive(self):
        try:
            handles = self.driver.window_handles
            if not handles:
                raise NoSuchWindowException("No window")
        except Exception:
            log_message(T(self.lang, "driver_restart"), self.logger)
            self.restart()
            try:
                self.driver.delete_all_cookies()
                self.driver.get("https://chat.openai.com/")
                self._dismiss_small_button()
                self._maybe_click_radix_link()
            except Exception:
                pass

    def _clear_cookies_and_reload(self):
        try:
            self.driver.delete_all_cookies()
        except Exception:
            pass
        try:
            self.driver.get("https://chat.openai.com/")
        except Exception:
            self.restart()
            return
        self._dismiss_small_button()
        self._maybe_click_radix_link()

    def refresh(self):
        self._ensure_alive()
        try:
            self.driver.get("https://chat.openai.com/")
            self._dismiss_small_button()
            self._maybe_click_radix_link()
        except Exception:
            log_message(T(self.lang, "driver_restart"), self.logger)
            self.restart()

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    def _ensure_send_triggered(self) -> bool:
        try:
            WebDriverWait(self.driver, 4).until(
                lambda d: (
                    len(d.find_elements(By.CSS_SELECTOR, "button[aria-label='Stop generating']")) > 0
                    or not w(d, "#composer-submit-button", 1, "clickable")
                )
            )
            return True
        except Exception:
            return False

    def _compose_and_send(self, prompt: str) -> str:
        log_message(T(self.lang, "open_gpt"), self.logger)
        self._maybe_click_radix_link()
        pm = w(self.driver, "div#prompt-textarea.ProseMirror[contenteditable='true']", 18, "visible")
        fb = None if pm else w(self.driver, "textarea[name='prompt-textarea']", 3, "present")
        if not pm and not fb:
            self._maybe_click_radix_link()
            pm = w(self.driver, "div#prompt-textarea.ProseMirror[contenteditable='true']", 6, "visible")
            fb = None if pm else w(self.driver, "textarea[name='prompt-textarea']", 3, "present")
            if not pm and not fb:
                raise RuntimeError("ChatGPT composer not found")

        if pm:
            self.driver.execute_script(
                """
                const el = arguments[0], txt = arguments[1];
                el.scrollIntoView({block:'center'}); el.focus();
                if (!el.querySelector('p')) { const p = document.createElement('p'); p.appendChild(document.createElement('br')); el.appendChild(p); }
                const range = document.createRange(); range.selectNodeContents(el);
                const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, txt);
                el.dispatchEvent(new InputEvent('input', {bubbles: true}));
            """,
                pm,
                prompt,
            )
        else:
            self.driver.execute_script(
                """
                const el = arguments[0], txt = arguments[1];
                el.value = txt; el.dispatchEvent(new Event('input', {bubbles: true}));
            """,
                fb,
                prompt,
            )

        send_btn = w(self.driver, "#composer-submit-button", 8, "clickable")
        for attempt in range(2):
            if send_btn:
                js_click(self.driver, send_btn)
            else:
                (pm or fb).send_keys(Keys.ENTER)
            if self._ensure_send_triggered():
                break
            log_message(T(self.lang, "send_retry"), self.logger)
            send_btn = w(self.driver, "#composer-submit-button", 4, "clickable")
        else:
            raise RuntimeError("Failed to trigger ChatGPT send")

        log_message(T(self.lang, "sent_gpt"), self.logger)

        response_text = ""
        stable = ""
        stable_count = 0
        for _ in range(160):
            time.sleep(0.35)
            bubbles = self.driver.find_elements(
                By.CSS_SELECTOR,
                "div[data-message-author-role='assistant'] .markdown.prose, "
                "div.markdown.prose.dark\\:prose-invert.w-full.break-words.dark.markdown-new-styling",
            )
            if not bubbles:
                self._maybe_click_radix_link()
                continue
            response_text = bubbles[-1].text.strip()
            if response_text == stable and response_text:
                stable_count += 1
            else:
                stable = response_text
                stable_count = 0
            if stable_count >= 3:
                break
        log_message(
            T(
                self.lang,
                "gpt_ans",
                x=(response_text[:80] + ("…" if len(response_text) > 80 else "")),
            ),
            self.logger,
        )
        return response_text

    def ask(self, prompt: str) -> str:
        for attempt in range(3):
            try:
                self._ensure_alive()
                self.msg_count += 1
                if self.msg_count % 3 == 0:
                    self._clear_cookies_and_reload()
                else:
                    self.refresh()
                return self._compose_and_send(prompt)
            except (NoSuchWindowException, WebDriverException, StaleElementReferenceException) as exc:
                log_message(T(self.lang, "driver_restart"), self.logger)
                self.restart()
                if attempt == 2:
                    raise exc
            except Exception:
                if attempt == 2:
                    raise
                self.restart()
        raise RuntimeError("Failed to ask ChatGPT")


# ----------------------- Prompt / parser -----------------


def build_prompt(task: TaskData, lang: str) -> str:
    parts = [
        T(lang, "p1"),
        T(lang, "p2"),
        T(lang, "p3"),
        T(lang, "p4"),
        T(lang, "p5"),
        T(lang, "p6"),
        T(lang, "p7"),
        "",
        T(lang, "p8"),
        task.text,
    ]
    if task.options:
        opt_lines = []
        for o in task.options:
            letter = chr(ord("A") + (o.index - 1))
            opt_lines.append(f"{o.index}/{letter}. {o.text}")
        parts.extend(["", T(lang, "p_radio_hdr"), "\n".join(opt_lines)])
    if task.dropdown_texts:
        lines = []
        for i, opts in enumerate(task.dropdown_texts, start=1):
            lettered = [f"{chr(ord('A')+j)}. {txt}" for j, txt in enumerate(opts)]
            lines.append(f"{i}) " + " | ".join(lettered))
        parts.extend(["", T(lang, "p_drop_hdr"), "\n".join(lines)])
    return "\n".join(parts)


# ...

def parse_answer(answer: str, task: TaskData):
    if not answer:
        return {"mode": "empty", "values": []}
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if not lines:
        return {"mode": "empty", "values": []}

    if task.dropdown_texts:
        values: List[int] = []
        for i, options_texts in enumerate(task.dropdown_texts):
            line = lines[i] if i < len(lines) else ""
            chosen_idx = None
            mnum = re.findall(r"\d+", line)
            if mnum:
                k = int(mnum[0])
                if 1 <= k <= len(options_texts):
                    chosen_idx = k
            if chosen_idx is None:
                mlet = re.findall(r"\b([A-Za-z])\b", line)
                if mlet:
                    L = mlet[0].lower()
                    k = ord(L) - ord("a") + 1
                    if 1 <= k <= len(options_texts):
                        chosen_idx = k
            if chosen_idx is None:
                normalized = line.lower()
                for j, txt in enumerate(options_texts, start=1):
                    if normalized == txt.lower():
                        chosen_idx = j
                        break
            if chosen_idx is None:
                normalized = line.lower()
                for j, txt in enumerate(options_texts, start=1):
                    if normalized and normalized in txt.lower():
                        chosen_idx = j
                        break
            values.append(chosen_idx or 1)
        return {"mode": "dropdowns", "values": values}

    if task.options:
        option_map = {o.index: o for o in task.options}
        letter_to_idx = {chr(ord("A") + (o.index - 1)).lower(): o.index for o in task.options}
        selected: List[int] = []
        for line in lines:
            for d in re.findall(r"\d+", line):
                i = int(d)
                if i in option_map and i not in selected:
                    selected.append(i)
            for L in re.findall(r"\b([A-Za-z])\b", line):
                idx = letter_to_idx.get(L.lower())
                if idx and idx not in selected:
                    selected.append(idx)
            if selected:
                continue
            normalized = line.lower()
            for o in task.options:
                if o.text.lower() == normalized and o.index not in selected:
                    selected.append(o.index)
                    break
        return {"mode": "select", "values": selected}

    tokens: List[str] = []
    for line in lines:
        core = re.sub(r"^\s*\d+[\)\.-:]*\s*", "", line)
        parts = re.findall(r"-?\d+(?:[.,]\d+)?|[A-Za-zĀ-ž]+", core)
        tokens.extend(parts)
    if not tokens:
        tokens = re.findall(r"-?\d+(?:[.,]\d+)?", answer)
    return {"mode": "text", "values": tokens}


# ----------------------- Fillers ------------------------

def fill_in_answers(driver, values: List[str], lang, logger: Logger = None):
    inputs = driver.find_elements(
        By.CSS_SELECTOR,
        "input[type='text'],input[type='number'],textarea,input.gxs-answer-number",
    )
    if not inputs:
        log_message(T(lang, "no_inputs"), logger)
        return
    for idx, element in enumerate(inputs):
        if idx >= len(values):
            break
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            driver.execute_script("arguments[0].value='';", element)
            element.send_keys(str(values[idx]))
        except Exception:
            continue
    submit_button = w(driver, "#submitAnswerBtn", 6, "clickable")
    if submit_button is not None:
        js_click(driver, submit_button)
        log_message(T(lang, "submitted"), logger)
    else:
        log_message(T(lang, "no_btn"), logger)


def select_answers(driver, task: TaskData, indexes: List[int], lang, logger: Logger = None):
    if not indexes:
        log_message(T(lang, "no_valid"), logger)
        return
    options = {o.index: o for o in task.options}
    chosen = []
    for idx in indexes:
        opt = options.get(idx)
        if not opt:
            continue
        target = opt.label_element if opt.label_element else opt.input_element
        try:
            js_click(driver, target)
            chosen.append(idx)
        except Exception:
            continue
    if chosen:
        submit_button = w(driver, "#submitAnswerBtn", 6, "clickable")
        if submit_button is not None:
            js_click(driver, submit_button)
            log_message(T(lang, "submitted"), logger)
        else:
            log_message(T(lang, "no_btn"), logger)
    else:
        log_message(T(lang, "no_valid"), logger)


def fill_dropdowns(
    driver,
    dropdown_texts: List[List[str]],
    dropdown_ids: List[Optional[str]],
    values: List[int],
    lang,
    logger: Logger = None,
):
    wrapper = w(driver, "#taskhtml > div", 6, "visible")
    if not wrapper:
        log_message(T(lang, "no_inputs"), logger)
        return
    fresh_selects: List[object] = []
    for sid in dropdown_ids:
        sel_el = None
        if sid:
            try:
                sel_el = driver.find_element(By.ID, sid)
            except Exception:
                sel_el = None
        if sel_el is None:
            try:
                all_sel = wrapper.find_elements(By.CSS_SELECTOR, "select.gxs-answer-dropdown")
                used = set(map(id, fresh_selects))
                sel_el = next((e for e in all_sel if id(e) not in used), None)
            except Exception:
                sel_el = None
        fresh_selects.append(sel_el)
    valid = [e for e in fresh_selects if e is not None]
    if len(valid) != len(dropdown_texts):
        try:
            fresh_selects = wrapper.find_elements(By.CSS_SELECTOR, "select.gxs-answer-dropdown")
        except Exception:
            fresh_selects = []
    for i, sel_el in enumerate(fresh_selects):
        if i >= len(values):
            break
        if sel_el is None:
            continue
        idx = values[i]
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", sel_el)
            s = Select(sel_el)
            opts = dropdown_texts[i]
            if 1 <= idx <= len(opts):
                s.select_by_visible_text(opts[idx - 1])
            else:
                s.select_by_index(max(1, idx))
        except StaleElementReferenceException:
            try:
                sid = dropdown_ids[i]
                sel2 = (
                    driver.find_element(By.ID, sid)
                    if sid
                    else wrapper.find_elements(By.CSS_SELECTOR, "select.gxs-answer-dropdown")[i]
                )
                s2 = Select(sel2)
                opts = dropdown_texts[i]
                if 1 <= idx <= len(opts):
                    s2.select_by_visible_text(opts[idx - 1])
                else:
                    s2.select_by_index(max(1, idx))
            except Exception:
                continue
        except Exception:
            continue
    submit_button = w(driver, "#submitAnswerBtn", 6, "clickable")
    if submit_button is not None:
        js_click(driver, submit_button)
        log_message(T(lang, "submitted"), logger)
    else:
        log_message(T(lang, "no_btn"), logger)


# ----------------------- Orchestrator -------------------

def solve_one_task(main_driver, gpt: ChatGPTSession, lang, logger: Logger = None) -> float:
    def select_and_fetch():
        select_task(main_driver, lang, logger)
        return fetch_task(main_driver, lang, logger)

    task: Optional[TaskData] = None
    for _ in range(12):
        task = select_and_fetch()
        if task == "SKIP":
            log_message("↻ …", logger)
            continue
        if task is None:
            log_message("⚠  fetch failed, retry…", logger)
            continue
        break

    if not isinstance(task, TaskData):
        log_message(T(lang, "no_valid"), logger)
        return 0.0

    prompt = build_prompt(task, lang)
    answer = gpt.ask(prompt)
    parsed = parse_answer(answer, task)

    if parsed["mode"] == "dropdowns" and task.dropdown_texts:
        fill_dropdowns(main_driver, task.dropdown_texts, task.dropdown_ids, parsed["values"], lang, logger)
    elif parsed["mode"] == "select" and task.options:
        select_answers(main_driver, task, parsed["values"], lang, logger)
    elif parsed["mode"] == "text" and parsed["values"]:
        fill_in_answers(main_driver, parsed["values"], lang, logger)
    else:
        log_message(T(lang, "no_valid"), logger)

    pts = parse_points_label(task.points_label)
    log_message(T(lang, "points_val", x=pts), logger)
    return pts


def run_automation(
    user: str,
    password: str,
    lang: str = "lv",
    logger: Logger = None,
    debug: bool = False,
    until_top: Optional[int] = None,
    gain_points: Optional[float] = None,
    keysys_user: Optional[str] = None,
    license_key: Optional[str] = None,
    force_keysys: bool = False,
) -> None:
    lic = LicenseManager(lang=lang, logger=logger)
    lic.ensure_for_cli(
        use_keysys_flag=force_keysys,
        license_user_arg=keysys_user,
        license_key_arg=license_key,
    )

    log_message(f"=== Uzdevumi.lv bots (FAST + dropdowns + loop + i18n) [{lang}] ===", logger)

    driver = build_fast_driver(incognito=True, new_window=False, block_images=True)
    clear_cookies(driver)

    def recreate_main():
        nonlocal driver
        try:
            try:
                clear_cookies(driver)
            except Exception:
                pass
            try:
                driver.quit()
            except Exception:
                pass
        finally:
            driver = build_fast_driver(incognito=True, new_window=False, block_images=True)

    gpt_session: Optional[ChatGPTSession] = None
    try:
        with_resilience(
            lambda: login(driver, user, password, lang, logger),
            recreate_main,
            lang,
            logger,
            retries=2,
        )
        gpt_session = ChatGPTSession(lang=lang, logger=logger)

        start_top = read_top_points(driver) or 0
        if until_top is not None:
            target_abs = until_top
            suffix = T(lang, "top_target", t=target_abs)
        elif gain_points is not None:
            target_abs = start_top + int(gain_points)
            suffix = T(lang, "top_target", t=target_abs)
        else:
            target_abs = None
            suffix = ""
        log_message(T(lang, "top_start", a=start_top, b=suffix), logger)

        round_idx = 0
        while True:
            round_idx += 1
            log_message(T(lang, "cycle", x=round_idx), logger)
            try:
                _ = solve_one_task(driver, gpt_session, lang, logger)
            except (NoSuchWindowException, WebDriverException, StaleElementReferenceException) as exc:
                log_message(T(lang, "driver_restart"), logger)
                recreate_main()
                if gpt_session:
                    gpt_session.restart()
                continue
            except Exception as exc:
                log_message(f"⚠ {exc}", logger)
                recreate_main()
                if gpt_session:
                    gpt_session.restart()
                continue
            time.sleep(0.7)
            try:
                now_top = read_top_points(driver) or start_top
            except Exception:
                recreate_main()
                now_top = start_top
            log_message(T(lang, "top_now", x=now_top), logger)
            if target_abs is not None and now_top >= target_abs:
                log_message(T(lang, "top_reached", a=now_top, b=target_abs), logger)
                break
            if target_abs is None:
                break
            try:
                driver.get("https://www.uzdevumi.lv/p")
                apply_hide_media_css(driver)
            except Exception:
                recreate_main()

        log_message(T(lang, "done"), logger)
        if debug:
            log_message(T(lang, "debug_keep"), logger)
            return
    finally:
        if not debug:
            try:
                driver.quit()
            except Exception:
                pass
            if gpt_session:
                gpt_session.close()


# ----------------------- GUI (CustomTkinter) -----------

def detect_backends() -> Dict[str, object]:
    available: Dict[str, object] = {}
    try:
        import customtkinter as ctk  # type: ignore

        available["customtkinter"] = ctk
    except ImportError:
        pass
    return available


def run_customtkinter_ui(ctk, default_lang: str = "lv", debug_default: bool = False) -> None:
    import tkinter.messagebox as messagebox
    import tkinter as tk

    app = ctk.CTk()
    app.title(I18N[default_lang]["title"])
    app.geometry("700x720")
    lang_var = tk.StringVar(value=default_lang)

    def L(key, **kw):
        return T(lang_var.get(), key, **kw)

    app.grid_columnconfigure(0, weight=1)
    header = ctk.CTkLabel(app, text=L("title"), font=("Arial", 20, "bold"))
    header.grid(row=0, column=0, pady=(12, 4))

    cred = ctk.CTkFrame(app)
    cred.grid(row=1, column=0, padx=12, pady=8, sticky="ew")
    cred.grid_columnconfigure(1, weight=1)
    user_label = ctk.CTkLabel(cred, text=L("ui_username"))
    user_label.grid(row=0, column=0, padx=8, pady=6, sticky="w")
    user_entry = ctk.CTkEntry(cred)
    user_entry.grid(row=0, column=1, padx=8, pady=6, sticky="ew")
    pass_label = ctk.CTkLabel(cred, text=L("ui_password"))
    pass_label.grid(row=1, column=0, padx=8, pady=6, sticky="w")
    pass_entry = ctk.CTkEntry(cred, show="*")
    pass_entry.grid(row=1, column=1, padx=8, pady=6, sticky="ew")

    lic_frame = ctk.CTkFrame(app)
    lic_frame.grid(row=2, column=0, padx=12, pady=8, sticky="ew")
    lic_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(lic_frame, text=L("ui_license")).grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")
    ctk.CTkLabel(lic_frame, text=L("ui_license_user")).grid(row=1, column=0, padx=8, pady=4, sticky="w")
    lic_user_entry = ctk.CTkEntry(lic_frame, placeholder_text=L("ui_license_user_ph"))
    lic_user_entry.grid(row=1, column=1, padx=8, pady=4, sticky="ew")
    ctk.CTkLabel(lic_frame, text=L("ui_license_key")).grid(row=2, column=0, padx=8, pady=4, sticky="w")
    lic_key_entry = ctk.CTkEntry(lic_frame, placeholder_text=L("ui_license_key_ph"))
    lic_key_entry.grid(row=2, column=1, padx=8, pady=4, sticky="ew")

    lic_status = ctk.CTkLabel(lic_frame, text=L("status") + ": —")
    lic_status.grid(row=3, column=0, columnspan=2, padx=8, pady=6, sticky="w")

    btn_row = ctk.CTkFrame(lic_frame)
    btn_row.grid(row=4, column=0, columnspan=2, padx=0, pady=4, sticky="w")
    lic_check_btn = ctk.CTkButton(btn_row, text=L("ui_check_license"))
    lic_check_btn.grid(row=0, column=0, padx=6, pady=4)
    lic_end_btn = ctk.CTkButton(btn_row, text=L("ui_end_trial"))
    lic_end_btn.grid(row=0, column=1, padx=6, pady=4)

    opts = ctk.CTkFrame(app)
    opts.grid(row=3, column=0, padx=12, pady=8, sticky="ew")
    opts.grid_columnconfigure(1, weight=1)
    dbg_var = tk.BooleanVar(value=debug_default)
    dbg_chk = ctk.CTkCheckBox(opts, text=L("ui_debug"), variable=dbg_var)
    dbg_chk.grid(row=0, column=0, padx=8, pady=4, sticky="w")

    until_entry = ctk.CTkEntry(opts, placeholder_text=L("ui_until"))
    until_entry.grid(row=1, column=0, padx=8, pady=4, sticky="ew")
    gain_entry = ctk.CTkEntry(opts, placeholder_text=L("ui_gain"))
    gain_entry.grid(row=1, column=1, padx=8, pady=4, sticky="ew")

    lang_frame = ctk.CTkFrame(app)
    lang_frame.grid(row=4, column=0, padx=12, pady=4, sticky="ew")
    ctk.CTkLabel(lang_frame, text=L("ui_lang")).grid(row=0, column=0, padx=8, pady=6, sticky="w")
    lang_menu = ctk.CTkOptionMenu(lang_frame, values=["lv", "en", "ru"], variable=lang_var)
    lang_menu.grid(row=0, column=1, padx=8, pady=6, sticky="w")

    btns = ctk.CTkFrame(app)
    btns.grid(row=5, column=0, padx=12, pady=8, sticky="ew")
    start_btn = ctk.CTkButton(btns, text=L("ui_start"))
    start_btn.grid(row=0, column=0, padx=8, pady=8)
    ctk.CTkButton(btns, text=L("ui_close"), command=app.destroy).grid(row=0, column=1, padx=8, pady=8)

    log_box = ctk.CTkTextbox(app, height=240)
    log_box.grid(row=6, column=0, padx=12, pady=(8, 12), sticky="nsew")
    app.grid_rowconfigure(6, weight=1)
    log_box.configure(state="disabled")
    log_queue: "queue.Queue[str]" = queue.Queue()

    def append_log(m: str):
        log_queue.put(m)

    def process_queue():
        try:
            while True:
                m = log_queue.get_nowait()
                log_box.configure(state="normal")
                log_box.insert("end", m + "\n")
                log_box.see("end")
                log_box.configure(state="disabled")
        except queue.Empty:
            pass
        app.after(100, process_queue)

    saved = load_saved_credentials(logger=append_log, lang=lang_var.get())
    if saved:
        user_entry.insert(0, saved.get("user", ""))
        pass_entry.insert(0, saved.get("password", ""))
        lic_user_entry.insert(0, saved.get("license_user", ""))
        lic_key_entry.insert(0, saved.get("license_key", ""))
        if saved.get("lang") in {"lv", "en", "ru"}:
            lang_var.set(saved.get("lang"))
        if saved.get("debug") is not None:
            dbg_var.set(bool(saved.get("debug")))
        if saved.get("until"):
            until_entry.insert(0, str(saved.get("until")))
        if saved.get("gain"):
            gain_entry.insert(0, str(saved.get("gain")))

    def append_and_save_credentials():
        save_credentials(
            {
                "user": user_entry.get().strip(),
                "password": pass_entry.get().strip(),
                "license_user": lic_user_entry.get().strip(),
                "license_key": lic_key_entry.get().strip(),
                "lang": lang_var.get(),
                "debug": dbg_var.get(),
                "until": until_entry.get().strip(),
                "gain": gain_entry.get().strip(),
            },
            logger=append_log,
            lang=lang_var.get(),
        )

    def process_queue_safe():
        try:
            process_queue()
        except Exception:
            pass

    lic_mgr = LicenseManager(lang=lang_var.get(), logger=append_log)
    popup_open_flag = {"open": False}

    def update_license_status():
        lic_mgr.lang = lang_var.get()
        st = lic_mgr.status()
        if st["state"] == "licensed":
            lic_status.configure(text=L("ui_licensed", u=st.get("user") or ""))
            start_btn.configure(state="normal")
        elif st["state"] == "trial":
            left = int(st.get("left_seconds") or 0)
            h = left // 3600
            m = (left % 3600) // 60
            s = left % 60
            lic_status.configure(text=L("ui_trial_left", h=h, m=m, s=s))
            start_btn.configure(state="normal")
        else:
            lic_status.configure(text=L("ui_trial_expired"))
            start_btn.configure(state="disabled")
            if not popup_open_flag["open"]:
                popup_open_flag["open"] = True
                open_license_popup()

        app.after(1000, update_license_status)

    def open_license_popup():
        win = ctk.CTkToplevel(app)
        win.title(L("ui_popup_title"))
        win.grab_set()
        win.geometry("420x220")
        win.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(win, text=L("ui_popup_msg")).grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 6), sticky="w"
        )
        ctk.CTkLabel(win, text=L("ui_license_user")).grid(row=1, column=0, padx=12, pady=6, sticky="w")
        e_user = ctk.CTkEntry(win, placeholder_text=L("ui_license_user_ph"))
        e_user.grid(row=1, column=1, padx=12, pady=6, sticky="ew")
        ctk.CTkLabel(win, text=L("ui_license_key")).grid(row=2, column=0, padx=12, pady=6, sticky="w")
        e_key = ctk.CTkEntry(win, placeholder_text=L("ui_license_key_ph"))
        e_key.grid(row=2, column=1, padx=12, pady=6, sticky="ew")

        def on_ok():
            u = e_user.get().strip()
            k = e_key.get().strip()
            ok, msg = lic_mgr.validate_and_store(u, k)
            if ok:
                lic_user_entry.delete(0, tk.END)
                lic_user_entry.insert(0, u)
                lic_key_entry.delete(0, tk.END)
                lic_key_entry.insert(0, k)
                append_and_save_credentials()
                win.destroy()
                popup_open_flag["open"] = False
            else:
                messagebox.showerror(L("ui_popup_title"), msg)

        def on_cancel():
            win.destroy()
            popup_open_flag["open"] = False

        btns_local = ctk.CTkFrame(win)
        btns_local.grid(row=3, column=0, columnspan=2, pady=12)
        ctk.CTkButton(btns_local, text=L("ui_popup_btn_ok"), command=on_ok).grid(row=0, column=0, padx=6)
        ctk.CTkButton(btns_local, text=L("ui_popup_btn_cancel"), command=on_cancel).grid(row=0, column=1, padx=6)

    def on_check_license():
        u = lic_user_entry.get().strip()
        k = lic_key_entry.get().strip()
        ok, msg = lic_mgr.validate_and_store(u, k)
        if ok:
            messagebox.showinfo(L("ui_license"), T(lang_var.get(), "lic_valid", u=u))
            append_and_save_credentials()
        else:
            messagebox.showerror(L("ui_license"), msg)

    def on_end_trial():
        lic_mgr.burn_trial()
        append_log(T(lang_var.get(), "lic_burned"))

    lic_check_btn.configure(command=on_check_license)
    lic_end_btn.configure(command=on_end_trial)

    def finish_run():
        start_btn.configure(state="normal")

    def worker(
        u: str,
        p: str,
        dbg: bool,
        until_val: Optional[int],
        gain_val: Optional[float],
        lang_sel: str,
        ks_user: Optional[str],
        ks_key: Optional[str],
        force_keysys: bool,
    ):
        try:
            run_automation(
                u,
                p,
                lang=lang_sel,
                logger=append_log,
                debug=dbg,
                until_top=until_val,
                gain_points=gain_val,
                keysys_user=ks_user,
                license_key=ks_key,
                force_keysys=force_keysys,
            )
        except Exception as exc:
            append_log(f"❌ {exc}")
            messagebox.showerror(I18N[lang_sel]["title"], str(exc))
        finally:
            app.after(0, finish_run)

    def on_start():
        u = user_entry.get().strip()
        p = pass_entry.get().strip()
        if not u or not p:
            messagebox.showerror(I18N[lang_var.get()]["title"], T(lang_var.get(), "ui_error_need_creds"))
            return
        until_val = None
        gain_val = None
        try:
            if until_entry.get().strip():
                until_val = int(re.sub(r"\D", "", until_entry.get().strip()))
        except Exception:
            until_val = None
        try:
            if gain_entry.get().strip():
                gain_val = float(
                    re.sub(r"[^0-9.,]", "", gain_entry.get().strip()).replace(",", ".")
                )
        except Exception:
            gain_val = None

        st = lic_mgr.status()
        force = st["state"] == "expired"

        ks_user = lic_user_entry.get().strip() or None
        ks_key = lic_key_entry.get().strip() or None

        append_and_save_credentials()
        start_btn.configure(state="disabled")
        threading.Thread(
            target=worker,
            args=(
                u,
                p,
                dbg_var.get(),
                until_val,
                gain_val,
                lang_var.get(),
                ks_user,
                ks_key,
                force,
            ),
            daemon=True,
        ).start()

    def refresh_ui(*_):
        app.title(L("title"))
        header.configure(text=L("title"))
        user_label.configure(text=L("ui_username"))
        pass_label.configure(text=L("ui_password"))
        dbg_chk.configure(text=L("ui_debug"))
        until_entry.configure(placeholder_text=L("ui_until"))
        gain_entry.configure(placeholder_text=L("ui_gain"))
        start_btn.configure(text=L("ui_start"))
        lic_check_btn.configure(text=L("ui_check_license"))
        lic_end_btn.configure(text=L("ui_end_trial"))
        lic_status.configure(text=L("status") + ": —")
        lic_user_entry.configure(placeholder_text=L("ui_license_user_ph"))
        lic_key_entry.configure(placeholder_text=L("ui_license_key_ph"))
        append_and_save_credentials()

    lang_var.trace_add(
        "write",
        lambda *a: (setattr(lic_mgr, "lang", lang_var.get()), refresh_ui()),
    )
    start_btn.configure(command=on_start)

    app.after(100, process_queue_safe)
    app.after(200, update_license_status)
    app.mainloop()


def launch_gui(default_lang: str, debug_default: bool) -> None:
    available = detect_backends()
    if not available or "customtkinter" not in available:
        raise RuntimeError("GUI not available (customtkinter missing). Use CLI with --nogui.")
    run_customtkinter_ui(available["customtkinter"], default_lang=default_lang, debug_default=debug_default)


# ----------------------- CLI ---------------------------

def load_cli_defaults(lang: str, logger: Logger = None) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    saved = load_saved_credentials(logger=logger, lang=lang)
    return saved.get("user"), saved.get("password"), saved


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Uzdevumi.lv bot (FAST + dropdowns + loop + i18n + Keysys licensing)"
    )
    parser.add_argument("--lang", choices=["lv", "en", "ru"], default="lv", help="UI/log/prompt language")
    parser.add_argument("--debug", action="store_true", help="Keep browsers open at the end")
    parser.add_argument("--until-top", type=int, help="Stop when Top points reach this absolute value")
    parser.add_argument("--gain", type=float, help="Stop after gaining this many Top points relative to start")
    parser.add_argument("--nogui", action="store_true", help="Run without GUI (pure CLI)")
    parser.add_argument("--user", help="uzdevumi.lv user ID (CLI)")
    parser.add_argument("--passw", help="uzdevumi.lv password (CLI)")
    parser.add_argument(
        "--keysys",
        action="store_true",
        help="Force Keysys mode (burns trial immediately; requires --license-user and --license)",
    )
    parser.add_argument("--license-user", help="Keysys username")
    parser.add_argument("--license", help="Keysys license key")
    args = parser.parse_args(argv)

    if args.nogui:
        user_cli = args.user
        pass_cli = args.passw
        if not user_cli or not pass_cli:
            saved_user, saved_pass, _ = load_cli_defaults(args.lang)
            user_cli = user_cli or saved_user
            pass_cli = pass_cli or saved_pass
        if not user_cli or not pass_cli:
            print("CLI mode requires --user and --passw or saved credentials")
            sys.exit(2)
        save_credentials(
            {
                "user": user_cli,
                "password": pass_cli,
                "license_user": args.license_user,
                "license_key": args.license,
                "lang": args.lang,
                "debug": args.debug,
                "until": str(args.until_top or ""),
                "gain": str(args.gain or ""),
            },
            lang=args.lang,
        )
        run_automation(
            user_cli,
            pass_cli,
            lang=args.lang,
            logger=None,
            debug=args.debug,
            until_top=args.until_top,
            gain_points=args.gain,
            keysys_user=args.license_user,
            license_key=args.license,
            force_keysys=args.keysys,
        )
    else:
        launch_gui(default_lang=args.lang, debug_default=args.debug)


if __name__ == "__main__":
    main()
