"""
Scheduler for Daily Stock Digests
Runs TWICE per day:
- 9:30 AM ET (market open)
- 3:00 PM ET (before close at 4 PM)

IMPORTANT: This only runs when your computer is on!
Consider deploying to a cloud service (Railway, Render, PythonAnywhere)
for 24/7 operation.
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from main import LongTermStockAgent
import pytz
from datetime import datetime

def morning_digest():
    """Morning digest at market open (9:30 AM ET)"""
    print(f"\n{'='*60}")
    print(f"🌅 Running MORNING digest - {datetime.now().strftime('%I:%M %p ET')}")
    print(f"{'='*60}\n")
    
    try:
        agent = LongTermStockAgent('portfolio.yaml')
        digest = agent.generate_daily_digest(session='morning')
        agent.send_notification(digest, session='morning')
        print("✅ Morning digest complete!")
    except Exception as e:
        print(f"❌ Morning digest failed: {e}")

def afternoon_digest():
    """Afternoon digest before market close (3:00 PM ET)"""
    print(f"\n{'='*60}")
    print(f"🌆 Running AFTERNOON digest - {datetime.now().strftime('%I:%M %p ET')}")
    print(f"{'='*60}\n")
    
    try:
        agent = LongTermStockAgent('portfolio.yaml')
        digest = agent.generate_daily_digest(session='afternoon')
        agent.send_notification(digest, session='afternoon')
        print("✅ Afternoon digest complete!")
    except Exception as e:
        print(f"❌ Afternoon digest failed: {e}")

def test_both_digests():
    """Test function to run both digests immediately"""
    print("\n" + "="*60)
    print("🧪 TESTING MODE - Running both digests now")
    print("="*60 + "\n")
    
    morning_digest()
    print("\n" + "-"*60 + "\n")
    afternoon_digest()
    
    print("\n" + "="*60)
    print("✅ Test complete! Check the output above.")
    print("="*60 + "\n")

def main():
    import sys
    
    # Check if running in test mode
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_both_digests()
        return
    
    scheduler = BlockingScheduler()
    eastern = pytz.timezone('America/Toronto')
    
    # Morning digest: 9:30 AM ET (market opens)
    scheduler.add_job(
        morning_digest,
        'cron',
        day_of_week='mon-fri',  # Only weekdays
        hour=9,
        minute=30,
        timezone=eastern,
        name='morning_digest'
    )
    
    # Afternoon digest: 3:00 PM ET (1 hour before close)
    scheduler.add_job(
        afternoon_digest,
        'cron',
        day_of_week='mon-fri',  # Only weekdays
        hour=15,
        minute=0,
        timezone=eastern,
        name='afternoon_digest'
    )
    
    print("\n" + "="*60)
    print("📅 STOCK DIGEST SCHEDULER STARTED")
    print("="*60)
    print("\n📧 You will receive TWO daily digests:")
    print("   🌅 Morning:   9:30 AM ET (market open)")
    print("   🌆 Afternoon: 3:00 PM ET (before close)")
    print("\n⚠️  IMPORTANT: Your computer must be ON and AWAKE for this to work!")
    print("   Consider deploying to Railway/Render for 24/7 operation.")
    print("\n⏰ Next scheduled runs:")
    
    # Show next job times
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        if next_run:
            print(f"   {job.name}: {next_run.strftime('%A, %B %d at %I:%M %p %Z')}")
    
    print("\n⏰ Scheduler running... Press Ctrl+C to stop\n")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n\n👋 Scheduler stopped. Goodbye!")

if __name__ == "__main__":
    main()