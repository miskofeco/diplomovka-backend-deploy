import time
import logging
import schedule
from datetime import datetime

# Import your scraping function and the landing page config from scraping.py
# Example: from scraping import scrape_for_new_articles, LANDING_PAGE_URL
from scraping import scrape_for_new_articles, LANDING_PAGE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def periodic_scrape():
    """
    Wrapper function that calls the scrape_for_new_articles logic 
    and logs how many articles are currently stored.
    """
    updated_articles = scrape_for_new_articles(LANDING_PAGE_URL)
    logging.info(f"Total articles stored so far: {len(updated_articles)}")

def main():
    # Schedule the scraping to run every 30 minutes.
    job = schedule.every(30).minutes.do(periodic_scrape)
    
    # Run an initial scrape immediately
    periodic_scrape()
    
    # We'll track time in minutes since we last logged a countdown
    minutes_passed = 0

    while True:
        schedule.run_pending()
        # Check when the next run is scheduled
        next_run = job.next_run  # A datetime object for the next scheduled run
        now = datetime.now()
        
        if next_run and next_run > now:
            # Calculate how many minutes remain until the next run
            diff_in_seconds = (next_run - now).total_seconds()
            minutes_left = int(diff_in_seconds // 60)

            # Log every 5 minutes
            if minutes_passed % 5 == 0 and minutes_left > 0:
                logging.info(f"Waiting for the next scrape... ~{minutes_left} minute(s) left.")

        else:
            # If there's no next_run or it's in the past (should be rare), log accordingly
            logging.info("No future scrape scheduled or next run is overdue. Waiting...")

        # Sleep 60 seconds before checking again
        time.sleep(60)
        minutes_passed += 1

if __name__ == "__main__":
    main()