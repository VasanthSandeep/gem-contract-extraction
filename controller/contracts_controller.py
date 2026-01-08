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

        self.csv_rows = []
        self.csv_category_set = set()
        self._load_csv()

    # --------------------------------------------------
    # CSV HANDLING
    # --------------------------------------------------
    def _load_csv(self):
        self.csv_rows.clear()
        self.csv_category_set.clear()

        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["category_name"].strip()
                self.csv_rows.append({
                    "si_no": int(row["si_no"]),
                    "category_name": name
                })
                self.csv_category_set.add(name.lower())

    def _append_multiple_categories(self, new_categories):
        """
        Append suggested categories ONLY at END of CSV.
        Do NOT affect current processing order.
        """
        if not new_categories:
            return

        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            for cat in new_categories:
                key = cat.lower()
                if key in self.csv_category_set:
                    continue

                si_no = len(self.csv_rows) + 1
                writer.writerow([si_no, cat])

                self.csv_rows.append({
                    "si_no": si_no,
                    "category_name": cat
                })
                self.csv_category_set.add(key)

                print(f"[CSV] ➕ Appended to end: {cat}")

    # --------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------
    def go_to_gem_contracts(self):
        self.page.wait_for_selector("ul#nav", timeout=60000)
        self.page.click('ul#nav a[title="View Contracts "]')
        self.page.wait_for_timeout(1000)
        self.page.click('ul#nav a[href="https://gem.gov.in/view_contracts"]')
        self.page.wait_for_timeout(2000)
        print("[NAV] Reached GeM Contracts page")

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

    def solve_and_submit_captcha(self, max_attempts=10):
        attempt = 1

        while attempt <= max_attempts:
            print(f"[CAPTCHA] Attempt {attempt}/{max_attempts}")

            img = self._get_captcha_image()
            text, confidence = ensemble_solve(img)

            print(f"[OCR] '{text}' | confidence={confidence:.2f}")

            if not text or confidence < 0.55:
                self._refresh_captcha()
                attempt += 1
                continue

            self.page.fill("#captcha_code1", text)
            self.page.click("#searchlocation1")

            try:
                self.page.wait_for_selector(
                    "div[style*='color:red'], table, #loader",
                    timeout=15000
                )

                if self.page.locator("#loader").count() > 0:
                    self.page.wait_for_selector("#loader", state="hidden", timeout=15000)

                print("[CAPTCHA] ✅ Search completed")
                return True

            except Exception:
                print("[CAPTCHA] ⚠️ Page stuck, retrying...")
                self._refresh_captcha()
                attempt += 1

        print("[CAPTCHA] ❌ Failed after max attempts")
        return False

    # --------------------------------------------------
    # CATEGORY PROCESS (UPDATED LOGIC)
    # --------------------------------------------------
    def process_category(self, category_name):
        """
        1. Type ONLY CSV category
        2. Collect website suggestions
        3. Append suggestions to END of CSV
        4. Select ONLY CSV category
        """
        print(f"[CATEGORY] Using CSV category: {category_name}")

        self.page.click(".select2-selection")
        self.page.wait_for_selector("input.select2-search__field")

        search = self.page.locator("input.select2-search__field")
        search.clear()
        search.fill(category_name)
        self.page.wait_for_timeout(1500)

        suggestions = self.page.locator(
            "li.select2-results__option:not(.select2-results__message)"
        )

        new_suggestions = []
        count = suggestions.count()
        print(f"[SUGGESTIONS] Found {count}")

        for i in range(count):
            text = suggestions.nth(i).inner_text().strip()
            if text and text.lower() not in self.csv_category_set:
                new_suggestions.append(text)
                print(f"[SUGGESTIONS] New → {text}")

        # ✅ APPEND ONLY (DO NOT PROCESS NOW)
        self._append_multiple_categories(new_suggestions)

        # ✅ SELECT ONLY CSV CATEGORY
        search.press("Enter")
        self.page.wait_for_timeout(1000)
        print("[CATEGORY] ✅ CSV category selected")

    # --------------------------------------------------
    # RESULT CHECK
    # --------------------------------------------------
    def has_no_result(self):
        try:
            locator = self.page.locator("div[style*='color:red']")
            if locator.count() > 0:
                text = locator.first.inner_text()
                return "No Result Found" in text
        except:
            pass
        return False

    # --------------------------------------------------
    # MAIN LOOP (QUEUE BEHAVIOR)
    # --------------------------------------------------
    def run(self):
        index = 0

        while index < len(self.csv_rows):
            row = self.csv_rows[index]
            print(f"\n[CSV] si_no={row['si_no']} | category={row['category_name']}")

            self.process_category(row["category_name"])
            self.set_date_filter()

            captcha_ok = self.solve_and_submit_captcha()
            if not captcha_ok:
                print("[RESET] Reloading page & retrying same category")
                self.go_to_gem_contracts()
                continue

            if self.has_no_result():
                print("[RESULT] ❌ No Result Found → next category")
                self.go_to_gem_contracts()
                index += 1
                continue

            print("[RESULT] ✅ Data found → ready for scraping")
            break
