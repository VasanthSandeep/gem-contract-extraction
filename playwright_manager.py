from playwright.sync_api import sync_playwright


class PlaywrightManager:
    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--start-maximized"]
        )
        self.context = self.browser.new_context(
            viewport=None
        )
        self.page = self.context.new_page()

        # Go to GeM homepage first
        self.page.goto("https://gem.gov.in", timeout=60000)

    def stop(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
