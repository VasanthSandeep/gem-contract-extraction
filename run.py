from playwright_manager import PlaywrightManager
from controller.contracts_controller import ContractsController


def main():
    browser = PlaywrightManager(headless=False)
    browser.start()

    contracts = ContractsController(browser)
    contracts.go_to_gem_contracts()

    # ✅ Main flow
    contracts.run()

    input("\nPress ENTER to close browser...")
    browser.stop()


if __name__ == "__main__":
    main()
