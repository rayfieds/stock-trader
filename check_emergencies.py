"""
Emergency Alert Checker
Runs every 30 minutes during market hours to catch urgent situations

This is separate from the regular digests and only alerts you when:
- Quality stocks crash >5% (BUY NOW opportunities)
- Your holdings drop >15% from highs (DANGER)
- Major portfolio spikes >10% (TAKE PROFITS)
"""

from main import LongTermStockAgent
from apscheduler.schedulers.blocking import BlockingScheduler
import pytz
from datetime import datetime

def check_for_emergencies():
    """Check for urgent situations"""
    now = datetime.now()
    print(f"\n⏰ Emergency check at {now.strftime('%I:%M %p ET')}")
    
    try:
        agent = LongTermStockAgent('portfolio.yaml')
        
        # Check if alerts are enabled
        if not agent.alerts.get('enabled', False):
            print("   Emergency alerts disabled in portfolio.yaml")
            return
        
        # Run emergency check
        has_emergency = agent.check_and_alert_emergencies()
        
        if has_emergency:
            print("   🚨 URGENT ALERT SENT!")
        else:
            print("   ✅ No emergencies detected")
            
    except Exception as e:
        print(f"   ❌ Emergency check failed: {e}")

def main():
    import sys
    
    # Test mode - check immediately
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        print("\n🧪 TESTING EMERGENCY ALERTS\n")
        check_for_emergencies()
        print("\nDone! Check if you got an alert.\n")
        return
    
    # Production mode - run on schedule
    scheduler = BlockingScheduler()
    eastern = pytz.timezone('America/Toronto')
    
    # Check every 30 minutes during market hours (9:30 AM - 4:00 PM ET)
    # Run at: 10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 1:00, 1:30, 2:00, 2:30, 3:00, 3:30
    for hour in range(10, 16):  # 10 AM to 3 PM
        for minute in [0, 30]:
            if hour == 15 and minute == 30:  # Don't run at 3:30 (too close to close)
                continue
            scheduler.add_job(
                check_for_emergencies,
                'cron',
                day_of_week='mon-fri',
                hour=hour,
                minute=minute,
                timezone=eastern
            )
    
    print("\n" + "="*60)
    print("🚨 EMERGENCY ALERT SYSTEM STARTED")
    print("="*60)
    print("\nWill check for urgent situations every 30 minutes:")
    print("   10:00 AM, 10:30 AM, 11:00 AM, 11:30 AM,")
    print("   12:00 PM, 12:30 PM, 1:00 PM, 1:30 PM,")
    print("   2:00 PM, 2:30 PM, 3:00 PM")
    print("\nYou'll get email alerts for:")
    print("   🔴 Quality stocks crashing (BUY opportunities)")
    print("   🔴 Your holdings in danger (SELL warnings)")
    print("   🟡 Profit-taking opportunities")
    print("\n⚠️  Computer must be ON during market hours!")
    print("\n⏰ Press Ctrl+C to stop\n")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n\n👋 Emergency alerts stopped. Goodbye!")

if __name__ == "__main__":
    main()