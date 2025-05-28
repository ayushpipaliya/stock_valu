import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
from typing import Dict, Any, Optional
import re
import time
from urllib.parse import quote
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from get_data import YahooKeyMetricsExtractor

# Set page config
st.set_page_config(
    page_title="Stock Valuation Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)


def calculate_additional_metrics(metrics):
    """Calculate additional financial metrics"""
    additional_metrics = {}
    
    # PEG Ratio (PE / Growth Rate)
    if metrics.get('pe_ratio_ttm') and metrics.get('growth_estimate_next_year'):
        if metrics['growth_estimate_next_year'] != 0:
            additional_metrics['peg_ratio'] = metrics['pe_ratio_ttm'] / metrics['growth_estimate_next_year']
    
    # Dividend Coverage Ratio (simplified estimation)
    if metrics.get('forward_dividend_rate') and metrics.get('current_price') and metrics.get('pe_ratio_ttm'):
        eps = metrics['current_price'] / metrics['pe_ratio_ttm'] if metrics['pe_ratio_ttm'] != 0 else None
        if eps:
            additional_metrics['estimated_eps'] = eps
            if metrics['forward_dividend_rate'] != 0:
                additional_metrics['dividend_coverage_ratio'] = eps / metrics['forward_dividend_rate']
    
    # Price to Book approximation (simplified)
    if metrics.get('pe_ratio_ttm') and metrics.get('growth_estimate_next_year'):
        # Rough estimation: PB = PE * ROE, assuming ROE relates to growth
        estimated_roe = metrics['growth_estimate_next_year'] / 100 if metrics['growth_estimate_next_year'] else 0.1
        additional_metrics['estimated_pb_ratio'] = metrics['pe_ratio_ttm'] * estimated_roe
    
    return additional_metrics

def calculate_valuation_metrics(current_price, pe_ratio, growth_rate, dividend_yield):
    """Calculate various valuation metrics"""
    valuations = {}
    
    if all([current_price, pe_ratio, growth_rate is not None, dividend_yield is not None]):
        # PEG-based valuation
        if growth_rate != 0:
            fair_pe = growth_rate  # Simple PEG = 1 assumption
            valuations['peg_based_fair_value'] = (current_price / pe_ratio) * fair_pe
        
        # Dividend Growth Model (simplified)
        if dividend_yield > 0:
            dividend_per_share = current_price * (dividend_yield / 100)
            # Assuming required return of 10%
            required_return = 0.10
            growth_rate_decimal = growth_rate / 100 if growth_rate else 0.05
            if required_return > growth_rate_decimal:
                valuations['dividend_growth_fair_value'] = dividend_per_share * (1 + growth_rate_decimal) / (required_return - growth_rate_decimal)
        
        # Combined valuation score
        peg_value = (growth_rate + dividend_yield) / pe_ratio if pe_ratio != 0 else 0
        valuations['valuation_score'] = peg_value
        
        if peg_value < 1:
            valuations['valuation_status'] = "🚩 Overvalued"
        elif 1 <= peg_value <= 1.5:
            valuations['valuation_status'] = "✅ Fairly Valued"
        elif 1.5 < peg_value <= 2:
            valuations['valuation_status'] = "📈 Neutral"
        else:
            valuations['valuation_status'] = "📈 Undervalued"
    
    return valuations

def create_valuation_chart(current_price, fair_values):
    """Create a valuation comparison chart"""
    fig = go.Figure()
    
    # Current price bar
    fig.add_trace(go.Bar(
        x=['Current Price'],
        y=[current_price],
        name='Current Price',
        marker_color='#ff6b6b'
    ))
    
    # Fair value bars
    colors = ['#4ecdc4', '#45b7d1', '#96ceb4', '#feca57']
    for i, (method, value) in enumerate(fair_values.items()):
        if value and value > 0:
            fig.add_trace(go.Bar(
                x=[method.replace('_', ' ').title()],
                y=[value],
                name=method.replace('_', ' ').title(),
                marker_color=colors[i % len(colors)]
            ))
    
    fig.update_layout(
        title='Stock Valuation Comparison',
        xaxis_title='Valuation Methods',
        yaxis_title='Price ($)',
        template='plotly_dark',
        showlegend=True
    )
    
    return fig

def create_metrics_radar_chart(metrics):
    """Create a radar chart for key metrics"""
    # Normalize metrics for radar chart
    categories = []
    values = []
    
    if metrics.get('pe_ratio_ttm'):
        categories.append('P/E Ratio<br>(Lower is Better)')
        # Normalize PE ratio (inverse scale, 0-40 range)
        pe_normalized = max(0, min(100, 100 - (metrics['pe_ratio_ttm'] * 2.5)))
        values.append(pe_normalized)
    
    if metrics.get('growth_estimate_next_year'):
        categories.append('Growth Rate<br>(Higher is Better)')
        # Normalize growth rate (0-30% range)
        growth_normalized = max(0, min(100, metrics['growth_estimate_next_year'] * 3.33))
        values.append(growth_normalized)
    
    if metrics.get('forward_dividend_yield'):
        categories.append('Dividend Yield<br>(Higher is Better)')
        # Normalize dividend yield (0-10% range)
        div_normalized = max(0, min(100, metrics['forward_dividend_yield'] * 10))
        values.append(div_normalized)
    
    # Add PEG ratio if available
    additional_metrics = calculate_additional_metrics(metrics)
    if additional_metrics.get('peg_ratio'):
        categories.append('PEG Ratio<br>(Lower is Better)')
        # Normalize PEG ratio (inverse scale, 0-3 range)
        peg_normalized = max(0, min(100, 100 - (additional_metrics['peg_ratio'] * 33.33)))
        values.append(peg_normalized)
    
    if len(categories) >= 3:  # Only create radar chart if we have enough data
        fig = go.Figure()
        
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name='Stock Metrics',
            line_color='#4ecdc4'
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )),
            showlegend=True,
            title="Stock Performance Radar",
            template='plotly_dark'
        )
        
        return fig
    
    return None

# Streamlit App
def main():
    # Title and description
    st.title("📈 Stock Valuation Analyzer")
    
    # Sidebar for input
    with st.sidebar:
        st.header("🔍 Stock Analysis")
        
        # Stock symbol input
        stock_symbol = st.text_input(
            "Enter Stock Symbol:",
            value="AAPL",
            help="Enter a valid stock ticker symbol (e.g., AAPL, MSFT, GOOGL)"
        ).upper()
        
        # Analysis button
        analyze_button = st.button("🚀 Analyze Stock", type="primary")
        
        st.markdown("---")
        st.markdown("**💡 How it works:**")
        st.markdown("• Fetches real-time data from Yahoo Finance")
        st.markdown("• Calculates multiple valuation metrics")
        st.markdown("• Provides comprehensive analysis")
    
    # Main content area
    if analyze_button and stock_symbol:
        # Show loading spinner
        with st.spinner(f'Analyzing {stock_symbol}... Please wait.'):
            # Initialize extractor and get metrics
            extractor = YahooKeyMetricsExtractor()
            metrics = extractor.get_key_metrics(stock_symbol)
        
        if metrics.get('error'):
            st.error(f"❌ Error: {metrics['error']}")
            return
        
        # Display basic stock info
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label="💰 Current Price",
                value=f"${metrics['current_price']:.2f}" if metrics['current_price'] else "N/A"
            )
        
        with col2:
            st.metric(
                label="📊 P/E Ratio (TTM)",
                value=f"{metrics['pe_ratio_ttm']:.2f}" if metrics['pe_ratio_ttm'] else "N/A"
            )
        
        with col3:
            st.metric(
                label="📈 Growth Est. (%)",
                value=f"{metrics['growth_estimate_next_year']:.2f}%" if metrics['growth_estimate_next_year'] else "N/A"
            )
        
        # Second row of metrics
        col4, col5, col6 = st.columns(3)
        
        with col4:
            st.metric(
                label="💎 Dividend Rate",
                value=f"${metrics['forward_dividend_rate']:.2f}" if metrics['forward_dividend_rate'] else "N/A"
            )
        
        with col5:
            st.metric(
                label="🎯 Dividend Yield",
                value=f"{metrics['forward_dividend_yield']:.2f}%" if metrics['forward_dividend_yield'] else "N/A"
            )
        
        # Calculate additional metrics
        additional_metrics = calculate_additional_metrics(metrics)
        
        with col6:
            if additional_metrics.get('peg_ratio'):
                st.metric(
                    label="⚡ PEG Ratio",
                    value=f"{additional_metrics['peg_ratio']:.2f}"
                )
            else:
                st.metric(label="⚡ PEG Ratio", value="N/A")
        
        st.markdown("---")
        
        # Valuation Analysis
        st.header("🎯 Valuation Analysis")
        
        if all([metrics['current_price'], metrics['pe_ratio_ttm'], 
                metrics['growth_estimate_next_year'] is not None, 
                metrics['forward_dividend_yield'] is not None]):
            
            # Calculate valuation metrics
            valuations = calculate_valuation_metrics(
                metrics['current_price'],
                metrics['pe_ratio_ttm'],
                metrics['growth_estimate_next_year'],
                metrics['forward_dividend_yield']
            )
            
            # Display valuation score and status
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    label="🔢 Valuation Score",
                    value=f"{valuations['valuation_score']:.2f}",
                    help="(Growth Rate + Dividend Yield) / PE Ratio"
                )
            
            with col2:
                st.markdown(f"### {valuations['valuation_status']}")
            
            # Fair value estimations
            st.subheader("💡 Fair Value Estimations")
            
            fair_values = {}
            if valuations.get('peg_based_fair_value'):
                fair_values['PEG Based'] = valuations['peg_based_fair_value']
            if valuations.get('dividend_growth_fair_value'):
                fair_values['Dividend Growth'] = valuations['dividend_growth_fair_value']
            
            if fair_values:
                # Create valuation chart
                fig = create_valuation_chart(metrics['current_price'], fair_values)
                st.plotly_chart(fig, use_container_width=True)
                
                # Show fair values in columns
                cols = st.columns(len(fair_values) + 1)
                
                with cols[0]:
                    st.metric("Current Price", f"${metrics['current_price']:.2f}")
                
                for i, (method, value) in enumerate(fair_values.items()):
                    with cols[i + 1]:
                        delta = value - metrics['current_price']
                        delta_pct = (delta / metrics['current_price']) * 100
                        st.metric(
                            f"{method} Fair Value",
                            f"${value:.2f}",
                            f"{delta_pct:+.1f}%"
                        )
            
        else:
            st.warning("⚠️ Insufficient data for complete valuation analysis")
        
        st.markdown("---")
        
        # Additional Financial Metrics
        st.header("📊 Additional Financial Metrics")
        
        # Create metrics dataframe
        metrics_data = []
        
        if additional_metrics.get('estimated_eps'):
            metrics_data.append({"Metric": "Estimated EPS", "Value": f"${additional_metrics['estimated_eps']:.2f}"})
        
        if additional_metrics.get('dividend_coverage_ratio'):
            metrics_data.append({"Metric": "Dividend Coverage Ratio", "Value": f"{additional_metrics['dividend_coverage_ratio']:.2f}x"})
        
        if additional_metrics.get('estimated_pb_ratio'):
            metrics_data.append({"Metric": "Estimated P/B Ratio", "Value": f"{additional_metrics['estimated_pb_ratio']:.2f}"})
        
        # Market cap estimation (simplified)
        if metrics['current_price'] and additional_metrics.get('estimated_eps'):
            shares_outstanding_est = 1000000000  # Rough estimation
            market_cap_est = metrics['current_price'] * shares_outstanding_est / 1000000000
            metrics_data.append({"Metric": "Est. Market Cap", "Value": f"${market_cap_est:.1f}B"})
        
        if metrics_data:
            df = pd.DataFrame(metrics_data)
            st.dataframe(df, use_container_width=True)
        
        # Radar chart
        radar_fig = create_metrics_radar_chart(metrics)
        if radar_fig:
            st.subheader("🎯 Performance Radar Chart")
            st.plotly_chart(radar_fig, use_container_width=True)
        
        st.markdown("---")
        
        # Investment Insights
        st.header("💡 Investment Insights")
        
        insights = []
        
        # PE Ratio insights
        if metrics.get('pe_ratio_ttm'):
            if metrics['pe_ratio_ttm'] < 15:
                insights.append("✅ **Low P/E Ratio**: Stock appears undervalued based on earnings")
            elif metrics['pe_ratio_ttm'] > 25:
                insights.append("⚠️ **High P/E Ratio**: Stock may be overvalued or high-growth")
            else:
                insights.append("📊 **Moderate P/E Ratio**: Reasonable valuation based on earnings")
        
        # Growth insights
        if metrics.get('growth_estimate_next_year'):
            if metrics['growth_estimate_next_year'] > 15:
                insights.append("🚀 **High Growth Expected**: Strong growth estimates for next year")
            elif metrics['growth_estimate_next_year'] < 5:
                insights.append("⚠️ **Low Growth Expected**: Limited growth potential")
        
        # Dividend insights
        if metrics.get('forward_dividend_yield'):
            if metrics['forward_dividend_yield'] > 4:
                insights.append("💰 **High Dividend Yield**: Good income-generating potential")
            elif metrics['forward_dividend_yield'] < 2:
                insights.append("📈 **Low Dividend Yield**: Growth-focused rather than income")
        
        # PEG insights
        if additional_metrics.get('peg_ratio'):
            if additional_metrics['peg_ratio'] < 1:
                insights.append("⭐ **Attractive PEG Ratio**: Growth appears reasonably priced")
            elif additional_metrics['peg_ratio'] > 2:
                insights.append("⚠️ **High PEG Ratio**: Growth may be overpriced")
        
        for insight in insights:
            st.markdown(insight)
        
        if not insights:
            st.info("📝 Insufficient data for detailed insights")
        
        # Raw data expander
        with st.expander("🔍 View Raw Data"):
            st.json({**metrics, **additional_metrics})
        
        # Disclaimer
        st.markdown("---")
        st.caption("⚠️ **Disclaimer**: This analysis is for informational purposes only and should not be considered as financial advice. Always do your own research and consult with financial professionals before making investment decisions.")

if __name__ == "__main__":
    main()
