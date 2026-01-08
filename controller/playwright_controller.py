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
        """Load all categories from CSV into memory"""
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
                self.csv_category_set.add(name.lower())  # Store lowercase for comparison
        
        print(f"[CSV] Loaded {len(self.csv_rows)} categories from file")

    def _append_multiple_categories(self, new_categories):
        """Batch append new categories to CSV (Windows safe with retry)"""
        if not new_categories:
            return

        # Filter out categories that already exist (case-insensitive check)
        categories_to_add = []
        for cat in new_categories:
            if cat.strip().lower() not in self.csv_category_set:
                categories_to_add.append(cat.strip())

        if not categories_to_add:
            print("[CSV] All suggested categories already exist in file")
            return

        # Retry logic for file writing (in case file is locked)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)

                    for cat in categories_to_add:
                        si_no = len(self.csv_rows) + 1
                        writer.writerow([si_no, cat])
                        
                        # Add to in-memory list
                        self.csv_rows.append({
                            "si_no": si_no,
                            "category_name": cat
                        })
                        self.csv_category_set.add(cat.lower())
                        print(f"[CSV] ✅ Added: {cat}")
                
                print(f"[CSV] Successfully added {len(categories_to_add)} new categories")
                print(f"[CSV] Total categories now: {len(self.csv_rows)}")
                break  # Success, exit retry loop
                
            except PermissionError as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    print(f"[CSV] ⚠️  File is locked, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"[CSV] ❌ ERROR: Could not write to CSV after {max_retries} attempts")
                    print(f"[CSV] Please close the CSV file in Excel/Notepad and press Enter to continue...")
                    input()
                    # Try one more time after user confirmation
                    try:
                        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            for cat in categories_to_add:
                                si_no = len(self.csv_rows) + 1
                                writer.writerow([si_no, cat])
                                self.csv_rows.append({
                                    "si_no": si_no,
                                    "category_name": cat
                                })
                                self.csv_category_set.add(cat.lower())
                                print(f"[CSV] ✅ Added: {cat}")
                        print(f"[CSV] Successfully added {len(categories_to_add)} new categories")
                        print(f"[CSV] Total categories now: {len(self.csv_rows)}")
                    except Exception as final_error:
                        print(f"[CSV] ❌ Final attempt failed: {final_error}")
                        raise

    # --------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------
    def go_to_gem_contracts(self):
        """Navigate to GeM Contracts page"""
        print("[NAV] Navigating to GeM Contracts page...")
        try:
            self.page.wait_for_selector("ul#nav", timeout=60000)
            self.page.click('ul#nav a[title="View Contracts "]')
            self.page.wait_for_timeout(1000)
            self.page.click('ul#nav a[href="https://gem.gov.in/view_contracts"]')
            self.page.wait_for_timeout(2000)
            print("[NAV] ✅ Successfully reached GeM Contracts page")
        except Exception as e:
            print(f"[NAV] ❌ Error navigating: {e}")
            raise

    # --------------------------------------------------
    # DATE FILTER (TODAY and 2 DAYS BEFORE)
    # --------------------------------------------------
    def set_date_filter(self):
        """Set date filter: FROM = 2 days before today, TO = today"""
        to_date = datetime.today()
        from_date = to_date - timedelta(days=2)

        try:
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

            print(f"[DATE] Set filter → FROM: {from_date:%d-%m-%Y} | TO: {to_date:%d-%m-%Y}")
        except Exception as e:
            print(f"[DATE] ❌ Error setting date: {e}")
            raise

    # --------------------------------------------------
    # CAPTCHA
    # --------------------------------------------------
    def _get_captcha_image(self):
        """Extract CAPTCHA image from page"""
        try:
            src = self.page.locator("#captchaimg1").get_attribute("src")
            img_bytes = base64.b64decode(src.split(",")[1])
            return Image.open(io.BytesIO(img_bytes))
        except Exception as e:
            print(f"[CAPTCHA] ❌ Error getting image: {e}")
            raise

    def _refresh_captcha(self):
        """Click on CAPTCHA image to refresh it"""
        try:
            self.page.click("#captchaimg1")
            self.page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[CAPTCHA] ❌ Error refreshing: {e}")

    def solve_and_submit_captcha(self, max_attempts=10):
        """Solve CAPTCHA using ensemble solver with retry logic"""
        attempt = 1

        while attempt <= max_attempts:
            print(f"[CAPTCHA] Attempt {attempt}/{max_attempts}")
            
            try:
                # Get CAPTCHA image and solve
                img = self._get_captcha_image()
                text, confidence = ensemble_solve(img)

                print(f"[OCR] Result: '{text}' | Confidence: {confidence:.2f}")

                # Check if confidence is acceptable
                if not text or len(text) < 4 or confidence < 0.55:
                    print(f"[CAPTCHA] Low confidence or invalid text, refreshing...")
                    self._refresh_captcha()
                    attempt += 1
                    continue

                # Fill CAPTCHA and submit
                self.page.fill("#captcha_code1", text)
                self.page.click("#searchlocation1")
                
                # Wait for page to process
                self.page.wait_for_timeout(3000)
                
                print(f"[CAPTCHA] ✅ Submitted with text: '{text}'")
                return True
                
            except Exception as e:
                print(f"[CAPTCHA] ❌ Error in attempt {attempt}: {e}")
                attempt += 1
                if attempt <= max_attempts:
                    self._refresh_captcha()

        print(f"[CAPTCHA] ❌ Failed after {max_attempts} attempts")
        return False

    # --------------------------------------------------
    # CATEGORY PROCESS (CORE LOGIC)
    # --------------------------------------------------
    def process_category(self, category_name):
        """
        Main logic:
        1. Type category name from CSV (EXACT name from current row)
        2. Collect all suggested categories from dropdown
        3. Check each suggestion against CSV
        4. Append new suggestions to CSV
        5. Select the FIRST (original CSV) category by pressing Enter
        """
        print(f"\n[CATEGORY] Processing: '{category_name}'")

        try:
            # Step 1: Open dropdown and clear any previous selection
            print("[CATEGORY] Opening category dropdown...")
            self.page.click(".select2-selection")
            self.page.wait_for_selector("input.select2-search__field", timeout=5000)

            search_input = self.page.locator("input.select2-search__field")
            
            # Clear any existing text first
            search_input.clear()
            self.page.wait_for_timeout(500)
            
            # Type the EXACT category name from CSV
            print(f"[CATEGORY] Typing: '{category_name}'")
            search_input.fill(category_name)
            
            # Wait for suggestions to load
            print("[CATEGORY] Waiting for suggestions to load...")
            self.page.wait_for_timeout(2000)

            # Step 2: Collect all suggestions from dropdown
            new_suggestions = []
            suggestions = self.page.locator(
                "li.select2-results__option:not(.select2-results__message)"
            )

            total_suggestions = suggestions.count()
            print(f"[SUGGESTIONS] Found {total_suggestions} suggestions from website")

            if total_suggestions == 0:
                print("[SUGGESTIONS] ⚠️  No suggestions found for this category")
            else:
                # Step 3: Check each suggestion against CSV
                for i in range(total_suggestions):
                    try:
                        text = suggestions.nth(i).inner_text().strip()
                        if text:
                            # Case-insensitive check
                            if text.lower() not in self.csv_category_set:
                                new_suggestions.append(text)
                                print(f"[SUGGESTIONS] New category found: '{text}'")
                            else:
                                print(f"[SUGGESTIONS] Already exists: '{text}'")
                    except Exception as e:
                        print(f"[SUGGESTIONS] Error reading suggestion {i}: {e}")
                        continue

            # Step 4: Append new suggestions to CSV BEFORE selecting
            if new_suggestions:
                print(f"\n[SUGGESTIONS] Saving {len(new_suggestions)} new categories to CSV...")
                self._append_multiple_categories(new_suggestions)
                print(f"[SUGGESTIONS] ✅ All new categories saved\n")
            else:
                print("[SUGGESTIONS] No new categories to save (all already in CSV)")

            # Step 5: Select the FIRST category (the one from CSV) by pressing Enter
            print(f"[CATEGORY] Selecting CSV category: '{category_name}' (pressing Enter)")
            search_input.press("Enter")
            self.page.wait_for_timeout(1000)
            print("[CATEGORY] ✅ Category selected")
            
        except Exception as e:
            print(f"[CATEGORY] ❌ Error processing category: {e}")
            raise

    # --------------------------------------------------
    # MAIN LOOP (RUNS THROUGH ALL CSV CATEGORIES)
    # --------------------------------------------------
    def run(self, start_index=0):
        """
        Main execution loop:
        - Process each category from CSV starting at start_index
        - Handle 'No Result Found' by moving to next category
        - Continue until data is found or CSV ends
        
        Args:
            start_index: Index to start from (default 0, which is si_no=1)
        """
        index = start_index
        total_categories = len(self.csv_rows)

        print("\n" + "="*70)
        print(f"🚀 STARTING PROCESS WITH {total_categories} CATEGORIES")
        if start_index > 0:
            print(f"   Starting from index {start_index} (si_no={self.csv_rows[start_index]['si_no']})")
        print("="*70 + "\n")

        while index < total_categories:
            row = self.csv_rows[index]
            
            print("\n" + "="*70)
            print(f"📋 PROCESSING CATEGORY {index + 1}/{total_categories}")
            print(f"   SI_NO: {row['si_no']}")
            print(f"   CATEGORY: '{row['category_name']}'")
            print(f"   INDEX: {index}")
            print("="*70)

            # Step 1: Process category (type EXACT name from CSV, collect suggestions, save, select)
            try:
                self.process_category(row["category_name"])
            except Exception as e:
                print(f"[ERROR] Failed to process category: {e}")
                print("[ACTION] Reloading page and moving to next category...")
                self.go_to_gem_contracts()
                index += 1
                continue

            # Step 2: Set date filter (FROM = 2 days ago, TO = today)
            try:
                self.set_date_filter()
            except Exception as e:
                print(f"[ERROR] Failed to set date filter: {e}")
                print("[ACTION] Reloading page and moving to next category...")
                self.go_to_gem_contracts()
                index += 1
                continue

            # Step 3: Solve CAPTCHA and submit
            try:
                captcha_solved = self.solve_and_submit_captcha(max_attempts=10)
                
                if not captcha_solved:
                    print("[CAPTCHA] ❌ Failed to solve CAPTCHA after max attempts")
                    print("[ACTION] Reloading page and retrying same category...")
                    self.go_to_gem_contracts()
                    continue  # Retry same category (don't increment index)
                    
            except Exception as e:
                print(f"[ERROR] CAPTCHA process failed: {e}")
                print("[ACTION] Reloading page and retrying same category...")
                self.go_to_gem_contracts()
                continue

            # Step 4: Check for "No Result Found"
            try:
                # Wait a bit for results to load
                self.page.wait_for_timeout(2000)
                
                # Check if "No Result Found" message appears
                no_result_locator = self.page.locator('div[style*="color:red"]')
                
                if no_result_locator.count() > 0:
                    result_text = no_result_locator.first.inner_text()
                    if "No Result Found" in result_text:
                        print("\n[RESULT] ❌ No Result Found for this category")
                        print(f"[ACTION] Moving to next category (index {index + 1})...\n")
                        
                        # Reset page for next category
                        self.go_to_gem_contracts()
                        index += 1
                        continue
                
                # If we reach here, data was found!
                print("\n" + "="*70)
                print("✅ SUCCESS! DATA FOUND FOR THIS CATEGORY")
                print(f"   Category: '{row['category_name']}'")
                print(f"   SI_NO: {row['si_no']}")
                print(f"   Index: {index}")
                print("="*70)
                print("\n🎯 Ready for scraping process...")
                return True, index  # Return success and current index
                
            except Exception as e:
                print(f"[ERROR] Failed to check results: {e}")
                print("[ACTION] Assuming data found, proceeding...")
                return True, index

        # Final status - reached end of CSV
        print("\n" + "="*70)
        print("⚠️  REACHED END OF CSV FILE")
        print(f"   Processed all {total_categories} categories")
        print("   No data found in any category")
        print("="*70 + "\n")
        
        return False, index  # Returns False if no data found

    # --------------------------------------------------
    # UTILITY: Resume from specific si_no
    # --------------------------------------------------
    def run_from_si_no(self, si_no):
        """
        Start processing from a specific si_no
        
        Args:
            si_no: The si_no to start from (e.g., 2 for "Sutures")
        """
        # Find index for this si_no
        index = None
        for i, row in enumerate(self.csv_rows):
            if row["si_no"] == si_no:
                index = i
                break
        
        if index is None:
            print(f"[ERROR] si_no {si_no} not found in CSV")
            return False, -1
        
        print(f"[INFO] Starting from si_no={si_no}, category='{self.csv_rows[index]['category_name']}'")
        return self.run(start_index=index)