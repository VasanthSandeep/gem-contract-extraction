from playwright_manager import PlaywrightManager
from controller.contracts_controller import ContractsController


def main():
    print("="*70)
    print("🚀 GeM Contracts Automation System")
    print("="*70)
    
    # Initialize browser
    print("\n[INIT] Launching browser...")
    browser = PlaywrightManager(headless=False)  # Set to True for headless
    browser.start()

    try:
        # Create controller
        contracts = ContractsController(browser)
        
        # Navigate to GeM contracts page
        contracts.go_to_gem_contracts()
        
        # Main processing loop - will break when data is found
        contracts.run()
        
        print("\n" + "="*70)
        print("🎉 SUCCESS - Data found and ready for scraping!")
        print("="*70)
            
    except KeyboardInterrupt:
        print("\n⚠️  Process interrupted by user")
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Keep browser open for inspection
        input("\nPress ENTER to close browser...")
        browser.stop()


if __name__ == "__main__":
    main()
