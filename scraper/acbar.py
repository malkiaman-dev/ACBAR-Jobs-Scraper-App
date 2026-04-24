import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urljoin

from deep_translator import GoogleTranslator

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchWindowException, WebDriverException


TARGET_URL = "https://www.acbar.org/site-rfq"

ROOT_DIR = Path(__file__).resolve().parents[1]
JOBS_DIR = ROOT_DIR / "jobs"
DOWNLOAD_ROOT = ROOT_DIR / "downloads_acbar_all"

JOBS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

DEFAULT_CHROMEDRIVER_PATH = ""
DEFAULT_HEADLESS = False
DEFAULT_VISUAL_MODE = True
DEFAULT_SLOW_MOTION = 0.3

WAIT_SECONDS = 25
DOWNLOAD_WAIT_SECONDS = 40

PAGE_LOAD_TIMEOUT_SECONDS = 120
PAGE_LOAD_STRATEGY = "eager"
RETRY_OPEN_ON_TIMEOUT = True

VEHICLE_KEYWORDS = [
    "vehicle", "vehicles", "car", "cars", "rental vehicle", "rental vehicles",
    "ambulance", "ambulances", "pickup", "pick-up", "truck", "trucks",
    "bus", "buses", "van", "vans", "transport", "transportation",
    "fleet", "driver", "drivers", "motorcycle", "motorcycles", "fuel",
    "diesel vehicle", "repair", "maintenance", "spare parts", "auto parts",
    "armored", "armoured",
    "suv", "sedan", "cit", "apc", "mrap", "4x4",
    "ballistic", "armor", "armour", "protected", "nij", "vpam", "stanag",
    "b4", "b5", "b6", "b7", "runflat", "reinforced", "suspension",
    "blast", "mine", "payload", "gvw",
    "toyota", "hilux", "prado", "cruiser", "landcruiser",
    "nissan", "patrol", "ford", "ranger", "chevrolet", "suburban",
    "mercedes", "sprinter", "gclass", "sclass",
    "bmw", "x5", "lexus", "lx", "gx",
]


def write_status(status_path: Path, payload: Dict[str, Any]) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = status_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(status_path)


def read_control(control_path: Path) -> Dict[str, bool]:
    if not control_path.exists():
        return {"pause": False, "stop": False}
    try:
        data = json.loads(control_path.read_text(encoding="utf-8"))
        return {"pause": bool(data.get("pause")), "stop": bool(data.get("stop"))}
    except Exception:
        return {"pause": False, "stop": False}


def enforce_pause_stop(control_path: Path, status_path: Path, base_status: Dict[str, Any]) -> str:
    """
    Returns:
      - "ok" to continue
      - "stop" to exit
    If pause is true, it waits until pause becomes false or stop becomes true.
    """
    while True:
        c = read_control(control_path)
        if c.get("stop"):
            return "stop"
        if not c.get("pause"):
            return "ok"

        # paused
        paused_payload = dict(base_status)
        paused_payload["state"] = "paused"
        paused_payload["message"] = "Paused (waiting for resume)"
        write_status(status_path, paused_payload)
        time.sleep(1.0)


def contains_persian_arabic_script(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", text or ""))


def translate_to_english_if_needed(title: str) -> Tuple[str, bool]:
    if not title or not title.strip():
        return "", False

    if contains_persian_arabic_script(title):
        try:
            en = GoogleTranslator(source="fa", target="en").translate(title)
            return en, True
        except Exception:
            return title, False

    return title, False


def is_vehicle_related(english_title: str) -> bool:
    if not english_title:
        return False
    t = english_title.lower()
    return any(k in t for k in VEHICLE_KEYWORDS)


def make_unique_id(title: str, org: str, close_date: str, download_url: str) -> str:
    raw = f"{title}|{org}|{close_date}|{download_url}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:12]


def ensure_folder_for_id(tender_id: str) -> Path:
    folder = DOWNLOAD_ROOT / tender_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_csv_header(csv_path: Path, fieldnames: List[str]) -> None:
    if csv_path.exists():
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        f.flush()


def load_existing_ids(csv_path: Path) -> set:
    existing = set()
    if not csv_path.exists():
        return existing
    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = (row.get("id") or "").strip()
                if rid:
                    existing.add(rid)
    except Exception:
        pass
    return existing


def append_row_realtime(csv_path: Path, fieldnames: List[str], row: Dict[str, Any]) -> None:
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(row)
        f.flush()


def human_pause(visual_mode: bool, slow_motion: float, sec: Optional[float] = None) -> None:
    if visual_mode:
        time.sleep(slow_motion if sec is None else sec)


def build_driver(chromedriver_path: str, headless: bool) -> webdriver.Chrome:
    chrome_options = webdriver.ChromeOptions()

    if headless:
        chrome_options.add_argument("--headless=new")

    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")

    chrome_options.page_load_strategy = PAGE_LOAD_STRATEGY

    prefs = {
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    service = Service(chromedriver_path) if chromedriver_path.strip() else Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)

    try:
        driver.maximize_window()
    except Exception:
        pass

    return driver


def open_url_with_fallback(driver: webdriver.Chrome, url: str) -> None:
    try:
        driver.get(url)
        return
    except TimeoutException:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return


def set_download_folder(driver: webdriver.Chrome, folder: Path) -> None:
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(folder)})


def wait_for_download_complete(folder: Path, timeout: int) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if list(folder.glob("*.crdownload")):
            time.sleep(0.5)
            continue
        files = [p for p in folder.glob("*") if p.is_file()]
        if files:
            return True
        time.sleep(0.5)
    return False


def get_table_rows(driver: webdriver.Chrome):
    table = WebDriverWait(driver, WAIT_SECONDS).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
    tbody = table.find_element(By.TAG_NAME, "tbody")
    return tbody.find_elements(By.TAG_NAME, "tr")


def parse_row(row) -> Dict[str, Any]:
    tds = row.find_elements(By.TAG_NAME, "td")
    if len(tds) < 5:
        return {}

    title = tds[1].text.strip()
    org = tds[2].text.strip()
    close_date = tds[3].text.strip()

    download_url = ""
    download_el = None
    try:
        a = tds[4].find_element(By.CSS_SELECTOR, "a")
        download_el = a
        download_url = (a.get_attribute("href") or "").strip()
    except Exception:
        pass

    return {"title": title, "organization": org, "close_date": close_date, "download_url": download_url, "download_el": download_el}


def scroll_into_view(driver: webdriver.Chrome, el, visual_mode: bool, slow_motion: float) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    human_pause(visual_mode, slow_motion, 0.6)


def click_next(driver: webdriver.Chrome, visual_mode: bool, slow_motion: float) -> bool:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    human_pause(visual_mode, slow_motion, 0.8)

    candidates = []
    candidates += driver.find_elements(By.XPATH, "//a[contains(., 'Next')]")
    candidates += driver.find_elements(By.XPATH, "//button[contains(., 'Next')]")

    if not candidates:
        return False

    next_btn = candidates[0]
    cls = (next_btn.get_attribute("class") or "").lower()
    aria_disabled = (next_btn.get_attribute("aria-disabled") or "").lower()

    if "disabled" in cls or aria_disabled == "true":
        return False

    try:
        scroll_into_view(driver, next_btn, visual_mode, slow_motion)
        next_btn.click()
        human_pause(visual_mode, slow_motion, 1.2)
        return True
    except Exception:
        return False


def download_via_click(
    driver: webdriver.Chrome,
    download_el,
    tender_folder: Path,
    visual_mode: bool,
    slow_motion: float,
    download_wait_seconds: int,
) -> str:
    set_download_folder(driver, tender_folder)

    try:
        original_handle = driver.current_window_handle
    except Exception:
        original_handle = None

    before_handles = list(driver.window_handles)

    scroll_into_view(driver, download_el, visual_mode, slow_motion)
    human_pause(visual_mode, slow_motion, 0.6)

    try:
        download_el.click()
    except Exception:
        pass

    human_pause(visual_mode, slow_motion, 1.0)

    try:
        after_handles = list(driver.window_handles)
    except Exception:
        after_handles = before_handles

    new_handles = [h for h in after_handles if h not in before_handles]

    if new_handles:
        new_tab = new_handles[-1]

        try:
            driver.switch_to.window(new_tab)
            human_pause(visual_mode, slow_motion, 1.0)
        except (NoSuchWindowException, WebDriverException):
            new_tab = None

        if new_tab is not None:
            try:
                driver.close()
            except (NoSuchWindowException, WebDriverException):
                pass

        try:
            if original_handle and original_handle in driver.window_handles:
                driver.switch_to.window(original_handle)
            else:
                handles_now = driver.window_handles
                if handles_now:
                    driver.switch_to.window(handles_now[0])
            human_pause(visual_mode, slow_motion, 0.8)
        except (NoSuchWindowException, WebDriverException):
            pass

    ok = wait_for_download_complete(tender_folder, download_wait_seconds)
    return "downloaded" if ok else "download_timeout"


def run_job(
    job_id: str,
    pages: Optional[int],
    chromedriver_path: str,
    headless: bool,
    visual_mode: bool,
    slow_motion: float,
    download_enabled: bool,
) -> int:
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    status_path = job_dir / "status.json"
    control_path = job_dir / "control.json"  # NEW

    csv_path = job_dir / "acbar_vehicle_tenders.csv"
    csv_fields = ["id", "Title", "Organization", "Close Date", "Download"]

    ensure_csv_header(csv_path, csv_fields)

    existing_ids = load_existing_ids(csv_path)
    seen_this_run = set()

    new_added = 0
    skipped_existing = 0
    skipped_non_vehicle = 0

    base = {
        "job_id": job_id,
        "state": "starting",
        "page": 0,
        "new_added": 0,
        "skipped_existing": 0,
        "skipped_non_vehicle": 0,
        "last_id": "",
        "message": "Launching browser",
        "csv_path": str(csv_path),
        "download_root": str(DOWNLOAD_ROOT),
    }
    write_status(status_path, base)

    driver = build_driver(chromedriver_path, headless=headless)

    try:
        base.update({"state": "running", "message": "Opening target page"})
        write_status(status_path, base)

        if enforce_pause_stop(control_path, status_path, base) == "stop":
            base.update({"state": "stopped", "message": "Stopped by user"})
            write_status(status_path, base)
            return 0

        open_url_with_fallback(driver, TARGET_URL)
        human_pause(visual_mode, slow_motion, 1.5)

        try:
            WebDriverWait(driver, WAIT_SECONDS).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        except TimeoutException:
            if RETRY_OPEN_ON_TIMEOUT:
                driver.execute_script("window.open('about:blank','_blank');")
                driver.switch_to.window(driver.window_handles[-1])
                open_url_with_fallback(driver, TARGET_URL)
                human_pause(visual_mode, slow_motion, 1.5)
                WebDriverWait(driver, WAIT_SECONDS).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
            else:
                raise

        page_num = 1

        while True:
            if pages is not None and page_num > pages:
                break

            base.update({
                "state": "running",
                "page": page_num,
                "new_added": new_added,
                "skipped_existing": skipped_existing,
                "skipped_non_vehicle": skipped_non_vehicle,
                "last_id": "",
                "message": "Scraping page",
            })
            write_status(status_path, base)

            if enforce_pause_stop(control_path, status_path, base) == "stop":
                base.update({"state": "stopped", "message": "Stopped by user"})
                write_status(status_path, base)
                return 0

            rows = get_table_rows(driver)

            for row in rows:
                if enforce_pause_stop(control_path, status_path, base) == "stop":
                    base.update({"state": "stopped", "message": "Stopped by user"})
                    write_status(status_path, base)
                    return 0

                item = parse_row(row)
                if not item:
                    continue

                title_en, _ = translate_to_english_if_needed(item["title"])
                if not is_vehicle_related(title_en):
                    skipped_non_vehicle += 1
                    continue

                download_url = (item.get("download_url") or "").strip()
                if download_url:
                    download_url = urljoin(TARGET_URL, download_url)

                tender_id = make_unique_id(
                    title=item["title"],
                    org=item["organization"],
                    close_date=item["close_date"],
                    download_url=download_url,
                )

                if tender_id in existing_ids:
                    skipped_existing += 1
                    continue
                if tender_id in seen_this_run:
                    continue

                seen_this_run.add(tender_id)

                append_row_realtime(csv_path, csv_fields, {
                    "id": tender_id,
                    "Title": item["title"],
                    "Organization": item["organization"],
                    "Close Date": item["close_date"],
                    "Download": download_url,
                })
                existing_ids.add(tender_id)
                new_added += 1

                base.update({
                    "state": "running",
                    "page": page_num,
                    "new_added": new_added,
                    "skipped_existing": skipped_existing,
                    "skipped_non_vehicle": skipped_non_vehicle,
                    "last_id": tender_id,
                    "message": "Saved vehicle tender",
                })
                write_status(status_path, base)

                if download_enabled and item.get("download_el") is not None and download_url:
                    base.update({"message": "Downloading attachment"})
                    write_status(status_path, base)

                    tender_folder = ensure_folder_for_id(tender_id)
                    _ = download_via_click(
                        driver,
                        item["download_el"],
                        tender_folder,
                        visual_mode=visual_mode,
                        slow_motion=slow_motion,
                        download_wait_seconds=DOWNLOAD_WAIT_SECONDS,
                    )

                human_pause(visual_mode, slow_motion, 0.2)

            page_num += 1
            if not click_next(driver, visual_mode, slow_motion):
                break

            human_pause(visual_mode, slow_motion, 1.0)

        base.update({
            "state": "done",
            "page": page_num - 1,
            "new_added": new_added,
            "skipped_existing": skipped_existing,
            "skipped_non_vehicle": skipped_non_vehicle,
            "last_id": "",
            "message": "Finished",
        })
        write_status(status_path, base)
        return 0

    except KeyboardInterrupt:
        base.update({"state": "stopped", "message": "Stopped by user"})
        write_status(status_path, base)
        return 0

    except Exception as e:
        base.update({"state": "error", "message": f"Error: {type(e).__name__}: {e}"})
        write_status(status_path, base)
        return 1

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--pages", default="all")
    p.add_argument("--chromedriver", default=DEFAULT_CHROMEDRIVER_PATH)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--no-visual", action="store_true")
    p.add_argument("--slow", type=float, default=DEFAULT_SLOW_MOTION)
    p.add_argument("--download", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()

    if args.pages.lower() == "all":
        pages = None
    else:
        pages = int(args.pages)
        if pages <= 0:
            print("Invalid --pages. Use a positive integer or 'all'.")
            sys.exit(2)

    visual_mode = (not args.no_visual) and (not args.headless)
    slow_motion = float(args.slow)

    code = run_job(
        job_id=args.job_id,
        pages=pages,
        chromedriver_path=args.chromedriver,
        headless=bool(args.headless),
        visual_mode=visual_mode,
        slow_motion=slow_motion,
        download_enabled=bool(args.download),
    )
    sys.exit(code)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user. Progress saved.\n")
        sys.exit(0)
