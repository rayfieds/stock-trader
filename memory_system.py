"""
Memory System for Stock Agent
Tracks recommendations, portfolio changes, and AI performance
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


class AgentMemory:
    """Persistent memory for the stock agent"""
    
    def __init__(self, memory_dir='agent_memory'):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(exist_ok=True)
        
        # Memory files
        self.recommendations_file = self.memory_dir / 'recommendations.json'
        self.portfolio_history_file = self.memory_dir / 'portfolio_history.json'
        self.market_context_file = self.memory_dir / 'market_context.json'
        
        # Load existing memory
        self.recommendations = self._load_json(self.recommendations_file)
        self.portfolio_history = self._load_json(self.portfolio_history_file)
        self.market_context = self._load_json(self.market_context_file)
    
    def _load_json(self, filepath):
        """Load JSON file or return empty dict"""
        try:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def _save_json(self, filepath, data):
        """Save data to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_recommendation(self, ticker, action, price, reason, session='morning'):
        """Store today's recommendation"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today not in self.recommendations:
            self.recommendations[today] = {
                'date': today,
                'session': session,
                'stocks': {}
            }
        
        self.recommendations[today]['stocks'][ticker] = {
            'action': action,
            'price': price,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
        
        self._save_json(self.recommendations_file, self.recommendations)
    
    def save_portfolio_snapshot(self, portfolio, cash, total_value):
        """Save daily portfolio state"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        self.portfolio_history[today] = {
            'date': today,
            'portfolio': portfolio.copy(),
            'cash': cash,
            'total_value': total_value,
            'timestamp': datetime.now().isoformat()
        }
        
        self._save_json(self.portfolio_history_file, self.portfolio_history)
    
    def save_market_context(self, tsx_level, oil_price, usd_cad, key_events=None):
        """Save daily market state"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        self.market_context[today] = {
            'date': today,
            'tsx': tsx_level,
            'oil': oil_price,
            'usd_cad': usd_cad,
            'events': key_events or [],
            'timestamp': datetime.now().isoformat()
        }
        
        self._save_json(self.market_context_file, self.market_context)
    
    def get_recent_recommendations(self, ticker=None, days=7):
        """Get recommendations from last N days"""
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        
        for date_str, data in sorted(self.recommendations.items(), reverse=True):
            date = datetime.strptime(date_str, '%Y-%m-%d')
            if date < cutoff:
                break
            
            if ticker:
                if ticker in data.get('stocks', {}):
                    stock_data = data['stocks'][ticker]
                    recent.append({
                        'date': date_str,
                        'ticker': ticker,
                        **stock_data
                    })
            else:
                for stock_ticker, stock_data in data.get('stocks', {}).items():
                    recent.append({
                        'date': date_str,
                        'ticker': stock_ticker,
                        **stock_data
                    })
        
        return recent
    
    def count_recommendations(self, ticker, days=7):
        """How many times was this stock recommended recently?"""
        recent = self.get_recent_recommendations(ticker, days)
        return len(recent)
    
    def was_recommended_recently(self, ticker, days=3):
        """Was this stock recommended in last N days?"""
        return self.count_recommendations(ticker, days) > 0
    
    def get_portfolio_changes(self, days=7):
        """Detect portfolio changes (what user actually bought/sold)"""
        dates = sorted(self.portfolio_history.keys(), reverse=True)[:days+1]
        
        if len(dates) < 2:
            return []
        
        changes = []
        
        # Compare today vs N days ago
        current = self.portfolio_history[dates[0]]['portfolio']
        past = self.portfolio_history[dates[-1]]['portfolio']
        
        # Find new positions
        for ticker, shares in current.items():
            if ticker not in past:
                changes.append({
                    'action': 'NEW POSITION',
                    'ticker': ticker,
                    'shares': shares
                })
            elif shares > past[ticker]:
                changes.append({
                    'action': 'ADDED TO',
                    'ticker': ticker,
                    'added_shares': shares - past[ticker],
                    'total_shares': shares
                })
        
        # Find sold positions
        for ticker, shares in past.items():
            if ticker not in current:
                changes.append({
                    'action': 'SOLD',
                    'ticker': ticker,
                    'shares': shares
                })
            elif shares > current.get(ticker, 0):
                changes.append({
                    'action': 'REDUCED',
                    'ticker': ticker,
                    'reduced_shares': shares - current[ticker],
                    'remaining_shares': current[ticker]
                })
        
        return changes
    
    def calculate_recommendation_outcomes(self, current_prices):
        """Track how past recommendations performed"""
        outcomes = []
        
        for date_str, data in self.recommendations.items():
            for ticker, rec in data.get('stocks', {}).items():
                recommended_price = rec['price']
                current_price = current_prices.get(ticker)
                
                if current_price:
                    gain_pct = ((current_price - recommended_price) / recommended_price * 100)
                    
                    days_ago = (datetime.now() - datetime.strptime(date_str, '%Y-%m-%d')).days
                    
                    outcomes.append({
                        'date': date_str,
                        'ticker': ticker,
                        'action': rec['action'],
                        'recommended_price': recommended_price,
                        'current_price': current_price,
                        'gain_pct': gain_pct,
                        'days_ago': days_ago,
                        'status': 'winning' if gain_pct > 0 else 'losing'
                    })
        
        return outcomes
    
    def get_ignored_recommendations(self, current_portfolio, days=7):
        """Find stocks AI recommended but user didn't buy"""
        ignored = []
        recent = self.get_recent_recommendations(days=days)
        
        for rec in recent:
            if rec['action'] == 'BUY' and rec['ticker'] not in current_portfolio:
                ignored.append(rec)
        
        return ignored
    
    def generate_memory_summary(self, current_portfolio, current_prices):
        """Generate comprehensive memory summary for AI"""
        
        # Recent activity
        recent_recs = self.get_recent_recommendations(days=7)
        # portfolio_changes = self.get_portfolio_changes(days=7)
        outcomes = self.calculate_recommendation_outcomes(current_prices)
        ignored = self.get_ignored_recommendations(current_portfolio, days=7)
        
        # Calculate statistics
        if outcomes:
            winning = [o for o in outcomes if o['gain_pct'] > 0]
            win_rate = len(winning) / len(outcomes) * 100 if outcomes else 0
            avg_gain = sum(o['gain_pct'] for o in outcomes) / len(outcomes)
        else:
            win_rate = 0
            avg_gain = 0
        
        summary = {
            'recent_recommendations_count': len(recent_recs),
            # 'portfolio_changes': portfolio_changes,
            'performance': {
                'total_calls': len(outcomes),
                'win_rate': win_rate,
                'avg_gain': avg_gain,
                'winning_trades': [o for o in outcomes if o['gain_pct'] > 5],
                'losing_trades': [o for o in outcomes if o['gain_pct'] < -5]
            },
            'ignored_stocks': ignored[:5],  # Top 5 most recent
            'repeated_recommendations': self._find_repeated_stocks(recent_recs)
        }
        
        return summary
    
    def _find_repeated_stocks(self, recommendations):
        """Find stocks recommended multiple times"""
        ticker_counts = {}
        
        for rec in recommendations:
            ticker = rec['ticker']
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        
        # Return tickers recommended 2+ times
        return {t: c for t, c in ticker_counts.items() if c >= 2}
    
    def format_memory_for_prompt(self, current_portfolio, current_prices):
        """Format memory summary for AI prompt"""
        
        summary = self.generate_memory_summary(current_portfolio, current_prices)
        
        text = f"""
📚 AGENT MEMORY & CONTEXT:

YOUR RECOMMENDATION PERFORMANCE:
  Total Recommendations: {summary['performance']['total_calls']}
  Win Rate: {summary['performance']['win_rate']:.1f}%
  Average Gain: {summary['performance']['avg_gain']:+.2f}%
  
Best Calls (Gains >5%):
{self._format_outcomes(summary['performance']['winning_trades'][:3])}

Worst Calls (Losses >5%):
{self._format_outcomes(summary['performance']['losing_trades'][:3])}

REPEATED RECOMMENDATIONS (You keep suggesting these):
{self._format_repeated(summary['repeated_recommendations'])}

IGNORED RECOMMENDATIONS (User didn't buy):
{self._format_ignored(summary['ignored_stocks'])}

🤖 INSTRUCTIONS FOR AI:
1. DON'T recommend stocks from "Repeated Recommendations" UNLESS:
   - Major news/event changed the situation
   - Price dropped significantly (>5%) creating new entry point
   - You can explain why NOW is different than before

2. REFERENCE your past performance:
   - "Last week I recommended X and it's up Y% - here's another similar opportunity"
   - "I was wrong about X (down Y%), here's what I learned"

3. LEARN from ignored stocks:
   - If user keeps ignoring tech stocks, maybe they prefer value/dividend
   - If user bought all energy recs, focus more on energy

4. BE FRESH - provide NEW insights, not same analysis
5. If repeating a recommendation, EXPLAIN what changed

6. ACKNOWLEDGE portfolio changes:
   - "I see you bought X - good choice!" or "Why didn't you buy Y?"
"""
        
        return text
    
    def _format_portfolio_changes(self, changes):
        """Format portfolio changes for display"""
        if not changes:
            return "  No changes detected (or first run)"
        
        lines = []
        for change in changes:
            if change['action'] == 'NEW POSITION':
                lines.append(f"  ✅ NEW: {change['ticker']} - {change['shares']} shares")
            elif change['action'] == 'ADDED TO':
                lines.append(f"  📈 ADDED: {change['ticker']} - {change['added_shares']} more shares (total: {change['total_shares']})")
            elif change['action'] == 'SOLD':
                lines.append(f"  ❌ SOLD: {change['ticker']} - {change['shares']} shares")
            elif change['action'] == 'REDUCED':
                lines.append(f"  📉 REDUCED: {change['ticker']} - {change['reduced_shares']} shares (remaining: {change['remaining_shares']})")
        
        return '\n'.join(lines) if lines else "  No changes"
    
    def _format_outcomes(self, outcomes):
        """Format recommendation outcomes"""
        if not outcomes:
            return "  None yet"
        
        lines = []
        for o in outcomes[:3]:  # Top 3
            lines.append(
                f"  {o['ticker']}: Recommended @ ${o['recommended_price']:.2f} "
                f"({o['days_ago']} days ago) → Now ${o['current_price']:.2f} "
                f"({o['gain_pct']:+.1f}%)"
            )
        
        return '\n'.join(lines) if lines else "  None yet"
    
    def _format_repeated(self, repeated):
        """Format repeated recommendations"""
        if not repeated:
            return "  None - all fresh recommendations!"
        
        lines = []
        for ticker, count in sorted(repeated.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {ticker}: Recommended {count} times in last 7 days ⚠️")
        
        return '\n'.join(lines)
    
    def _format_ignored(self, ignored):
        """Format ignored recommendations"""
        if not ignored:
            return "  User acted on all recommendations!"
        
        lines = []
        for rec in ignored[:3]:  # Top 3
            lines.append(
                f"  {rec['ticker']}: {rec['action']} @ ${rec['price']:.2f} "
                f"on {rec['date']} - User passed"
            )
        
        return '\n'.join(lines)
    
    def should_recommend_again(self, ticker, days_since_last=3, price_change_threshold=5):
        """Decide if it's okay to recommend this stock again
        
        Returns: (should_recommend, reason)
        """
        recent = self.get_recent_recommendations(ticker, days=days_since_last)
        
        if not recent:
            return True, "First time recommending"
        
        last_rec = recent[0]
        last_price = last_rec['price']
        
        # If price changed significantly, can recommend again
        # (This would be checked by caller with current price)
        
        return False, f"Already recommended {len(recent)} times in last {days_since_last} days"