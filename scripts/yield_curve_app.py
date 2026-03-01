"""
Treasury Yield Curve Visualizer - Enhanced with Tabs
====================================================
Interactive exploration with advanced analytics.

Run with:
    python -m streamlit run yield_curve_app_v3.py
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# Import curve reconstruction
from curve_reconstruction import reconstruct_curves

# Page configuration
st.set_page_config(
    page_title="Treasury Yield Curve Visualizer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# LOAD DATA
# ============================================================================

@st.cache_data
def load_npz_data(npz_path):
    """Load and cache NPZ data with bootstrap parameters"""
    data = np.load(npz_path, allow_pickle=True)
    
    dates = pd.to_datetime(data['dates'])
    
    result = {
        'dates': dates,
        'tenor_labels': data['tenor_labels'],
        'tenor_years': data['tenor_years'],
        'par_rates': data['par_rates_input'],
        'spot_rates': data['spot_rates_cc_T'],
        'discount_factors': data['discount_factors_T'],
        'forward_rates': data['forward_endpoint_T'],
        'method': str(data['method']),
        'r0': data['r0'],
        'r0_source': data['r0_source'],
    }
    
    # Load scheme-specific parameters
    if 's1_f' in data:
        result['s1_f'] = data['s1_f']
    if 's2_a' in data:
        result['s2_a'] = data['s2_a']
        result['s2_b'] = data['s2_b']
    if 's3_a' in data:
        result['s3_a'] = data['s3_a']
        result['s3_b'] = data['s3_b']
        result['s3_c'] = data['s3_c']
        result['s3_d'] = data['s3_d']
    
    return result

# ============================================================================
# PLOTTING FUNCTIONS - MAIN CURVES
# ============================================================================

def plot_yield_curves(data, date_idx, show_par=True, show_spot=True, show_forward=True):
    """Create yield curve plot with mathematically correct curves"""
    date = data['dates'][date_idx]
    T = data['tenor_years']
    tenors = data['tenor_labels']
    
    par = data['par_rates'][date_idx] * 100
    
    fig = go.Figure()
    
    # Par rates (linear interpolation - these are inputs)
    if show_par:
        fig.add_trace(go.Scatter(
            x=T, y=par,
            mode='lines+markers',
            name='Par Rates',
            line=dict(color='#2E86AB', width=3),
            marker=dict(size=8),
            hovertemplate='<b>%{text}</b><br>Par: %{y:.2f}%<extra></extra>',
            text=tenors
        ))
    
    # Reconstruct smooth curves from bootstrap parameters
    curves = reconstruct_curves(data, date_idx, num_points=1000)
    
    if curves is not None:
        # Spot rates - smooth exponential decay
        if show_spot:
            fig.add_trace(go.Scatter(
                x=curves['t_dense'],
                y=curves['spot_dense'] * 100,
                mode='lines',
                name='Spot (Zero) Rates',
                line=dict(color='#A23B72', width=2.5, dash='dash'),
                hovertemplate='Spot: %{y:.2f}%<extra></extra>',
            ))
            fig.add_trace(go.Scatter(
                x=curves['T_nodes'],
                y=curves['spot_nodes'] * 100,
                mode='markers',
                marker=dict(size=8, symbol='diamond', color='#A23B72'),
                hovertemplate='<b>%{text}</b><br>Spot: %{y:.2f}%<extra></extra>',
                text=tenors[np.isfinite(data['spot_rates'][date_idx])],
                showlegend=False
            ))
        
        # Forward rates - scheme-dependent shape
        if show_forward:
            fig.add_trace(go.Scatter(
                x=curves['t_dense'],
                y=curves['forward_dense'] * 100,
                mode='lines',
                name='Forward Rates',
                line=dict(color='#18A558', width=2, dash='dot'),
                hovertemplate='Forward: %{y:.2f}%<extra></extra>',
            ))
            fig.add_trace(go.Scatter(
                x=curves['T_nodes'],
                y=curves['forward_nodes'] * 100,
                mode='markers',
                marker=dict(size=6, symbol='square', color='#18A558'),
                hovertemplate='<b>%{text}</b><br>Fwd: %{y:.2f}%<extra></extra>',
                text=tenors[np.isfinite(data['forward_rates'][date_idx])],
                showlegend=False
            ))
    
    fig.update_layout(
        title=f'<b>Treasury Yield Curves - {date.strftime("%B %d, %Y")}</b><br>' +
              f'<sup>Bootstrap: {data["method"]} | r₀: {data["r0"][date_idx]*100:.2f}% ({data["r0_source"][date_idx]})</sup>',
        xaxis_title='<b>Maturity (years)</b>',
        yaxis_title='<b>Rate (%)</b>',
        template='plotly_white',
        height=500,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.12,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(255,255,255,0)',
            borderwidth=0
        )
    )
    
    return fig

def plot_discount_factors(data, date_idx):
    """Plot discount factors with smooth exponential decay"""
    date = data['dates'][date_idx]
    
    curves = reconstruct_curves(data, date_idx, num_points=1000)
    
    fig = go.Figure()
    
    if curves is not None:
        # Smooth discount curve
        fig.add_trace(go.Scatter(
            x=curves['t_dense'],
            y=curves['discount_dense'],
            mode='lines',
            line=dict(color='#6A4C93', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(106, 76, 147, 0.2)',
            hovertemplate='P(T): %{y:.6f}<extra></extra>',
        ))
        # Markers at tenor nodes
        tenors = data['tenor_labels']
        fig.add_trace(go.Scatter(
            x=curves['T_nodes'],
            y=curves['discount_nodes'],
            mode='markers',
            marker=dict(size=8, color='#6A4C93'),
            hovertemplate='<b>%{text}</b><br>P(T): %{y:.6f}<extra></extra>',
            text=tenors[np.isfinite(data['discount_factors'][date_idx])],
            showlegend=False
        ))
    
    fig.update_layout(
        title=f'<b>Discount Factors - {date.strftime("%B %d, %Y")}</b>',
        xaxis_title='<b>Maturity (years)</b>',
        yaxis_title='<b>P(T)</b>',
        template='plotly_white',
        height=350
    )
    
    return fig

def plot_spot_par_spread(data, date_idx):
    """Plot spot-par spread - clean bar chart"""
    date = data['dates'][date_idx]
    tenors = data['tenor_labels']
    par = data['par_rates'][date_idx] * 100
    spot = data['spot_rates'][date_idx] * 100
    spread_bp = (spot - par) * 100
    
    fig = go.Figure()
    mask = np.isfinite(spread_bp)
    
    # Simple bar chart with single color
    fig.add_trace(go.Bar(
        x=tenors[mask], 
        y=spread_bp[mask],
        marker=dict(
            color='#6A4C93',
            line=dict(color='#4A2C73', width=1)
        ),
        hovertemplate='<b>%{x}</b><br>Spread: %{y:.2f} bp<extra></extra>'
    ))
    
    fig.update_layout(
        title=f'<b>Spot-Par Spread - {date.strftime("%B %d, %Y")}</b>',
        xaxis_title='<b>Tenor</b>',
        yaxis_title='<b>Spread (basis points)</b>',
        template='plotly_white',
        height=350,
        yaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor='gray')
    )
    
    return fig

# ============================================================================
# PLOTTING FUNCTIONS - SPREAD ANALYSIS
# ============================================================================

def plot_spread_timeseries(data, tenor1_idx, tenor2_idx, rate_type='spot', date_range=None):
    """Plot spread between two tenors over time"""
    tenor1_name = data['tenor_labels'][tenor1_idx]
    tenor2_name = data['tenor_labels'][tenor2_idx]
    
    if rate_type == 'spot':
        rates1 = data['spot_rates'][:, tenor1_idx] * 100
        rates2 = data['spot_rates'][:, tenor2_idx] * 100
        ylabel = 'Spot Rate Spread (bp)'
        color = '#A23B72'
    elif rate_type == 'par':
        rates1 = data['par_rates'][:, tenor1_idx] * 100
        rates2 = data['par_rates'][:, tenor2_idx] * 100
        ylabel = 'Par Rate Spread (bp)'
        color = '#2E86AB'
    else:  # forward
        rates1 = data['forward_rates'][:, tenor1_idx] * 100
        rates2 = data['forward_rates'][:, tenor2_idx] * 100
        ylabel = 'Forward Rate Spread (bp)'
        color = '#18A558'
    
    spread_bp = (rates2 - rates1) * 100  # Convert to basis points
    
    # Apply date range filter
    dates = data['dates']
    if date_range:
        mask = (dates >= date_range[0]) & (dates <= date_range[1])
        dates = dates[mask]
        spread_bp = spread_bp[mask]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates, 
        y=spread_bp,
        mode='lines',
        line=dict(color=color, width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>Spread: %{y:.2f} bp<extra></extra>'
    ))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    fig.update_layout(
        title=f'<b>{tenor2_name} - {tenor1_name} Spread ({rate_type.capitalize()} Rates)</b>',
        xaxis_title='<b>Date</b>',
        yaxis_title=f'<b>{ylabel}</b>',
        template='plotly_white',
        height=400,
        xaxis_rangeslider_visible=True
    )
    
    return fig, spread_bp

def plot_spread_histogram(spread_bp, tenor1_name, tenor2_name, rate_type):
    """Plot histogram of spread distribution"""
    
    # Remove NaN values
    spread_clean = spread_bp[np.isfinite(spread_bp)]
    
    if len(spread_clean) == 0:
        return None
    
    fig = go.Figure()
    
    fig.add_trace(go.Histogram(
        x=spread_clean,
        nbinsx=50,
        marker=dict(
            color='#6A4C93',
            line=dict(color='#4A2C73', width=1)
        ),
        hovertemplate='Range: %{x:.1f} bp<br>Count: %{y}<extra></extra>'
    ))
    
    # Add statistics
    mean_spread = np.mean(spread_clean)
    std_spread = np.std(spread_clean)
    
    fig.add_vline(x=mean_spread, line_dash="dash", line_color="red", 
                  annotation_text=f"Mean: {mean_spread:.1f} bp")
    
    fig.update_layout(
        title=f'<b>Spread Distribution: {tenor2_name} - {tenor1_name}</b>',
        xaxis_title='<b>Spread (basis points)</b>',
        yaxis_title='<b>Frequency</b>',
        template='plotly_white',
        height=400,
        showlegend=False
    )
    
    return fig, mean_spread, std_spread

# ============================================================================
# PLOTTING FUNCTIONS - FORWARD PROJECTIONS
# ============================================================================

def compute_forward_rate_curve(data, date_idx, tenor_M_years, max_s=30.0, n_points=361):
    """
    Compute forward rate f(0, s, s+M) for various s
    
    Args:
        data: NPZ data dictionary
        date_idx: Date index
        tenor_M_years: Forward tenor M in years (e.g., 1.0 for 1Yr)
        max_s: Maximum forward start time (default 30 years)
        n_points: Number of points (default 361 for monthly)
    
    Returns:
        s_grid: Forward start times
        forward_rates: Forward rates f(0, s, s+M) in decimal
    """
    # Reconstruct instantaneous forward curve
    curves = reconstruct_curves(data, date_idx, num_points=2000)
    
    if curves is None:
        return None, None
    
    t_dense = curves['t_dense']
    f_dense = curves['forward_dense']
    
    # Create monthly grid for s (forward start times)
    s_grid = np.linspace(0, max_s, n_points)
    forward_rates = np.zeros(n_points)
    
    # Get last forward value for flat extrapolation
    f_last = f_dense[-1]
    t_max = t_dense[-1]
    
    for i, s in enumerate(s_grid):
        t_start = s
        t_end = s + tenor_M_years
        
        # Create dense integration grid for this interval
        n_integrate = max(100, int(tenor_M_years * 100))  # At least 100 points
        t_integrate = np.linspace(t_start, t_end, n_integrate)
        
        # Evaluate instantaneous forward at each point
        f_integrate = np.zeros(n_integrate)
        for j, t in enumerate(t_integrate):
            if t <= t_max:
                # Interpolate from reconstructed curve
                f_integrate[j] = np.interp(t, t_dense, f_dense)
            else:
                # Flat extrapolation beyond 30Y
                f_integrate[j] = f_last
        
        # Average using trapezoidal rule
        # f(0, s, s+M) = (1/M) * integral_s^(s+M) f(0, u) du
        integral = np.trapezoid(f_integrate, t_integrate)
        forward_rates[i] = integral / tenor_M_years
    
    return s_grid, forward_rates

def plot_forward_term_structure(data, date_idx, selected_tenors):
    """
    Plot forward rate term structure for multiple tenors
    
    Args:
        data: NPZ data dictionary
        date_idx: Date index
        selected_tenors: List of (label, years) tuples
    
    Returns:
        Plotly figure
    """
    date = data['dates'][date_idx]
    
    fig = go.Figure()
    
    # Color scheme for different tenors
    colors = ['#2E86AB', '#A23B72', '#18A558', '#F18F01', '#C73E1D', 
              '#6A4C93', '#1B998B', '#E63946']
    
    for idx, (label, tenor_years) in enumerate(selected_tenors):
        s_grid, forward_rates = compute_forward_rate_curve(
            data, date_idx, tenor_years, max_s=30.0, n_points=361
        )
        
        if s_grid is None:
            continue
        
        # Convert to percentage
        forward_rates_pct = forward_rates * 100
        
        # Determine valid range (where s+M <= some reasonable bound)
        # We allow extrapolation, so show full range
        
        color = colors[idx % len(colors)]
        
        fig.add_trace(go.Scatter(
            x=s_grid,
            y=forward_rates_pct,
            mode='lines',
            name=f'{label} Forward',
            line=dict(color=color, width=2.5),
            hovertemplate=f'Start: %{{x:.2f}}y<br>{label} Forward: %{{y:.2f}}%<extra></extra>'
        ))
    
    fig.update_layout(
        title=f'<b>Forward Rate Term Structure - {date.strftime("%B %d, %Y")}</b><br>' +
              '<sup>f(0, s, s+M) = Implied forward rate for M-tenor loan starting at time s</sup>',
        xaxis_title='<b>Forward Start Time s (years)</b>',
        yaxis_title='<b>Forward Rate f(0, s, s+M) (%)</b>',
        template='plotly_white',
        height=550,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="center",
            x=0.5
        )
    )
    
    # Add grid
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    
    return fig

def plot_forward_comparison_snapshot(data, date_idx, s_values=[0, 1, 5, 10, 20]):
    """
    Show forward rates at specific start times for different tenors
    
    Helps see the term structure at key forward start points
    """
    date = data['dates'][date_idx]
    
    # Tenors to compute
    tenor_map = {
        '1Mo': 1/12, '3Mo': 0.25, '6Mo': 0.5, '1Yr': 1.0,
        '2Yr': 2.0, '5Yr': 5.0, '10Yr': 10.0, '20Yr': 20.0, '30Yr': 30.0
    }
    
    fig = go.Figure()
    
    colors = ['#2E86AB', '#A23B72', '#18A558', '#F18F01', '#C73E1D']
    
    for idx, s in enumerate(s_values):
        rates = []
        tenors = []
        
        for label, tenor_years in tenor_map.items():
            s_grid, forward_rates = compute_forward_rate_curve(
                data, date_idx, tenor_years, max_s=30.0, n_points=361
            )
            
            if s_grid is None:
                continue
            
            # Find rate at this s value
            rate_at_s = np.interp(s, s_grid, forward_rates) * 100
            rates.append(rate_at_s)
            tenors.append(label)
        
        fig.add_trace(go.Scatter(
            x=tenors,
            y=rates,
            mode='lines+markers',
            name=f's = {s}Y',
            line=dict(color=colors[idx % len(colors)], width=2),
            marker=dict(size=8),
            hovertemplate=f's={s}Y<br>Tenor: %{{x}}<br>Rate: %{{y:.2f}}%<extra></extra>'
        ))
    
    fig.update_layout(
        title=f'<b>Forward Rates by Tenor - {date.strftime("%B %d, %Y")}</b><br>' +
              '<sup>Comparison at different forward start times</sup>',
        xaxis_title='<b>Forward Loan Tenor (M)</b>',
        yaxis_title='<b>Forward Rate (%)</b>',
        template='plotly_white',
        height=450,
        hovermode='x unified'
    )
    
    return fig

# ============================================================================
# DATA TABLE
# ============================================================================

def create_data_table(data, date_idx):
    """Create data table"""
    tenors = data['tenor_labels']
    T = data['tenor_years']
    par = data['par_rates'][date_idx] * 100
    spot = data['spot_rates'][date_idx] * 100
    discount = data['discount_factors'][date_idx]
    forward = data['forward_rates'][date_idx] * 100
    
    df = pd.DataFrame({
        'Tenor': tenors,
        'Maturity (yr)': T,
        'Par (%)': par,
        'Spot (%)': spot,
        'Discount': discount,
        'Forward (%)': forward,
        'Spot-Par (bp)': (spot - par) * 100
    })
    
    for col in ['Maturity (yr)', 'Par (%)', 'Spot (%)', 'Discount', 'Forward (%)', 'Spot-Par (bp)']:
        df[col] = df[col].apply(lambda x: f'{x:.4f}' if pd.notna(x) and np.isfinite(x) else 'N/A')
    
    return df

# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.title("📈 Treasury Yield Curve Visualizer")
    st.markdown("Interactive visualization with **mathematically correct** curve reconstruction")
    
    # Sidebar
    st.sidebar.header("⚙️ Configuration")
    
    # Find NPZ files in multiple locations
    npz_files = []
    
    # Check current directory
    npz_files.extend(list(Path('.').glob('*.npz')))
    
    # Check data/samples/ directory
    samples_dir = Path('data/samples')
    if samples_dir.exists():
        npz_files.extend(list(samples_dir.glob('*.npz')))
    
    # Check parent directory (if running from scripts/)
    parent_npz = list(Path('..').glob('*.npz'))
    if parent_npz:
        npz_files.extend(parent_npz)
    
    # Check ../data/samples/ (if running from scripts/)
    parent_samples = Path('../data/samples')
    if parent_samples.exists():
        npz_files.extend(list(parent_samples.glob('*.npz')))
    
    # Remove duplicates and sort
    npz_files = sorted(list(set(npz_files)))
    
    if not npz_files:
        st.error("No NPZ files found!")
        st.info("""
        **No bootstrap data found.** Please either:
        
        1. **Use sample data:** Clone the repo with sample files in `data/samples/`
        2. **Generate your own:** Run bootstrap with `--write-npz` flag
        
        See documentation for details.
        """)
        st.stop()
    
    selected_file = st.sidebar.selectbox(
        "Select NPZ file:",
        npz_files,
        format_func=lambda x: x.name
    )
    
    # Load data
    try:
        data = load_npz_data(str(selected_file))
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()
    
    st.sidebar.success(f"✓ {len(data['dates'])} dates loaded")
    st.sidebar.info(f"Method: {data['method']}")
    st.sidebar.markdown("---")
    
    # Date selection
    st.sidebar.header("📅 Date Selection")
    
    selected_date = st.sidebar.date_input(
        "Select date:",
        value=data['dates'][0].date(),
        min_value=data['dates'].min().date(),
        max_value=data['dates'].max().date()
    )
    
    target_date = pd.to_datetime(selected_date)
    date_idx = int(np.abs((data['dates'] - target_date).total_seconds()).argmin())
    
    date_idx_slider = st.sidebar.slider(
        "Or browse:",
        0, len(data['dates']) - 1,
        value=date_idx
    )
    date_idx = date_idx_slider
    
    st.sidebar.markdown("---")
    
    # Display options
    st.sidebar.header("📊 Display")
    show_par = st.sidebar.checkbox("Par Rates", value=True)
    show_spot = st.sidebar.checkbox("Spot Rates", value=True)
    show_forward = st.sidebar.checkbox("Forward Rates", value=True)
    
    # Main content with TABS
    st.markdown("---")
    
    # Header metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Date", data['dates'][date_idx].strftime("%Y-%m-%d"))
    with col2:
        st.metric("Short Rate", f"{data['r0'][date_idx]*100:.2f}%")
    with col3:
        st.metric("Source", data['r0_source'][date_idx])
    with col4:
        st.metric("Method", data['method'])
    
    # CREATE TABS
    tab1, tab2, tab3 = st.tabs([
        "📈 Yield Curves", 
        "📊 Spread Analysis", 
        "🎯 Forward Projections"
    ])
    
    # ========================================================================
    # TAB 1: YIELD CURVES
    # ========================================================================
    with tab1:
        # Main chart
        st.plotly_chart(
            plot_yield_curves(data, date_idx, show_par, show_spot, show_forward),
            use_container_width=True
        )
        
        # Two-column layout
        col1, col2 = st.columns(2)
        
        with col1:
            st.plotly_chart(plot_discount_factors(data, date_idx), use_container_width=True)
        
        with col2:
            st.plotly_chart(plot_spot_par_spread(data, date_idx), use_container_width=True)
        
        # Data table (collapsible)
        st.markdown("---")
        with st.expander("📋 View Data Table"):
            st.markdown("**Numerical data for selected date**")
            df = create_data_table(data, date_idx)
            st.dataframe(df, use_container_width=True, height=400)
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Download CSV",
                csv,
                f"yield_curve_{data['dates'][date_idx].strftime('%Y-%m-%d')}.csv",
                "text/csv"
            )
    
    # ========================================================================
    # TAB 2: SPREAD ANALYSIS
    # ========================================================================
    with tab2:
        st.subheader("Tenor Spread Analysis")
        st.markdown("Analyze the spread between any two tenors over time")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            tenor1_idx = st.selectbox(
                "Tenor 1 (subtract from):",
                range(len(data['tenor_labels'])),
                index=1,  # 2Yr default
                format_func=lambda i: data['tenor_labels'][i]
            )
        
        with col2:
            tenor2_idx = st.selectbox(
                "Tenor 2:",
                range(len(data['tenor_labels'])),
                index=12,  # 10Yr default
                format_func=lambda i: data['tenor_labels'][i]
            )
        
        with col3:
            rate_type = st.selectbox(
                "Rate Type:",
                ['spot', 'par', 'forward'],
                format_func=lambda x: x.capitalize()
            )
        
        # Date range filter
        st.markdown("**Date Range Filter:**")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date:",
                value=data['dates'].min().date()
            )
        with col2:
            end_date = st.date_input(
                "End Date:",
                value=data['dates'].max().date()
            )
        
        date_range = (pd.to_datetime(start_date), pd.to_datetime(end_date))
        
        # Plot spread time series
        fig_spread, spread_data = plot_spread_timeseries(
            data, tenor1_idx, tenor2_idx, rate_type, date_range
        )
        st.plotly_chart(fig_spread, use_container_width=True)
        
        # Plot histogram
        st.markdown("**Distribution Analysis:**")
        tenor1_name = data['tenor_labels'][tenor1_idx]
        tenor2_name = data['tenor_labels'][tenor2_idx]
        
        result = plot_spread_histogram(spread_data, tenor1_name, tenor2_name, rate_type)
        
        if result:
            fig_hist, mean_val, std_val = result
            
            col1, col2 = st.columns([2, 1])
            with col1:
                st.plotly_chart(fig_hist, use_container_width=True)
            with col2:
                st.markdown("**Statistics:**")
                st.metric("Mean Spread", f"{mean_val:.2f} bp")
                st.metric("Std Dev", f"{std_val:.2f} bp")
                st.metric("Current", f"{spread_data[-1]:.2f} bp" if len(spread_data) > 0 else "N/A")
    
    # ========================================================================
    # TAB 3: FORWARD PROJECTIONS
    # ========================================================================
    with tab3:
        st.subheader("Forward Rate Term Structure")
        st.markdown("""
        **Implied forward rates f(0, s, s+M):** What rate does the market expect for an M-tenor loan starting at time s?
        
        - **s** = Forward start time (x-axis)
        - **M** = Loan tenor (select below)
        - **f(0, s, s+M)** = Average of instantaneous forwards over [s, s+M]
        
        As M increases, curves become smoother (averaging over longer periods).
        """)
        
        # Tenor selection
        st.markdown("**Select Forward Tenors (M):**")
        
        col1, col2, col3 = st.columns(3)
        
        tenor_options = {
            '1 Mo': 1/12,
            '3 Mo': 0.25,
            '6 Mo': 0.5,
            '1 Yr': 1.0,
            '2 Yr': 2.0,
            '5 Yr': 5.0,
            '10 Yr': 10.0,
            '20 Yr': 20.0,
            '30 Yr': 30.0
        }
        
        selected_tenors = []
        
        with col1:
            if st.checkbox('1 Mo', value=True):
                selected_tenors.append(('1Mo', 1/12))
            if st.checkbox('3 Mo'):
                selected_tenors.append(('3Mo', 0.25))
            if st.checkbox('6 Mo'):
                selected_tenors.append(('6Mo', 0.5))
        
        with col2:
            if st.checkbox('1 Yr', value=True):
                selected_tenors.append(('1Yr', 1.0))
            if st.checkbox('2 Yr'):
                selected_tenors.append(('2Yr', 2.0))
            if st.checkbox('5 Yr', value=True):
                selected_tenors.append(('5Yr', 5.0))
        
        with col3:
            if st.checkbox('10 Yr'):
                selected_tenors.append(('10Yr', 10.0))
            if st.checkbox('20 Yr'):
                selected_tenors.append(('20Yr', 20.0))
            if st.checkbox('30 Yr'):
                selected_tenors.append(('30Yr', 30.0))
        
        if len(selected_tenors) == 0:
            st.warning("Please select at least one forward tenor")
        else:
            # Main forward term structure plot
            with st.spinner('Computing forward rate curves...'):
                fig_fwd_structure = plot_forward_term_structure(data, date_idx, selected_tenors)
                st.plotly_chart(fig_fwd_structure, use_container_width=True)
            
            # Additional snapshot view (optional)
            st.markdown("---")
            if st.checkbox("Show cross-section view", value=False):
                st.markdown("**Cross-Section View:** Forward rates at specific start times")
                fig_snapshot = plot_forward_comparison_snapshot(data, date_idx, s_values=[0, 1, 5, 10, 20])
                st.plotly_chart(fig_snapshot, use_container_width=True)
        
        # Interpretation guide
        st.markdown("---")
        st.markdown("**💡 Interpretation:**")
        st.info("""
        - **Flat extrapolation:** For s+M > 30Y, assumes forward rates = f(0, 30Y)
        - **Scheme 1 (Piecewise Constant):** 1Mo forward ≈ instantaneous (jagged), 30Yr forward very smooth
        - **Scheme 3 (Monotone Cubic):** All curves smooth, but still get duller with larger M
        - **Upward sloping:** Market expects rates to rise in the future
        - **Downward sloping:** Market expects rates to fall
        """)
        
        # Technical note
        with st.expander("📐 Technical Details"):
            st.markdown("""
            **Forward Rate Formula:**
            
            f(0, s, s+M) = (1/M) × ∫ₛˢ⁺ᴹ f(0, u) du
            
            Where:
            - f(0, u) = Instantaneous forward rate at time u (from bootstrap)
            - Integration uses trapezoidal rule
            - For u > 30Y: f(0, u) = f(0, 30Y) (flat extrapolation)
            
            **Computational Grid:**
            - s: Monthly grid from 0 to 30 years (361 points)
            - Each f(0, s, s+M) computed by averaging ~100+ instantaneous forward points
            
            **Why curves smooth with larger M:**
            - Larger M → averaging over more years
            - High-frequency components in f(0, t) get averaged out
            - 30Y forward ≈ average of entire forward curve (very smooth)
            """)
    
if __name__ == "__main__":
    main()
