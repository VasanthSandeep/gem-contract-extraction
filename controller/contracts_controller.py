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

        self.category_csv = base_path / "data" / "Datasets" / "categories.csv"
        self.output_dir = base_path / "data" / "scrapped"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.output_csv = self.output_dir / "contracts_merged.csv"
        self._init_output_csv()

        with open(self.category_csv, newline="", encoding="utf-8") as f:
            self.categories = list(csv.DictReader(f))

    # --------------------------------------------------
    # OUTPUT CSV
    # --------------------------------------------------
    def _init_output_csv(self):
        if not self.output_csv.exists():
            with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "serial_no",
                    "category_name",
                    "bid_no",
                    "product",
                    "brand",
                    "model",
                    "ordered_quantity",
                    "price",
                    "total_value",
                    "buyer_dept_org",
                    "organization_name",
                    "buyer_designation",
                    "state",
                    "buyer_department",
                    "office_zone",
                    "buying_mode",
                    "contract_date",
                    "order_status",
                    "download_link"
                ])

    def _append_row(self, row):
        with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    # --------------------------------------------------
    # RESET TO HOME
    # --------------------------------------------------
    def reset_to_home(self):
        print("[NAV] Resetting to https://gem.gov.in/")
        self.page.goto("https://gem.gov.in/", timeout=60000)
        self.page.wait_for_timeout(3000)

    # --------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------
    def go_to_gem_contracts(self):
        self.page.wait_for_selector("ul#nav", timeout=60000)
        self.page.click('ul#nav a[title="View Contracts "]')
        self.page.wait_for_timeout(1000)
        self.page.click('ul#nav a[href="https://gem.gov.in/view_contracts"]')
        self.page.wait_for_timeout(3000)

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

    # --------------------------------------------------
    # CATEGORY (KEYWORD → EXACT MATCH)
    # --------------------------------------------------
    def process_category(self, category_name):
        self.page.click(".select2-selection")
        self.page.wait_for_selector("input.select2-search__field")

        search = self.page.locator("input.select2-search__field")
        search.clear()
        search.fill(category_name)
        self.page.wait_for_timeout(1500)

        options = self.page.locator(
            "li.select2-results__option:not(.select2-results__message)"
        )

        target = category_name.lower()
        for i in range(options.count()):
            if options.nth(i).inner_text().strip().lower() == target:
                options.nth(i).click()
                self.page.wait_for_timeout(1000)
                return

        raise Exception(f"Category not found: {category_name}")

    # --------------------------------------------------
    # MAIN SEARCH CAPTCHA
    # --------------------------------------------------
    def solve_main_captcha_and_search(self):
        src = self.page.locator("#captchaimg1").get_attribute("src")
        img = Image.open(io.BytesIO(base64.b64decode(src.split(",")[1])))

        text, conf = ensemble_solve(img)
        if not text or conf < 0.55:
            raise Exception("Main captcha failed")

        self.page.fill("#captcha_code1", text)
        self.page.click("#searchlocation1")
        self.page.wait_for_timeout(4000)

    # --------------------------------------------------
    # NO RESULT FOUND CHECK  ✅ NEW
    # --------------------------------------------------
    def has_no_result(self):
        locator = self.page.locator('div[style*="color:red"]')
        if locator.count() > 0:
            text = locator.first.inner_text()
            return "No Result Found" in text
        return False

    # --------------------------------------------------
    # ROW + POPUP PROCESS
    # --------------------------------------------------
    def process_rows(self, category_name):
        # 🔴 IMPORTANT CHECK
        if self.has_no_result():
            print(f"[RESULT] ❌ No Result Found → {category_name}")
            return

        self.page.wait_for_selector("span.ajxtag_order_number", timeout=30000)

        bid_nodes = self.page.locator("span.ajxtag_order_number")
        item_nodes = self.page.locator("span.ajxtag_item_title")
        qty_nodes = self.page.locator("span.ajxtag_quantity")
        value_nodes = self.page.locator("span.ajxtag_totalvalue")
        buyer_nodes = self.page.locator("span.ajxtag_buyer_dept_org")
        mode_nodes = self.page.locator("span.ajxtag_buying_mode")
        date_nodes = self.page.locator("span.ajxtag_contract_date")
        status_nodes = self.page.locator("span.ajxtag_order_status")

        total = bid_nodes.count()
        print(f"[INFO] Total tenders: {total}")

        for i in range(total):
            bid_no = bid_nodes.nth(i).inner_text().strip()

            product = item_nodes.nth(i * 3).inner_text().strip()
            brand = item_nodes.nth(i * 3 + 1).inner_text().strip()
            model = item_nodes.nth(i * 3 + 2).inner_text().strip()

            qty = qty_nodes.nth(i).inner_text().strip()
            total_value = value_nodes.nth(i * 2).inner_text().strip()
            price = value_nodes.nth(i * 2 + 1).inner_text().strip()

            buyer_dept = buyer_nodes.nth(i * 3).inner_text().strip()
            org_name = buyer_nodes.nth(i * 3 + 1).inner_text().strip()
            designation = buyer_nodes.nth(i * 3 + 2).inner_text().strip()

            state = mode_nodes.nth(i * 4).inner_text().strip()
            buyer_department = mode_nodes.nth(i * 4 + 1).inner_text().strip()
            office_zone = mode_nodes.nth(i * 4 + 2).inner_text().strip()
            buying_mode = mode_nodes.nth(i * 4 + 3).inner_text().strip()

            contract_date = date_nodes.nth(i).inner_text().strip()
            order_status = status_nodes.nth(i).inner_text().strip()

            print(f"[ROW] Processing {bid_no}")

            bid_nodes.nth(i).click()
            self.page.wait_for_timeout(2000)

            self.page.wait_for_selector("#captchaimg", timeout=15000)
            src = self.page.locator("#captchaimg").get_attribute("src")
            img = Image.open(io.BytesIO(base64.b64decode(src.split(",")[1])))

            text, conf = ensemble_solve(img)
            if not text or conf < 0.55:
                self.page.click("button[data-dismiss='modal']")
                continue

            self.page.fill("#captcha_code", text)
            self.page.click("#modelsbt")
            self.page.wait_for_timeout(3000)

            self.page.wait_for_selector("a#dwnbtn", timeout=15000)
            download_link = self.page.locator("a#dwnbtn").get_attribute("href")

            self._append_row([
                i + 1,
                category_name,
                bid_no,
                product,
                brand,
                model,
                qty,
                price,
                total_value,
                buyer_dept,
                org_name,
                designation,
                state,
                buyer_department,
                office_zone,
                buying_mode,
                contract_date,
                order_status,
                download_link
            ])

            print(f"[ROW] Saved {bid_no}")
            self.page.click("button[data-dismiss='modal']")
            self.page.wait_for_timeout(2000)

    # --------------------------------------------------
    # MAIN LOOP (ALL CATEGORIES)
    # --------------------------------------------------
    def run(self):
        for idx, row in enumerate(self.categories, start=1):
            category_name = row["category_name"]

            print("\n" + "=" * 70)
            print(f"🚀 CATEGORY {idx}/{len(self.categories)} → {category_name}")
            print("=" * 70)

            self.reset_to_home()
            self.go_to_gem_contracts()
            self.process_category(category_name)
            self.set_date_filter()
            self.solve_main_captcha_and_search()

            print("[RESULT] Results loaded")
            self.process_rows(category_name)
