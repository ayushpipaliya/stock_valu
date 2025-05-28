# yahoo_key_metrics_corrected.py
import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, Any, Optional
import re
import time
from urllib.parse import quote


class YahooKeyMetricsExtractor:
    """Extract specific key metrics from Yahoo Finance"""
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_key_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        Extract PE Ratio (TTM), Forward Dividend & Yield %, Growth Estimates Next Year %, and Current Price
        
        Args:
            symbol (str): Stock ticker symbol (e.g., 'AAPL')
            
        Returns:
            Dict containing the key metrics
        """
        metrics = {
            'symbol': symbol.upper(),
            'current_price': None,
            'pe_ratio_ttm': None,
            'forward_dividend_rate': None,
            'forward_dividend_yield': None,
            'growth_estimate_next_year': None,
            'error': None
        }
        
        try:
            # Get PE Ratio, Dividend info, and Current Price from summary page
            summary_metrics = self._get_summary_metrics(symbol)
            metrics.update(summary_metrics)
            
            # Small delay between requests
            time.sleep(1)
            
            # Get Growth Estimates from analysis page
            growth_metrics = self._get_growth_estimates(symbol)
            metrics.update(growth_metrics)
            
        except Exception as e:
            metrics['error'] = f"Error fetching metrics for {symbol}: {str(e)}"
        
        return metrics
    
    def _get_summary_metrics(self, symbol: str) -> Dict[str, Any]:
        """Extract PE Ratio, Dividend info, and Current Price from Yahoo Finance summary page"""
        metrics = {}
        
        try:
            url = f"https://finance.yahoo.com/quote/{quote(symbol.upper())}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return {'error': f"Failed to retrieve summary data: Status code {response.status_code}"}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract current stock price
            self._extract_current_price(soup, metrics)
            
            # Extract PE ratio and dividend info using multiple methods
            self._extract_by_testid(soup, metrics)
            self._extract_from_quote_stats(soup, metrics)
            self._extract_from_tables(soup, metrics)
            
        except Exception as e:
            metrics['error'] = f"Error in summary metrics: {str(e)}"
        
        return metrics
    
    def _extract_current_price(self, soup: BeautifulSoup, metrics: Dict[str, Any]):
        """Extract current stock price from the page"""
        try:
            # Method 1: Look for span with data-testid="qsp-price" (most reliable)
            price_element = soup.find('span', {'data-testid': 'qsp-price'})
            if price_element:
                price_text = price_element.get_text(strip=True)
                price = self._clean_numeric_value(price_text)
                if price and price > 0:
                    metrics['current_price'] = price
                    return
            
            # Method 2: Look for fin-streamer with price data
            price_elements = soup.find_all('fin-streamer', {'data-field': 'regularMarketPrice'})
            for element in price_elements:
                value = element.get('value') or element.get_text(strip=True)
                if value:
                    price = self._clean_numeric_value(value)
                    if price and price > 0:
                        metrics['current_price'] = price
                        return
            
            # Method 3: Look for price in quote-price section
            quote_price_section = soup.find('section', {'data-testid': 'quote-price'})
            if quote_price_section:
                # Look for spans with price-like classes or patterns
                price_spans = quote_price_section.find_all('span', class_=lambda x: x and ('price' in str(x).lower() or 'qsp' in str(x).lower()))
                for span in price_spans:
                    text = span.get_text(strip=True)
                    # Match patterns like "201.18" (price format)
                    if re.match(r'^\d{1,4}\.\d{2}$', text):
                        price = self._clean_numeric_value(text)
                        if price and price > 1:  # Reasonable price threshold
                            metrics['current_price'] = price
                            return
            
            # Method 4: Look in the quote header area with improved pattern matching
            quote_header = soup.find('div', {'data-testid': 'quote-header'}) or soup.find('section', {'data-testid': 'quote-hdr'})
            if quote_header:
                # Look for spans that contain price-like values with better pattern
                spans = quote_header.find_all('span')
                for span in spans:
                    text = span.get_text(strip=True)
                    # More specific pattern for stock prices (e.g., 201.18, 45.67, etc.)
                    if re.match(r'^\d{1,4}\.\d{2}$', text):
                        price = self._clean_numeric_value(text)
                        if price and price > 1:  # Reasonable price threshold
                            metrics['current_price'] = price
                            return
            
            # Method 5: Fallback - look for any element with price-like content
            all_elements = soup.find_all(['span', 'div'], string=re.compile(r'^\d{1,4}\.\d{2}$'))
            for element in all_elements:
                text = element.get_text(strip=True)
                price = self._clean_numeric_value(text)
                if price and price > 1:
                    # Additional validation - check if parent has price-related attributes
                    parent = element.parent
                    if parent and (parent.get('data-testid') or parent.get('class')):
                        parent_attrs = str(parent.get('data-testid', '')) + ' ' + ' '.join(parent.get('class', []))
                        if any(keyword in parent_attrs.lower() for keyword in ['price', 'quote', 'market']):
                            metrics['current_price'] = price
                            return
            
        except Exception as e:
            print(f"Error extracting current price: {str(e)}")
            
    def _extract_by_testid(self, soup: BeautifulSoup, metrics: Dict[str, Any]):
        """Extract metrics using data-testid attributes"""
        test_ids = {
            'PE_RATIO-value': 'pe_ratio_ttm',
            'FORWARD_DIVIDEND_AND_YIELD-value': 'forward_dividend_yield',
            'TD_DIVIDEND_AND_YIELD-value': 'forward_dividend_yield'
        }
        
        for test_id, metric_key in test_ids.items():
            element = soup.find(attrs={'data-testid': test_id})
            if element:
                value = element.get_text(strip=True)
                if value and value.upper() not in ['N/A', 'NA', '--']:
                    if metric_key == 'forward_dividend_yield':
                        self._parse_dividend_info(value, metrics)
                    elif metric_key == 'pe_ratio_ttm':
                        metrics[metric_key] = self._clean_numeric_value(value)
    
    def _extract_from_quote_stats(self, soup: BeautifulSoup, metrics: Dict[str, Any]):
        """Extract from quote statistics section"""
        # Look for various quote statistics sections
        stats_sections = soup.find_all('div', {'data-testid': lambda x: x and 'quote' in x and 'stat' in x})
        
        if not stats_sections:
            # Fallback to finding sections with financial data
            stats_sections = soup.find_all('section', class_=lambda x: x and 'quote' in str(x).lower())
        
        for section in stats_sections:
            # Look for list items or table rows with labels and values
            items = section.find_all(['li', 'tr', 'div'])
            
            for item in items:
                try:
                    # Try to find label and value pairs
                    text = item.get_text(strip=True).lower()
                    
                    if 'pe ratio' in text or 'p/e ratio' in text:
                        if 'ttm' in text or 'trailing' in text:
                            # Extract the numeric value
                            numbers = re.findall(r'\d+\.?\d*', item.get_text())
                            if numbers:
                                metrics['pe_ratio_ttm'] = self._clean_numeric_value(numbers[-1])
                    
                    elif 'dividend' in text and 'yield' in text:
                        # Look for dividend information
                        div_text = item.get_text(strip=True)
                        self._parse_dividend_info(div_text, metrics)
                        
                except Exception:
                    continue
    
    def _extract_from_tables(self, soup: BeautifulSoup, metrics: Dict[str, Any]):
        """Extract from financial tables"""
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    try:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        
                        if ('pe ratio' in label or 'p/e ratio' in label) and ('ttm' in label or 'trailing' in label):
                            metrics['pe_ratio_ttm'] = self._clean_numeric_value(value)
                        elif 'forward annual dividend rate' in label:
                            metrics['forward_dividend_rate'] = self._clean_numeric_value(value)
                        elif 'forward annual dividend yield' in label:
                            metrics['forward_dividend_yield'] = self._clean_percentage_value(value)
                        elif 'dividend' in label and 'yield' in label and 'forward' in label:
                            self._parse_dividend_info(value, metrics)
                            
                    except Exception:
                        continue
    
    def _get_growth_estimates(self, symbol: str) -> Dict[str, Any]:
        """Extract growth estimates from Yahoo Finance analysis page"""
        metrics = {}
        
        try:
            url = f"https://finance.yahoo.com/quote/{quote(symbol.upper())}/analysis"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return {'error': f"Failed to retrieve analysis data: Status code {response.status_code}"}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for Growth Estimates table
            growth_estimate = self._extract_growth_estimate_table(soup, symbol)
            if growth_estimate is not None:
                metrics['growth_estimate_next_year'] = growth_estimate
            
        except Exception as e:
            metrics['error'] = f"Error in growth estimates: {str(e)}"
        
        return metrics
    
    def _extract_growth_estimate_table(self, soup: BeautifulSoup, symbol: str) -> Optional[float]:
        """Extract growth estimate for next year from the analysis page"""
        try:
            # Method 1: Look for specific Growth Estimates section
            growth_section = soup.find('section', {'data-testid': 'growthEstimate'})
            
            if growth_section:
                table = growth_section.find('table')
                if table:
                    result = self._extract_from_growth_table(table, symbol)
                    if result is not None:
                        return result
            
            # Method 2: Look for tables containing growth estimates
            tables = soup.find_all('table')
            
            for table in tables:
                table_text = table.get_text().lower()
                if 'growth' in table_text and 'next year' in table_text:
                    result = self._extract_from_growth_table(table, symbol)
                    if result is not None:
                        return result
            
            # Method 3: Look for any table with "estimate" in nearby text
            for table in tables:
                # Check if table or its parent contains growth/estimate keywords
                parent_text = ""
                parent = table.parent
                if parent:
                    parent_text = parent.get_text().lower()
                
                if ('estimate' in parent_text and 'growth' in parent_text) or 'next year' in table.get_text().lower():
                    result = self._extract_from_growth_table(table, symbol)
                    if result is not None:
                        return result
                        
        except Exception as e:
            print(f"Error extracting growth estimates: {str(e)}")
        
        return None
    
    def _extract_from_growth_table(self, table: BeautifulSoup, symbol: str) -> Optional[float]:
        """Extract growth estimate from a specific table"""
        try:
            # Find header row
            header_row = table.find('thead')
            if not header_row:
                header_row = table.find('tr')
            
            if not header_row:
                return None
                
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # Find "Next Year" column index
            next_year_col_idx = None
            for i, header in enumerate(headers):
                if any(keyword in header.lower() for keyword in ['next year', 'next 5 years', '2025', '2024']):
                    next_year_col_idx = i
                    break
            
            if next_year_col_idx is None:
                return None
            
            # Find rows and look for the company data
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) > next_year_col_idx:
                    first_cell_text = cells[0].get_text(strip=True).upper()
                    
                    # Check if this is the company row (not S&P 500 or sector)
                    if (first_cell_text == symbol.upper() or 
                        (len(first_cell_text) <= 6 and first_cell_text.isalpha() and 
                         'S&P' not in first_cell_text and '500' not in first_cell_text and
                         'SECTOR' not in first_cell_text and 'INDUSTRY' not in first_cell_text)):
                        
                        growth_value = cells[next_year_col_idx].get_text(strip=True)
                        if growth_value and growth_value.upper() not in ['N/A', 'NA', '--']:
                            return self._clean_percentage_value(growth_value)
            
        except Exception:
            pass
        
        return None
    
    def _parse_dividend_info(self, dividend_text: str, metrics: Dict[str, Any]):
        """Parse dividend rate and yield from text like '0.25 (1.2%)'"""
        try:
            # Pattern to match: number followed by optional (percentage)
            pattern = r'(\d+\.?\d*)\s*\((\d+\.?\d*%?)\)'
            match = re.search(pattern, dividend_text)
            
            if match:
                metrics['forward_dividend_rate'] = float(match.group(1))
                yield_text = match.group(2)
                metrics['forward_dividend_yield'] = self._clean_percentage_value(yield_text)
            else:
                # Try to extract just numbers
                numbers = re.findall(r'\d+\.?\d*', dividend_text)
                percentages = re.findall(r'\d+\.?\d*%', dividend_text)
                
                if numbers and not metrics.get('forward_dividend_rate'):
                    metrics['forward_dividend_rate'] = float(numbers[0])
                
                if percentages and not metrics.get('forward_dividend_yield'):
                    metrics['forward_dividend_yield'] = self._clean_percentage_value(percentages[0])
                    
        except Exception as e:
            print(f"Error parsing dividend info: {str(e)}")
    
    def _clean_numeric_value(self, value: str) -> Optional[float]:
        """Clean and convert numeric value"""
        if not value or str(value).upper() in ['N/A', 'NA', '--', '', 'NULL']:
            return None
        
        try:
            # Remove commas and other non-numeric characters except decimal point and minus
            cleaned = re.sub(r'[^\d.-]', '', str(value))
            if cleaned and cleaned not in ['-', '.', '-.']:
                return float(cleaned)
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _clean_percentage_value(self, value: str) -> Optional[float]:
        """Clean and convert percentage value"""
        if not value or str(value).upper() in ['N/A', 'NA', '--', '', 'NULL']:
            return None
        
        try:
            # Remove % sign and other non-numeric characters except decimal point and minus
            cleaned = re.sub(r'[^\d.-]', '', str(value))
            if cleaned and cleaned not in ['-', '.', '-.']:
                return float(cleaned)
        except (ValueError, TypeError):
            pass
        
        return None
    
    def get_multiple_stocks_metrics(self, symbols: list) -> Dict[str, Dict[str, Any]]:
        """Get key metrics for multiple stocks"""
        results = {}
        
        for i, symbol in enumerate(symbols):
            print(f"Fetching metrics for {symbol} ({i+1}/{len(symbols)})...")
            results[symbol.upper()] = self.get_key_metrics(symbol)
            
            # Add delay between requests to be respectful
            if i < len(symbols) - 1:
                time.sleep(2)
        
        return results
    
    def save_metrics_to_json(self, metrics: Dict[str, Any], filename: str):
        """Save metrics to JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            print(f"Metrics saved to {filename}")
        except Exception as e:
            print(f"Error saving to file: {str(e)}")
    
    def format_metrics_display(self, metrics: Dict[str, Any]) -> str:
        """Format metrics for display"""
        lines = []
        lines.append(f"Symbol: {metrics['symbol']}")
        
        if metrics['current_price']:
            lines.append(f"Current Price: ${metrics['current_price']:.2f}")
        else:
            lines.append("Current Price: N/A")
        
        if metrics['pe_ratio_ttm']:
            lines.append(f"PE Ratio (TTM): {metrics['pe_ratio_ttm']:.2f}")
        else:
            lines.append("PE Ratio (TTM): N/A")
        
        if metrics['forward_dividend_rate']:
            lines.append(f"Forward Dividend Rate: ${metrics['forward_dividend_rate']:.2f}")
        else:
            lines.append("Forward Dividend Rate: N/A")
        
        if metrics['forward_dividend_yield']:
            lines.append(f"Forward Dividend Yield: {metrics['forward_dividend_yield']:.2f}%")
        else:
            lines.append("Forward Dividend Yield: N/A")
        
        if metrics['growth_estimate_next_year']:
            lines.append(f"Growth Estimate Next Year: {metrics['growth_estimate_next_year']:.2f}%")
        else:
            lines.append("Growth Estimate Next Year: N/A")
        
        if metrics.get('error'):
            lines.append(f"Error: {metrics['error']}")
        
        return '\n'.join(lines)


# Example usage and testing
if __name__ == "__main__":
    # Initialize the extractor
    extractor = YahooKeyMetricsExtractor()
    
    # Test with a few popular stocks
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    
    print("Extracting key metrics for test symbols...")
    print("=" * 60)
    
    for symbol in test_symbols:
        print(f"\nFetching data for {symbol}:")
        metrics = extractor.get_key_metrics(symbol)
        print(extractor.format_metrics_display(metrics))
        print("-" * 40)
    
    # Example: Get metrics for multiple stocks and save to JSON
    print("\nFetching metrics for multiple stocks...")
    all_metrics = extractor.get_multiple_stocks_metrics(['AAPL', 'MSFT'])
    
    # Save to JSON file
    extractor.save_metrics_to_json(all_metrics, 'stock_key_metrics.json')
    
    # Pretty print the results
    print("\nComplete results:")
    print(json.dumps(all_metrics, indent=2))
