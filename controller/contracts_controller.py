# controller/contracts_controller.py

import csv
import base64
import io
import time
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image

from solver.captcha_solver import ensemble_solve


class ContractsController:
    def __init__(self, browser):
        self.browser = browser
        self.page = browser.page

        self.csv_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "Datasets"
            / "categories.csv"
        )

        # Load CSV once
        self.csv_rows = []
        self.csv_category_set = set()
        self._load_csv()

    # --------------------------------------------------
    # CSV HANDLING (WINDOWS SAFE)
    # --------------------------------------------------
    def _load_csv(self):
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["category_name"].strip()
                self.csv_rows.append({
                    "si_no": int(row["si_no"]),
                    "category_name": name
                })
                self.csv_category_set.add(name)

    def _append_multiple_categories(self, new_categories):
        if not new_categories:
            return

        # Retry logic for file writing (in case file is locked)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)

                    for cat in new_categories:
                        if cat not in self.csv_category_set:
                            si_no = len(self.csv_rows) + 1
                            writer.writerow([si_no, cat])
                            self.csv_rows.append({
                                "si_no": si_no,
                                "category_name": cat
                            })
                            self.csv_category_set.add(cat)
                            print(f"[CSV] Added new category: {cat}")
                
                print(f"[CSV] Total categories in queue: {len(self.csv_rows)}")
                break  # Success, exit retry loop
                
            except PermissionError as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    print(f"[CSV] File is locked, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"[CSV] ❌ ERROR: Could not write to CSV after {max_retries} attempts")
                    print(f"[CSV] Please close the CSV file in any editor and press Enter to continue...")
                    input()
                    # Try one more time after user confirmation
                    with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        for cat in new_categories:
                            if cat not in self.csv_category_set:
                                si_no = len(self.csv_rows) + 1
                                writer.writerow([si_no, cat])
                                self.csv_rows.append({
                                    "si_no": si_no,
                                    "category_name": cat
                                })
                                self.csv_category_set.add(cat)
                                print(f"[CSV] Added new category: {cat}")
                    print(f"[CSV] Total categories in queue: {len(self.csv_rows)}")

    # --------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------
    def go_to_gem_contracts(self):
        self.page.wait_for_selector("ul#nav", timeout=60000)
        self.page.click('ul#nav a[title="View Contracts "]')
        self.page.wait_for_timeout(1000)
        self.page.click('ul#nav a[href="https://gem.gov.in/view_contracts"]')
        self.page.wait_for_timeout(2000)
        print("[SUCCESS] Reached GeM Contracts page")

    # --------------------------------------------------
    # DATE FILTER
    # --------------------------------------------------
    def set_date_filter(self):
        to_date = datetime.today()
        from_date = to_date - timedelta(days=2)

        self.page.evaluate(
            """
            (d) => {
                document.querySelector('#from_date_contract_search1').value = d.from;
                document.querySelector('#to_date_contract_search1').value = d.to;
                document.querySelector('#from_date_contract_search1').dispatchEvent(new Event('change'));
                document.querySelector('#to_date_contract_search1').dispatchEvent(new Event('change'));
            }
            """,
            {
                "from": from_date.strftime("%d-%m-%Y"),
                "to": to_date.strftime("%d-%m-%Y")
            }
        )

        print(f"[DATE] {from_date:%d-%m-%Y} → {to_date:%d-%m-%Y}")

    # --------------------------------------------------
    # CAPTCHA
    # --------------------------------------------------
    def _get_captcha_image(self):
        src = self.page.locator("#captchaimg1").get_attribute("src")
        img_bytes = base64.b64decode(src.split(",")[1])
        return Image.open(io.BytesIO(img_bytes))

    def _refresh_captcha(self):
        self.page.click("#captchaimg1")
        self.page.wait_for_timeout(1000)

    def solve_and_submit_captcha(self):
        attempt = 1

        while True:
            print(f"[CAPTCHA] Attempt {attempt}")
            img = self._get_captcha_image()
            text, confidence = ensemble_solve(img)

            print(f"[OCR] '{text}' | confidence={confidence}")

            if not text or confidence < 0.55:
                self._refresh_captcha()
                attempt += 1
                continue

            self.page.fill("#captcha_code1", text)
            self.page.click("#searchlocation1")
            self.page.wait_for_timeout(2500)
            return

    # --------------------------------------------------
    # CATEGORY PROCESS
    # --------------------------------------------------
    def process_category(self, category_name):
        print(f"[CATEGORY] Using CSV category: {category_name}")

        self.page.click(".select2-selection")
        self.page.wait_for_selector("input.select2-search__field")

        search = self.page.locator("input.select2-search__field")
        search.fill(category_name)
        self.page.wait_for_timeout(1500)

        # Collect suggestions
        new_suggestions = set()
        suggestions = self.page.locator(
            "li.select2-results__option:not(.select2-results__message)"
        )

        total_suggestions = suggestions.count()
        print(f"[SUGGESTIONS] Found {total_suggestions} suggestions from website")

        for i in range(total_suggestions):
            text = suggestions.nth(i).inner_text().strip()
            if text and text not in self.csv_category_set:
                new_suggestions.add(text)

        # Append safely ONCE
        if new_suggestions:
            print(f"[SUGGESTIONS] Saving {len(new_suggestions)} new categories to CSV...")
            self._append_multiple_categories(new_suggestions)
        else:
            print("[SUGGESTIONS] No new categories to save (all already in CSV)")

        # Select ONLY CSV category
        search.press("Enter")
        print("[CATEGORY] CSV category selected")

    # --------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------
    def run(self):
        index = 0
        while index < len(self.csv_rows):
            row = self.csv_rows[index]
            print(f"\n[CSV] si_no={row['si_no']} | category={row['category_name']}")

            self.process_category(row["category_name"])
            self.set_date_filter()
            self.solve_and_submit_captcha()

            if self.page.locator("text=No Result Found").count() > 0:
                print("[RESULT] ❌ No Result Found → moving to next si_no")
                # Reset page state for next category
                print("[RESET] Reloading contracts page for next category...")
                self.go_to_gem_contracts()
                index += 1
                continue

            print("[RESULT] ✅ Data found → ready for scraping")
            break
