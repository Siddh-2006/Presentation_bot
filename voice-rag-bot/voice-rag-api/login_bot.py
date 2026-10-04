import os
from playwright.sync_api import sync_playwright

def main():
    profile_dir = os.path.join(os.getcwd(), "bot_chrome_profile")
    os.makedirs(profile_dir, exist_ok=True)
    
    # Check if system Chrome is available, same as bot.py
    chrome_path = os.getenv("PPT_CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    
    print("==========================================================")
    print("Launching visible browser for bot login...")
    print(f"Profile directory: {profile_dir}")
    print("Please log into a Google Account. When you are fully logged in")
    print("and see your Google account dashboard, CLOSE the browser window.")
    print("==========================================================")

    with sync_playwright() as p:
        kwargs = {
            "headless": False,  # We want to see the browser to log in!
            "user_data_dir": profile_dir,
            "args": ["--disable-blink-features=AutomationControlled"]
        }
        if os.path.exists(chrome_path):
            kwargs["executable_path"] = chrome_path
            
        browser = p.chromium.launch_persistent_context(**kwargs)
        page = browser.new_page()
        
        # Go to Google sign-in
        page.goto("https://accounts.google.com/signin/v2/identifier")
        
        print("\nWaiting for you to close the browser...")
        try:
            # Wait indefinitely until the user manually closes the browser
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
            
        browser.close()
        
    print("\n✅ Profile saved! The bot will now use this logged-in account.")

if __name__ == "__main__":
    main()
