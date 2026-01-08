import csv
import base64
import io
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image

from solver.captcha_solver import ensemble_solve


class ContractsController:
    def __init__(self, browser):
        self.browser = browser
        self.page = browser.page

        base_path = Path(__file__).resolve().parents[1]

        self.csv_path = base_path / "data" / "Datasets" / "categories.csv"
        self.scrap_dir = base_path / "data" / "scrapped"
        self.scrap_dir.mkdir(parents=True, exist_ok=True)

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

        print(f"[CSV] Loaded {len(self.csv_rows)} categories")

    def _append_multiple_categories(self, new_categories):
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

                print(f"[CSV] ➕ Appended (queued later): {cat}")

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
        for _ in range(max_attempts):
            img = self._get_captcha_image()
            text, confidence = ensemble_solve(img)

            if not text or confidence < 0.55:
                self._refresh_captcha()
                continue

            self.page.fill("#captcha_code1", text)
            self.page.click("#searchlocation1")
            self.page.wait_for_timeout(3000)
            return True

        return False

    # --------------------------------------------------
    # CATEGORY PROCESS
    # --------------------------------------------------
    def process_category(self, category_name):
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
        exact_match = None
        csv_lc = category_name.lower()

        for i in range(suggestions.count()):
            text = suggestions.nth(i).inner_text().strip()
            if not text:
                continue

            if text.lower() not in self.csv_category_set:
                new_suggestions.append(text)

            if text.lower() == csv_lc:
                exact_match = suggestions.nth(i)

        self._append_multiple_categories(new_suggestions)

        if exact_match:
            exact_match.click()
            self.page.wait_for_timeout(1000)
        else:
            raise Exception(f"Exact match not found: {category_name}")

    # --------------------------------------------------
    # SCRAPING LOGIC (FINAL – ALL FIELDS)
    # --------------------------------------------------
    def scrape_results(self):
        self.page.wait_for_selector("span.ajxtag_order_number", timeout=15000)

        bid_nodes = self.page.locator("span.ajxtag_order_number")
        item_nodes = self.page.locator("span.ajxtag_item_title")
        qty_nodes = self.page.locator("span.ajxtag_quantity")
        value_nodes = self.page.locator("span.ajxtag_totalvalue")
        buyer_org_nodes = self.page.locator("span.ajxtag_buyer_dept_org")
        mode_nodes = self.page.locator("span.ajxtag_buying_mode")
        date_nodes = self.page.locator("span.ajxtag_contract_date")
        status_nodes = self.page.locator("span.ajxtag_order_status")

        row_count = bid_nodes.count()
        print(f"[SCRAPE] Rows detected: {row_count}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.scrap_dir / f"bids_{timestamp}.csv"

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "serial_no",
                "bid_no",
                "product",
                "brand",
                "model",
                "ordered_quantity",
                "price",
                "total_value",
                "Organization Type",
                "organization_name",
                "buyer_designation",
                "Ministry",
                "Department",
                "office_zone",
                "buying_mode",
                "contract_date",
                "order_status"
            ])

            for i in range(row_count):
                writer.writerow([
                    i + 1,
                    bid_nodes.nth(i).inner_text().strip(),

                    # product / brand / model (3 per row)
                    item_nodes.nth(i * 3).inner_text().strip() if (i * 3) < item_nodes.count() else "N/A",
                    item_nodes.nth(i * 3 + 1).inner_text().strip() if (i * 3 + 1) < item_nodes.count() else "N/A",
                    item_nodes.nth(i * 3 + 2).inner_text().strip() if (i * 3 + 2) < item_nodes.count() else "N/A",

                    # ordered quantity
                    qty_nodes.nth(i).inner_text().strip() if i < qty_nodes.count() else "N/A",

                    # price & total value (2 per row)
                    value_nodes.nth(i * 2 + 1).inner_text().strip() if (i * 2 + 1) < value_nodes.count() else "N/A",
                    value_nodes.nth(i * 2).inner_text().strip() if (i * 2) < value_nodes.count() else "N/A",

                    # ajxtag_buyer_dept_org (3 per row)
                    buyer_org_nodes.nth(i * 3).inner_text().strip() if (i * 3) < buyer_org_nodes.count() else "N/A",
                    buyer_org_nodes.nth(i * 3 + 1).inner_text().strip() if (i * 3 + 1) < buyer_org_nodes.count() else "N/A",
                    buyer_org_nodes.nth(i * 3 + 2).inner_text().strip() if (i * 3 + 2) < buyer_org_nodes.count() else "N/A",

                    # ajxtag_buying_mode (4 per row)
                    mode_nodes.nth(i * 4).inner_text().strip() if (i * 4) < mode_nodes.count() else "N/A",
                    mode_nodes.nth(i * 4 + 1).inner_text().strip() if (i * 4 + 1) < mode_nodes.count() else "N/A",
                    mode_nodes.nth(i * 4 + 2).inner_text().strip() if (i * 4 + 2) < mode_nodes.count() else "N/A",
                    mode_nodes.nth(i * 4 + 3).inner_text().strip() if (i * 4 + 3) < mode_nodes.count() else "N/A",

                    # contract date
                    date_nodes.nth(i).inner_text().strip() if i < date_nodes.count() else "N/A",

                    # order status
                    status_nodes.nth(i).inner_text().strip() if i < status_nodes.count() else "N/A"
                ])

        print(f"[SCRAPE] ✅ Saved to {output_file}")

    # --------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------
    def run(self):
        index = 0

        while index < len(self.csv_rows):
            self.process_category(self.csv_rows[index]["category_name"])
            self.set_date_filter()

            if not self.solve_and_submit_captcha():
                self.go_to_gem_contracts()
                continue

            if self.page.locator("div[style*='color:red']").count() > 0:
                self.go_to_gem_contracts()
                index += 1
                continue

            print("[RESULT] ✅ Data found → SCRAPING")
            self.scrape_results()
            break
