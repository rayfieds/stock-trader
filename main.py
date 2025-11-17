import os
import yaml
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from dotenv import load_dotenv
import regex as re
import markdown
from portfolio_loader import load_portfolio_from_secret

load_dotenv()

class LongTermStockAgent:
    def __init__(self, config_path='portfolio.yaml'):
        """Initialize agent for long-term growth investing"""
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        
        config = load_portfolio_from_secret()
        self.portfolio = config['portfolio']
        self.cash = config['cash']
        self.tsx_top_stocks = self._get_tsx_top_stocks()
        
        # News API key (optional - for enhanced news)
        self.news_api_key = os.getenv("NEWS_API_KEY")  # Get free at newsapi.org
        self.alphavantage_key = os.getenv("ALPHAVANTAGE_API_KEY")  # alpha vantage news
        
    def load_config(self, config_path):
        """Load portfolio and preferences from YAML"""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        self.portfolio = config['portfolio']
        self.cash = config['cash']
        self.watchlist = config.get('watchlist', [])
        self.preferences = config.get('preferences', {})
        self.notification = config.get('notification', {})
        self.alerts = config.get('alerts', {})
        
        print(f"✓ Portfolio loaded: {len(self.portfolio)} positions, ${self.cash:,.2f} CAD cash")
        print(f"✓ Personal watchlist: {len(self.watchlist)} stocks")
        
    def get_news_sentiment(self, ticker, days=3):
        """Get news headlines and sentiment for a stock
            
        Uses multiple sources: Yahoo Finance, Alpha Vantage, NewsAPI
        """
        try:
            stock = yf.Ticker(ticker)
            company_name = stock.info.get('longName', ticker)
            news_items = []
            
            # Source 1: Yahoo Finance (always try this first)
            try:
                yf_news = stock.news if hasattr(stock, 'news') else []
                news_items.extend(yf_news[:5])
            except:
                pass
            
            # Source 2: Alpha Vantage (if API key available)
            if self.alphavantage_key and len(news_items) < 3:
                av_news = self._get_alphavantage_news(ticker, company_name)
                news_items.extend(av_news)
            
            # Source 3: NewsAPI (if API key available)
            if self.news_api_key and len(news_items) < 5:
                newsapi_articles = self._get_newsapi_articles(ticker, company_name, days)
                news_items.extend(newsapi_articles)
            
            # If still no news, return None (don't make up fake news!)
            if not news_items:
                return None
            
            # Format news for AI analysis
            headlines = []
            for item in news_items[:10]:  # Top 10 articles
                title = item.get('title', '')
                pub_date = item.get('providerPublishTime', 0)
                if pub_date:
                    date_str = datetime.fromtimestamp(pub_date).strftime('%b %d')
                else:
                    date_str = "Recent"
                headlines.append(f"[{date_str}] {title}")
            
            # Use AI to analyze sentiment
            sentiment_prompt = f"""Analyze the sentiment of these news headlines for {ticker} ({company_name}):

{chr(10).join(headlines)}

Provide:
1. Overall Sentiment: Positive/Negative/Neutral (and strength 0-10)
2. Key Themes: What's driving the news?
3. Investment Impact: Should this make me more/less likely to buy?

Be concise - 2-3 sentences max."""

            response = self.model.generate_content(sentiment_prompt)
            
            return {
                'ticker': ticker,
                'company': company_name,
                'headline_count': len(headlines),
                'headlines': headlines[:5],  # Top 5 for display
                'analysis': response.text
            }
            
        except Exception as e:
            return None
    
    def _get_alphavantage_news(self, ticker, company_name):
        """Get news from Alpha Vantage News API"""
        try:
            # Remove .TO suffix for API call
            symbol = ticker.replace('.TO', '')
            
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': symbol,
                'apikey': self.alphavantage_key,
                'limit': 10
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'feed' not in data:
                return []
            
            articles = []
            for item in data['feed'][:5]:
                # Convert Alpha Vantage format to our format
                articles.append({
                    'title': item.get('title', ''),
                    'providerPublishTime': self._parse_av_time(item.get('time_published', ''))
                })
            
            return articles
            
        except Exception as e:
            return []
    
    def _parse_av_time(self, time_str):
        """Parse Alpha Vantage time format: 20241103T120000"""
        try:
            dt = datetime.strptime(time_str[:8], '%Y%m%d')
            return int(dt.timestamp())
        except:
            return int(datetime.now().timestamp())
        
    def _get_newsapi_articles(self, ticker, company_name, days=3):
        """Get news from NewsAPI (optional, requires API key)"""
        try:
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            url = f"https://newsapi.org/v2/everything"
            params = {
                'q': f'"{company_name}" OR {ticker}',
                'from': from_date,
                'language': 'en',
                'sortBy': 'relevancy',
                'apiKey': self.news_api_key
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                articles = response.json().get('articles', [])
                return [
                    {
                        'title': a['title'],
                        'providerPublishTime': int(datetime.strptime(a['publishedAt'], '%Y-%m-%dT%H:%M:%SZ').timestamp())
                    }
                    for a in articles[:5]
                ]
        except:
            pass
        return []
    
    def get_macro_context(self):
        """Get macroeconomic context affecting TSX stocks"""
        print("📊 Fetching macro context...")
        
        macro = {
            'oil_prices': self._get_oil_prices(),
            'forex': self._get_forex_rates(),
            'rates': self._get_interest_rates(),
            'indices': self._get_market_indices()
        }
        
        return macro
    
    def _get_oil_prices(self):
        """Get oil prices (critical for TSX energy sector - 20% of index)"""
        try:
            # WTI Crude Oil
            wti = yf.Ticker("CL=F")
            wti_hist = wti.history(period='5d')
            
            # Brent Crude Oil
            brent = yf.Ticker("BZ=F")
            brent_hist = brent.history(period='5d')
            
            if not wti_hist.empty and not brent_hist.empty:
                wti_current = wti_hist['Close'].iloc[-1]
                wti_prev = wti_hist['Close'].iloc[-2] if len(wti_hist) > 1 else wti_current
                wti_change = ((wti_current - wti_prev) / wti_prev * 100)
                
                brent_current = brent_hist['Close'].iloc[-1]
                brent_prev = brent_hist['Close'].iloc[-2] if len(brent_hist) > 1 else brent_current
                brent_change = ((brent_current - brent_prev) / brent_prev * 100)
                
                return {
                    'wti': f"${wti_current:.2f} ({wti_change:+.2f}%)",
                    'brent': f"${brent_current:.2f} ({brent_change:+.2f}%)",
                    'impact': 'Bullish for energy stocks' if wti_change > 2 else 'Bearish for energy stocks' if wti_change < -2 else 'Neutral'
                }
        except:
            pass
        
        return {'wti': 'N/A', 'brent': 'N/A', 'impact': 'Unknown'}
    
    def _get_forex_rates(self):
        """Get USD/CAD rate (affects Canadian exporters)"""
        try:
            usdcad = yf.Ticker("USDCAD=X")
            hist = usdcad.history(period='5d')
            
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change = ((current - prev) / prev * 100)
                
                return {
                    'usd_cad': f"{current:.4f} ({change:+.2f}%)",
                    'impact': 'CAD strengthening - bad for exporters' if change < -0.5 else 'CAD weakening - good for exporters' if change > 0.5 else 'Stable'
                }
        except:
            pass
        
        return {'usd_cad': 'N/A', 'impact': 'Unknown'}
    
    def _get_interest_rates(self):
        """Get bond yields (proxy for interest rate environment)"""
        try:
            # Canada 10-year bond yield
            ca10y = yf.Ticker("^TNX")  # Using US 10Y as proxy (CA data limited on yfinance)
            hist = ca10y.history(period='5d')
            
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change = current - prev
                
                return {
                    'ca_10y_yield': f"{current:.2f}% ({change:+.2f})",
                    'impact': 'Rising rates - bearish for banks, REITs' if change > 0.1 else 'Falling rates - bullish for growth' if change < -0.1 else 'Stable'
                }
        except:
            pass
        
        return {'ca_10y_yield': 'N/A', 'impact': 'Unknown'}
    
    def _get_market_indices(self):
        """Get major market indices for context"""
        try:
            # S&P 500 (affects TSX sentiment)
            sp500 = yf.Ticker("^GSPC")
            sp_hist = sp500.history(period='2d')
            
            # VIX (fear index)
            vix = yf.Ticker("^VIX")
            vix_hist = vix.history(period='2d')
            
            results = {}
            
            if not sp_hist.empty:
                sp_current = sp_hist['Close'].iloc[-1]
                sp_prev = sp_hist['Close'].iloc[-2] if len(sp_hist) > 1 else sp_current
                sp_change = ((sp_current - sp_prev) / sp_prev * 100)
                results['sp500'] = f"{sp_current:.2f} ({sp_change:+.2f}%)"
            
            if not vix_hist.empty:
                vix_current = vix_hist['Close'].iloc[-1]
                results['vix'] = f"{vix_current:.2f}"
                results['fear_level'] = 'High fear' if vix_current > 25 else 'Low fear' if vix_current < 15 else 'Normal fear'
            
            return results
        except:
            pass
        
        return {'sp500': 'N/A', 'vix': 'N/A'}

    def check_emergency_opportunities(self):
        """Check for URGENT buy/sell situations that need immediate action
        
        Triggers emergency alerts for:
        - Huge price drops in quality stocks (>5% intraday)
        - Dividend announcements on watchlist
        - Earnings beats significantly above expectations
        - Major portfolio holdings dropping dangerously
        """
        emergencies = []
        alert_config = self.alerts
        
        if not alert_config.get('enabled', False):
            return emergencies
        
        print("🚨 Checking for emergency situations...")
        
        # Check watchlist for sudden drops (buying opportunities)
        for ticker in self.watchlist:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period='2d', interval='1m')
                
                if len(hist) < 2:
                    continue
                
                # Get today's open and current price
                today_data = hist[hist.index.date == datetime.now().date()]
                if len(today_data) < 2:
                    continue
                
                open_price = today_data['Open'].iloc[0]
                current_price = today_data['Close'].iloc[-1]
                change_pct = ((current_price - open_price) / open_price * 100)
                
                # EMERGENCY: Big drop in quality stock
                if change_pct < -alert_config.get('price_drop_threshold', -5):
                    # Check if it's still quality
                    data = self.get_stock_data(ticker)
                    if data and data.get('quality_score', 0) >= 7:
                        emergencies.append({
                            'type': 'FLASH CRASH',
                            'urgency': 'HIGH',
                            'ticker': ticker,
                            'message': f"{ticker} DOWN {change_pct:.1f}% today to ${current_price:.2f}!",
                            'action': f"Quality stock on sale - BUY ${alert_config.get('emergency_buy_amount', 1000)} NOW",
                            'reason': f"Quality score {data['quality_score']}/10, temporary panic selling"
                        })
                
                # EMERGENCY: Huge spike (might want to take profits)
                if change_pct > alert_config.get('price_spike_threshold', 10):
                    if ticker in self.portfolio:
                        emergencies.append({
                            'type': 'PROFIT TAKING',
                            'urgency': 'MEDIUM',
                            'ticker': ticker,
                            'message': f"{ticker} UP {change_pct:.1f}% today!",
                            'action': f"Consider trimming position - take some profits",
                            'reason': f"Unusually large gain, might pull back"
                        })
                        
            except Exception as e:
                continue
        
        # Check portfolio holdings for danger zones
        for ticker, shares in self.portfolio.items():
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period='5d')
                
                if len(hist) < 2:
                    continue
                
                # Check if dropping below key support
                current = hist['Close'].iloc[-1]
                week_high = hist['High'].max()
                drop_from_high = ((current - week_high) / week_high * 100)
                
                if drop_from_high < -15:  # Down >15% from recent high
                    # Get news to see if fundamentals changed
                    news = self.get_news_sentiment(ticker, days=2)
                    
                    emergencies.append({
                        'type': 'PORTFOLIO ALERT',
                        'urgency': 'HIGH',
                        'ticker': ticker,
                        'message': f"{ticker} down {drop_from_high:.1f}% from recent high",
                        'action': f"Review position - check if fundamentals deteriorated",
                        'reason': f"Significant decline, may need to sell or average down",
                        'news_summary': news['analysis'] if news else "No recent news"
                    })
                    
            except Exception as e:
                continue
        
        return emergencies
    
    def _get_tsx_top_stocks(self):
        """Get TSX top stocks and popular Canadian ETFs"""
        # TSX 60 + common large caps + Popular Canadian ETFs
        top_stocks = [
            # Big Banks
            'RY.TO', 'TD.TO', 'BNS.TO', 'BMO.TO', 'CM.TO',
            # Energy
            'ENB.TO', 'SU.TO', 'CNQ.TO', 'TRP.TO', 'IMO.TO', 'CVE.TO',
            # Materials/Mining
            'ABX.TO', 'NTR.TO', 'FM.TO', 'K.TO', 'WPM.TO',
            # Industrials/Rails
            'CNR.TO', 'CP.TO', 'CSU.TO', 'TOU.TO',
            # Tech/Telecom
            'SHOP.TO', 'BCE.TO', 'T.TO', 'RCI-B.TO',
            # Consumer
            'L.TO', 'ATD.TO', 'DOL.TO', 'QSR.TO',
            # Real Estate
            'BIP-UN.TO', 'AP-UN.TO',
            # Utilities
            'FTS.TO', 'EMA.TO', 'AQN.TO', 'H.TO',
            # Insurance/Financial
            'MFC.TO', 'SLF.TO', 'GWO.TO', 'IFC.TO', 'POW.TO',
            # Healthcare/Pharma
            'GSY.TO',
        ]
        
        # Popular Canadian ETFs
        canadian_etfs = [
            # Broad Market
            'XIU.TO',   # iShares S&P/TSX 60 Index ETF
            'VCN.TO',   # Vanguard FTSE Canada All Cap Index ETF
            'XIC.TO',   # iShares Core S&P/TSX Capped Composite Index ETF
            
            # US Exposure
            'VFV.TO',   # Vanguard S&P 500 Index ETF (CAD)
            'XSP.TO',   # iShares Core S&P 500 Index ETF (CAD)
            'VUN.TO',   # Vanguard U.S. Total Market Index ETF
            
            # International
            'XAW.TO',   # iShares Core MSCI All Country World ex Canada
            'VXC.TO',   # Vanguard FTSE Global All Cap ex Canada
            'XEF.TO',   # iShares Core MSCI EAFE IMI Index ETF
            
            # Dividend
            'VDY.TO',   # Vanguard FTSE Canadian High Dividend Yield
            'XDV.TO',   # iShares Canadian Select Dividend Index ETF
            'CDZ.TO',   # iShares S&P/TSX Canadian Dividend Aristocrats
            
            # Bonds
            'VAB.TO',   # Vanguard Canadian Aggregate Bond Index ETF
            'XBB.TO',   # iShares Core Canadian Universe Bond Index ETF
            'ZAG.TO',   # BMO Aggregate Bond Index ETF
            
            # Sector ETFs
            'XEG.TO',   # iShares S&P/TSX Capped Energy Index ETF
            'XFN.TO',   # iShares S&P/TSX Capped Financials Index ETF
            'XIT.TO',   # iShares S&P/TSX Capped Information Technology
            'XRE.TO',   # iShares S&P/TSX Capped REIT Index ETF
            
            # Growth/Tech
            'TEC.TO',   # iShares Global Tech ETF
            'HGRO.TO',  # Harvest Global Equity Growth Leaders ETF
        ]
        
        all_securities = top_stocks + canadian_etfs
        
        print(f"✓ Scanning {len(top_stocks)} TSX stocks + {len(canadian_etfs)} ETFs = {len(all_securities)} total")
        return all_securities
    
    def get_stock_data(self, ticker):
        """Get comprehensive data for long-term analysis (stocks and ETFs)"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period='1y')
            
            if hist.empty:
                return None
            
            current_price = hist['Close'].iloc[-1]
            year_ago_price = hist['Close'].iloc[0]
            year_return = ((current_price - year_ago_price) / year_ago_price * 100)
            
            # Detect if this is an ETF (has lower expense ratio, no PE typically)
            is_etf = info.get('quoteType') == 'ETF'
            
            data = {
                'ticker': ticker,
                'name': info.get('longName', ticker),
                'type': 'ETF' if is_etf else 'Stock',
                'price': round(current_price, 2),
                'market_cap': info.get('totalAssets' if is_etf else 'marketCap', 0),
                'dividend_yield': round(info.get('yield' if is_etf else 'dividendYield', 0), 2) if info.get('yield' if is_etf else 'dividendYield') else 0,
                'year_return': round(year_return, 2),
                'sector': info.get('category' if is_etf else 'sector', 'N/A'),
            }
            
            # Stock-specific metrics
            if not is_etf:
                data.update({
                    'pe_ratio': info.get('trailingPE'),
                    'forward_pe': info.get('forwardPE'),
                    'peg_ratio': info.get('pegRatio'),
                    'debt_to_equity': info.get('debtToEquity'),
                    'profit_margin': round(info.get('profitMargins', 0) * 100, 2) if info.get('profitMargins') else None,
                    'roe': round(info.get('returnOnEquity', 0) * 100, 2) if info.get('returnOnEquity') else None,
                    'is_undervalued': self._check_valuation(info),
                    'quality_score': self._calculate_quality_score(info),
                })
            else:
                # ETF-specific metrics
                data.update({
                    'expense_ratio': round(info.get('annualReportExpenseRatio', 0) * 100, 3) if info.get('annualReportExpenseRatio') else None,
                    'ytd_return': info.get('ytdReturn'),
                    'three_year_return': info.get('threeYearAverageReturn'),
                    'five_year_return': info.get('fiveYearAverageReturn'),
                    'quality_score': self._calculate_etf_score(info, hist),
                })
            
            return data
        except Exception as e:
            return None
    
    def _check_valuation(self, info):
        """Simple valuation check for long-term investing"""
        pe = info.get('trailingPE')
        peg = info.get('pegRatio')
        
        if pe and peg:
            # PEG < 1 often indicates undervaluation
            # PE < industry average also good
            if peg < 1.5 and pe < 25:
                return True
        return False
    
    def _calculate_quality_score(self, info):
        """Score stock quality (0-10) based on fundamentals"""
        score = 5  # Start neutral
        
        # Dividend yield (stability indicator)
        div_yield = info.get('dividendYield', 0)
        if div_yield and div_yield > 0.03:  # >3%
            score += 1
        
        # Profit margin
        margin = info.get('profitMargins', 0)
        if margin and margin > 0.15:  # >15%
            score += 1
        
        # Return on Equity
        roe = info.get('returnOnEquity', 0)
        if roe and roe > 0.15:  # >15%
            score += 1
        
        # Debt management
        debt_equity = info.get('debtToEquity')
        if debt_equity and debt_equity < 100:  # Low debt
            score += 1
        
        # PEG ratio (growth at reasonable price)
        peg = info.get('pegRatio')
        if peg and peg < 2:
            score += 1
        
        return min(score, 10)
    
    def _calculate_etf_score(self, info, hist):
        """Score ETF quality (0-10) based on ETF-specific factors"""
        score = 5  # Start neutral
        
        # Low expense ratio (< 0.5% is good)
        expense = info.get('annualReportExpenseRatio', 0)
        if expense and expense < 0.005:  # < 0.5%
            score += 2
        elif expense and expense < 0.01:  # < 1%
            score += 1
        
        # Good dividend/distribution yield
        div_yield = info.get('yield', 0)
        if div_yield and div_yield > 0.03:  # > 3%
            score += 1
        
        # Strong historical returns
        three_yr = info.get('threeYearAverageReturn', 0)
        if three_yr and three_yr > 0.10:  # > 10% annualized
            score += 2
        elif three_yr and three_yr > 0.05:  # > 5% annualized
            score += 1
        
        # Check volatility (lower is better for long-term)
        if len(hist) > 50:
            volatility = hist['Close'].pct_change().std()
            if volatility < 0.015:  # Low volatility
                score += 1
        
        return min(score, 10)
    
    def scan_market_opportunities(self):
        """Scan TSX for long-term opportunities (stocks and ETFs)"""
        print("🔍 Scanning TSX market for opportunities...")
        
        opportunities = []
        
        # Scan top TSX stocks and ETFs
        for ticker in self.tsx_top_stocks:
            data = self.get_stock_data(ticker)
            if data and data['quality_score'] >= 6:  # Only quality securities
                # Skip if already in portfolio at high weight
                if ticker in self.portfolio:
                    continue
                opportunities.append(data)
        
        # Sort by quality score and type (separate stocks from ETFs)
        opportunities.sort(key=lambda x: (x.get('type', 'Stock') == 'Stock', x['quality_score'], x.get('is_undervalued', False)), reverse=True)
        
        return opportunities[:15]  # Top 15 opportunities
    
    def analyze_portfolio(self):
        """Analyze current portfolio holdings"""
        print("📊 Analyzing your portfolio...")
        
        holdings_analysis = []
        total_value = self.cash
        
        for ticker, shares in self.portfolio.items():
            data = self.get_stock_data(ticker)
            if data:
                position_value = shares * data['price']
                total_value += position_value
                
                holdings_analysis.append({
                    'ticker': ticker,
                    'shares': shares,
                    'price': data['price'],
                    'value': position_value,
                    'quality_score': data['quality_score'],
                    'dividend_yield': data['dividend_yield'],
                    'year_return': data['year_return'],
                    'recommendation': self._get_holding_recommendation(data, shares, position_value)
                })
        
        # Calculate position percentages
        for holding in holdings_analysis:
            holding['portfolio_weight'] = round((holding['value'] / total_value * 100), 1)
        
        return holdings_analysis, total_value
    
    def _get_holding_recommendation(self, data, shares, position_value):
        """Decide if should HOLD, BUY MORE, or TRIM"""
        quality = data['quality_score']
        
        if quality >= 8:
            return 'HOLD/BUY MORE' if (data['type'] != 'ETF' and data['is_undervalued']) else 'HOLD'
        elif quality >= 6:
            return 'HOLD'
        else:
            return 'CONSIDER TRIMMING'
    
    def analyze_watchlist(self):
        """Analyze personal watchlist stocks"""
        if not self.watchlist:
            return []
        
        print(f"👀 Checking your {len(self.watchlist)} watchlist stocks...")
        
        watchlist_analysis = []
        for ticker in self.watchlist:
            data = self.get_stock_data(ticker)
            if data:
                watchlist_analysis.append(data)
        
        return watchlist_analysis
    
    def generate_daily_digest(self, session='morning'):
        """Generate digest for market open (morning) or close (afternoon)
        
        Args:
            session: 'morning' for 9:30 AM digest, 'afternoon' for 3:00 PM digest
        """
        
        # Check for emergencies FIRST
        emergencies = self.check_emergency_opportunities()
        
        # Get all analysis
        portfolio_analysis, total_value = self.analyze_portfolio()
        market_opportunities = self.scan_market_opportunities()
        watchlist_analysis = self.analyze_watchlist()

        # Get macro context (oil, forex, rates)
        macro_context = self.get_macro_context()
        
        # Get news sentiment for portfolio + watchlist
        news_insights = {}
        print("📰 Fetching news sentiment...")

        tickers_to_check = list(self.portfolio.keys()) + self.watchlist
        for ticker in tickers_to_check:
            news = self.get_news_sentiment(ticker, days=1 if session == 'afternoon' else 3)
            if news:  # Only add if news exists
                news_insights[ticker] = news
        
        # Get market overview
        tsx = yf.Ticker("^GSPTSE")
        tsx_hist = tsx.history(period='5d')
        tsx_current = tsx_hist['Close'].iloc[-1] if not tsx_hist.empty else 0
        tsx_prev = tsx_hist['Close'].iloc[-2] if len(tsx_hist) > 1 else tsx_current
        tsx_change = ((tsx_current - tsx_prev) / tsx_prev * 100) if tsx_prev else 0
        
        # Get intraday data if afternoon session
        intraday_change = None
        if session == 'afternoon':
            tsx_today = tsx.history(period='1d', interval='1m')
            if not tsx_today.empty and len(tsx_today) > 0:
                open_price = tsx_today['Open'].iloc[0]
                current_price = tsx_today['Close'].iloc[-1]
                intraday_change = ((current_price - open_price) / open_price * 100)
        
        # Build AI prompt based on session
        emergency_section = ""
        if emergencies:
            emergency_section = f"""
🚨 EMERGENCY ALERTS - IMMEDIATE ACTION REQUIRED:
{self._format_emergencies(emergencies)}

"""
        
        news_section = ""
        if news_insights:
            news_section = f"""
📰 NEWS SENTIMENT (Stocks with recent news):
{self._format_news_insights(news_insights)}

"""
        else:
            news_section = """
📰 NEWS SENTIMENT: No significant news today for your portfolio/watchlist stocks.
(This is normal - most stocks don't have daily news. Focus on technical/fundamental analysis.)

"""
        
        macro_section = f"""
🌍 MACRO CONTEXT (Affecting TSX):

OIL PRICES (20% of TSX is energy):
  WTI Crude: {macro_context['oil_prices']['wti']}
  Brent Crude: {macro_context['oil_prices']['brent']}
  Impact: {macro_context['oil_prices']['impact']}

CURRENCY:
  USD/CAD: {macro_context['forex']['usd_cad']}
  Impact: {macro_context['forex']['impact']}

INTEREST RATES:
  10Y Yield: {macro_context['rates']['ca_10y_yield']}
  Impact: {macro_context['rates']['impact']}

MARKET SENTIMENT:
  S&P 500: {macro_context['indices'].get('sp500', 'N/A')}
  VIX (Fear): {macro_context['indices'].get('vix', 'N/A')} - {macro_context['indices'].get('fear_level', 'Unknown')}

"""
        if session == 'morning':
            session_emoji = "🌅"
            session_title = "MARKET OPEN"
            session_context = """
This is the MORNING digest (9:30 AM ET - market just opened).

Focus on:
- Fresh opportunities after analyzing overnight news and pre-market moves
- What to BUY today if you have cash available
- Any changes to watchlist stocks that make them attractive
- Setting expectations for the day"""
        else:
            session_emoji = "🌆"
            session_title = "PRE-MARKET CLOSE"
            intraday_text = f"\nToday's Intraday Change: {intraday_change:+.2f}%" if intraday_change else ""
            session_context = f"""
This is the AFTERNOON digest (3:00 PM ET - 1 hour before market close).{intraday_text}

Focus on:
- Quick review of how the day went
- URGENT actions before 4 PM close (buy/sell opportunities expiring today)
- Any positions that need trimming TODAY due to significant moves
- Brief recap - don't repeat full analysis from morning"""
        
        prompt = f"""{session_emoji} You are a long-term growth investment advisor analyzing Canadian stocks (TSX).

📅 {session_title} - {datetime.now().strftime('%B %d, %Y at %I:%M %p ET')}

{session_context}

{emergency_section}

🇨🇦 TSX MARKET
S&P/TSX Composite: {tsx_current:.2f} ({tsx_change:+.2f}% from yesterday)

{macro_section}

💼 YOUR PORTFOLIO (Total: ${total_value:,.2f} CAD)
Cash Available: ${self.cash:,.2f} CAD ({self.cash/total_value*100:.1f}%)

Current Holdings:
{self._format_portfolio_for_ai(portfolio_analysis)}

{news_section}

🎯 YOUR PERSONAL WATCHLIST
{self._format_watchlist_for_ai(watchlist_analysis)}

🔍 TOP TSX MARKET OPPORTUNITIES (Quality Score 6+)
{self._format_opportunities_for_ai(market_opportunities)}

📋 YOUR INVESTMENT PREFERENCES
{yaml.dump(self.preferences, default_flow_style=False)}

🤖 INSTRUCTIONS:
Provide a {'MORNING' if session == 'morning' else 'AFTERNOON'} digest for a LONG-TERM GROWTH investor (not day trading).

IMPORTANT: 
- If no news is available for a stock, that's NORMAL - base recommendations on fundamentals and technical analysis instead
- Consider macro context (oil prices affect energy stocks, USD/CAD affects exporters, rates affect banks)
- Focus on quality (score 7+) and value (reasonable PE ratios)
- Don't demand news - most days stocks don't have news and that's fine!

{"**MORNING DIGEST FORMAT:**" if session == 'morning' else "**AFTERNOON DIGEST FORMAT:**"}

1. **Market Summary**: Quick TSX overview and key sector trends

2. {"**Portfolio Review**: Any holdings that should be HELD, BOUGHT MORE, or TRIMMED" if session == 'morning' else "**Today's Moves**: How did the market/your holdings perform today?"}

3. **{"Today's" if session == 'morning' else "Action Before Close"} Action Items**:
   - SPECIFIC buy recommendations with:
     * Ticker and company name
     * Target buy price or "at market"
     * Suggested investment amount
     * Clear rationale (valuation, growth, dividend, etc.)
   - Any sells needed {"(only if fundamental deterioration)" if session == 'morning' else "(urgent only if something changed significantly today)"}

4. {"**Watchlist Updates**: Comments on your personal watchlist stocks" if session == 'morning' else "**Watchlist**: Any urgent opportunities or updates from morning"}

5. {"**Long-term Outlook**: Any macro trends affecting Canadian market" if session == 'morning' else "**Set Up for Tomorrow**: Anything to watch overnight or tomorrow"}

Keep recommendations ACTIONABLE and SPECIFIC. Focus on quality companies with:
- Strong fundamentals (quality score 6+)
- Reasonable valuations (not overpaying)
- Good dividend yields (3%+) preferred
- Solid balance sheets

{"Be conservative. Better to miss an opportunity than chase overvalued stocks." if session == 'morning' else "Keep it brief - focus only on time-sensitive items before market close."}
"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"❌ Error generating digest: {e}"
    
    def _format_portfolio_for_ai(self, analysis):
        """Format portfolio data for AI prompt"""
        lines = []
        for h in analysis:
            lines.append(
                f"  {h['ticker']}: {h['shares']} shares @ ${h['price']} = ${h['value']:,.0f} "
                f"({h['portfolio_weight']}%) | Quality: {h['quality_score']}/10 | "
                f"Div: {h['dividend_yield']}% | YTD: {h['year_return']:+.1f}% | {h['recommendation']}"
            )
        return '\n'.join(lines) if lines else "  (No holdings)"
    
    def _format_watchlist_for_ai(self, analysis):
        """Format portfolio data for AI prompt"""
        lines = []
        for h in analysis:
            lines.append(
                f"  {h['ticker']}: {h['shares']} shares @ ${h['price']} = ${h['value']:,.0f} "
                f"({h['portfolio_weight']}%) | Quality: {h['quality_score']}/10 | "
                f"Div: {h['dividend_yield']}% | YTD: {h['year_return']:+.1f}% | {h['recommendation']}"
            )
        return '\n'.join(lines) if lines else "  (No holdings)"
    
    def _format_watchlist_for_ai(self, analysis):
        """Format watchlist for AI"""
        if not analysis:
            return "  (No watchlist)"
        lines = []
        for stock in analysis:
            if stock['type'] == 'ETF':
                lines.append(
                    f"  {stock['ticker']} ({stock['name']}): ${stock['price']} | "
                    f"Quality: {stock['quality_score']}/10 | MER: {stock.get('expense_ratio', 'N/A')}% | "
                    f"Div: {stock['dividend_yield']}% | YTD: {stock['year_return']:+.1f}%"
                )
            else:
                lines.append(
                    f"  {stock['ticker']} ({stock['name']}): ${stock['price']} | "
                    f"Quality: {stock['quality_score']}/10 | PE: {stock['pe_ratio']} | "
                    f"Div: {stock['dividend_yield']}% | Undervalued: {'YES' if stock['is_undervalued'] else 'NO'}"
                )

        return '\n'.join(lines)
    
    def _format_opportunities_for_ai(self, opportunities):
        """Format market opportunities for AI"""
        if not opportunities:
            return "  (No strong opportunities found)"
        
        # Separate stocks and ETFs
        stocks = [s for s in opportunities if s.get('type') == 'Stock']
        etfs = [e for e in opportunities if e.get('type') == 'ETF']
        
        lines = []
        
        if stocks:
            lines.append("  STOCKS:")
            for i, stock in enumerate(stocks[:5], 1):  # Top 5 stocks
                pe_str = f"PE: {stock['pe_ratio']:.1f}" if stock.get('pe_ratio') else "PE: N/A"
                underval = "✓ Undervalued" if stock.get('is_undervalued') else ""
                lines.append(
                    f"    {i}. {stock['ticker']} ({stock['name']}): ${stock['price']} | "
                    f"Quality: {stock['quality_score']}/10 | {pe_str} | "
                    f"Div: {stock['dividend_yield']}% | Sector: {stock['sector']} {underval}"
                )
        
        if etfs:
            lines.append("\n  ETFs:")
            for i, etf in enumerate(etfs[:5], 1):  # Top 5 ETFs
                expense = f"MER: {etf.get('expense_ratio', 0):.2f}%" if etf.get('expense_ratio') else "MER: N/A"
                lines.append(
                    f"    {i}. {etf['ticker']} ({etf['name']}): ${etf['price']} | "
                    f"Quality: {etf['quality_score']}/10 | {expense} | "
                    f"Div: {etf['dividend_yield']}% | YTD: {etf['year_return']:+.1f}%"
                )
        
        return '\n'.join(lines) if lines else "  (No strong opportunities found)"
    
    def _format_emergencies(self, emergencies):
        """Format emergency alerts for display"""
        lines = []
        for i, alert in enumerate(emergencies, 1):
            urgency_emoji = "🔴" if alert['urgency'] == 'HIGH' else "🟡"
            lines.append(f"{urgency_emoji} ALERT #{i}: {alert['type']}")
            lines.append(f"   {alert['ticker']}: {alert['message']}")
            lines.append(f"   ACTION: {alert['action']}")
            lines.append(f"   WHY: {alert['reason']}")
            if 'news_summary' in alert:
                lines.append(f"   NEWS: {alert['news_summary'][:100]}...")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_news_insights(self, news_insights):
        """Format news sentiment for AI"""
        lines = []
        for ticker, news in news_insights.items():
            lines.append(f"  {ticker} ({news['headline_count']} articles):")
            lines.append(f"    {news['analysis']}")
            lines.append(f"    Top Headlines:")
            for headline in news['headlines'][:3]:
                lines.append(f"      - {headline}")
            lines.append("")
        return '\n'.join(lines)
    
    def strip_markdown(self, text):
        # Remove **bold** or __bold__
        text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
        # Remove *italic* or _italic_
        text = re.sub(r'(\*|_)(.*?)\1', r'\2', text)
        # Optional: remove other markdown like `code` or [links](url)
        text = re.sub(r'`(.*?)`', r'\1', text)
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        return text
    
    def send_notification(self, digest, session='morning', is_emergency=False):
        """Send digest via email or SMS
        
        Args:
            session: 'morning' or 'afternoon' for subject line
            is_emergency: True if this is an urgent alert
        """
        method = self.notification.get('method', 'console')
        
        if method == 'email':
            digest = markdown.markdown(digest)
            self._send_email(digest, session, is_emergency)
        elif method == 'sms':
            digest = self.strip_markdown(digest)
            self._send_sms(digest, session, is_emergency)
        else:
            # Console output (default)
            digest = self.strip_markdown(digest)
            self._print_digest(digest, session, is_emergency)
    
    def _send_email(self, digest, session='morning', is_emergency=False):
        """Send digest via email"""
        config = self.notification.get('email', {})
        
        if is_emergency:
            session_emoji = "🚨"
            session_label = "URGENT ALERT"
        else:
            session_emoji = "🌅" if session == 'morning' else "🌆"
            session_label = "Market Open" if session == 'morning' else "Pre-Close"
        
        try:
            msg = MIMEMultipart()
            msg['From'] = config['from_email']
            msg['To'] = config['to_email']
            
            if is_emergency:
                msg['Subject'] = f"{session_emoji} URGENT: Stock Alert - {datetime.now().strftime('%b %d, %I:%M %p')}"
                msg['Priority'] = '1'  # High priority
            else:
                msg['Subject'] = f"{session_emoji} Stock Digest - {session_label} - {datetime.now().strftime('%b %d')}"
            
            msg.attach(MIMEText(digest, 'html'))
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(config['from_email'], os.environ.get('EMAIL_PASSWORD'))
                server.send_message(msg)
            
            print(f"✅ {session_label} email sent successfully!")
        
        except Exception as e:
            print(f"❌ Email error: {e}")
            self._print_digest(digest, session, is_emergency)
    
    def _send_sms(self, digest, session='morning', is_emergency=False):
        """Send digest via SMS (using Twilio or similar)"""
        # Implement SMS sending here
        print(f"⚠️  SMS not implemented yet, printing {session} digest to console:")
        self._print_digest(digest, session, is_emergency)
    
    def _print_digest(self, digest, session='morning', is_emergency=False):
        """Print digest to console"""
        border = "=" * 80
        
        if is_emergency:
            session_emoji = "🚨"
            session_title = "URGENT ALERT"
        else:
            session_emoji = "🌅" if session == 'morning' else "🌆"
            session_title = "MARKET OPEN (9:30 AM)" if session == 'morning' else "PRE-CLOSE (3:00 PM)"
        
        print(f"\n{border}")
        print(f"{session_emoji} DAILY LONG-TERM INVESTMENT DIGEST - {session_title}")
        print(f"{border}\n")
        print(digest)
        print(f"\n{border}\n")
        
        # Save to file
        prefix = "URGENT_" if is_emergency else ""
        filename = f"{prefix}digest_{datetime.now().strftime('%Y%m%d_%H%M')}_{session}.txt"
        with open(filename, 'w') as f:
            f.write(digest)
        print(f"💾 Saved to: {filename}\n")
    
    def check_and_alert_emergencies(self):
        """Standalone emergency check - can be run more frequently (e.g. every 30 min)"""
        emergencies = self.check_emergency_opportunities()
        
        if emergencies:
            # Generate quick emergency digest
            emergency_text = f"""🚨 URGENT STOCK ALERT - {datetime.now().strftime('%B %d, %Y at %I:%M %p ET')}

{self._format_emergencies(emergencies)}

This is an automated urgent alert based on your watchlist and portfolio.
Check your regular digest for full market analysis.

---
Generated by your AI Stock Agent
"""
            self.send_notification(emergency_text, session='emergency', is_emergency=True)
            return True
        
        return False


if __name__ == "__main__":
    import sys
    
    # Allow running specific session from command line
    # Usage: python stock_agent.py morning  OR  python stock_agent.py afternoon
    session = sys.argv[1] if len(sys.argv) > 1 else 'morning'
    
    if session not in ['morning', 'afternoon']:
        print("❌ Invalid session. Use: python stock_agent.py morning  OR  python stock_agent.py afternoon")
        sys.exit(1)
    
    agent = LongTermStockAgent('portfolio.yaml')
    digest = agent.generate_daily_digest(session=session)
    agent.send_notification(digest, session=session)