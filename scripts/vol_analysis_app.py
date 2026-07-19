"""
vol_analysis_app.py
===================
Streamlit app: Forward Rate Volatility Analysis — Tabs 1 & 2

Run from repo root:
    python -m streamlit run scripts/vol_analysis_app.py

Requires: numpy, scipy, plotly, streamlit
"""

import os, sys, datetime
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import vol_analysis as va

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Forward Rate Volatility",
    page_icon="📈",
    layout="wide",
)
st.title("Forward Rate Volatility Analysis")
st.caption(
    "Span-weighted PCA and t_ν tail-distribution fitting on S1 "
    "instantaneous forward rates. CMTRateBootstrap."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Data")

# Initialise selected path in session state
if 'npz_path_selected' not in st.session_state:
    st.session_state['npz_path_selected'] = ''

def _browse_for_npz():
    """
    Open the native OS file picker and store the result in session state.

    Windows : tkinter.filedialog  (reliable, main-thread-safe via Streamlit)
    macOS   : osascript / AppleScript  (avoids tkinter threading restrictions)
    Linux   : tkinter with graceful fallback to manual text input
    """
    import platform
    system = platform.system()
    selected = ''

    try:
        if system == 'Darwin':
            # AppleScript runs out-of-process — no threading restrictions
            import subprocess
            script = (
                'POSIX path of (choose file '
                'with prompt "Select S1 bootstrap NPZ file:" '
                'of type {"npz", "public.data"})'
            )
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                selected = result.stdout.strip()

        else:
            # Windows (and Linux fallback)
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            if system == 'Windows':
                root.wm_attributes('-topmost', 1)
            initial = (os.path.dirname(st.session_state['npz_path_selected'])
                       if st.session_state['npz_path_selected']
                       else os.path.expanduser('~'))
            selected = filedialog.askopenfilename(
                title="Select S1 bootstrap NPZ file",
                filetypes=[("NumPy archive", "*.npz"), ("All files", "*.*")],
                initialdir=initial,
            )
            root.destroy()

        if selected:
            st.session_state['npz_path_selected'] = os.path.normpath(selected)

    except Exception as e:
        st.session_state['_browse_error'] = str(e)

# Browse button + path display in same row
_col_path, _col_btn = st.sidebar.columns([5, 1])
_col_btn.button("📂", on_click=_browse_for_npz,
                help="Open file browser to select an NPZ file.")
if '_browse_error' in st.session_state:
    st.sidebar.caption(f"⚠ {st.session_state.pop('_browse_error')}")

npz_path = _col_path.text_input(
    "NPZ file",
    value=st.session_state['npz_path_selected'],
    label_visibility="collapsed",
    placeholder="Click 📂 to browse…",
)
# Sync manual edits back to session state
if npz_path != st.session_state['npz_path_selected']:
    st.session_state['npz_path_selected'] = npz_path

st.sidebar.header("Settings")
var_threshold = st.sidebar.selectbox(
    "Variance threshold",
    options=[0.90, 0.95, 0.99], index=1,
    format_func=lambda x: f"{int(x*100)}%",
    help="Minimum cumulative variance for PC count display.",
)

# ── Validate path ─────────────────────────────────────────────────────────────
if not os.path.exists(npz_path):
    st.error(
        f"File not found: `{npz_path}`  \n"
        "Update the path in the sidebar."
    )
    st.stop()

# ── Date range ────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading panel…")
def _get_date_bounds(path: str):
    p = va.load_vol_panel(path)
    d_min = p.dates[-1].astype('datetime64[D]').astype(datetime.date)
    d_max = p.dates[0].astype('datetime64[D]').astype(datetime.date)
    return d_min, d_max

d_min, d_max = _get_date_bounds(npz_path)

st.sidebar.header("Date range")
date_start, date_end = st.sidebar.date_input(
    "Select range",
    value=(d_min, d_max),
    min_value=d_min, max_value=d_max,
)
if date_start >= date_end:
    st.sidebar.error("Start must be before end.")
    st.stop()

# ── Core computation (single cache entry) ─────────────────────────────────────
# Bundle load + filter + PCA + both fits into one cache call.
# Cache key: (path, date_start, date_end).
# Clear with: st.cache_data.clear() or restart Streamlit.
@st.cache_data(show_spinner="Computing PCA and tail fits…")
def _compute(path: str, ds: str, de: str):
    """
    Returns (panel, pca, fits) where
      panel : VolPanel
      pca   : PCAResult
      fits  : BothFits  — k5 (QQ) and k14 (MLE)
    """
    panel_full = va.load_vol_panel(path)
    panel = va.filter_panel(
        panel_full,
        np.datetime64(ds),
        np.datetime64(de),
    )
    pca  = va.weighted_pca(panel)
    fits = va.fit_both(panel, pca)
    return panel, pca, fits

try:
    panel, pca, fits = _compute(npz_path, str(date_start), str(date_end))
except ValueError as e:
    st.error(str(e))
    st.stop()

labels  = panel.tenor_labels
n_obs   = panel.delta_f.shape[0]
n_pcs   = va.pcs_for_threshold(pca, var_threshold)

st.sidebar.markdown(f"**{n_obs:,}** observations in range")

# ── Shared Plotly style ───────────────────────────────────────────────────────
_LAYOUT = dict(
    template="plotly_white",
    font=dict(family="system-ui, sans-serif", size=12),
    margin=dict(l=60, r=20, t=40, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1),
)
C = dict(blue='#185FA5', orange='#D85A30', green='#1D9E75',
         purple='#7F77DD', amber='#F0A500', red='#E05555', grey='#888780')


# ═════════════════════════════════════════════════════════════════════════════
# TABS
# ═════════════════════════════════════════════════════════════════════════════
tab1, tab2 = st.tabs(["📊 PCA", "📈 Tail Distribution"])


# ── TAB 1: PCA ────────────────────────────────────────────────────────────────
with tab1:

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PC1 variance", f"{pca.var_share[0]*100:.1f}%")
    c2.metric(f"PCs for {int(var_threshold*100)}%", str(n_pcs))
    c3.metric("Observations", f"{n_obs:,}")
    c4.metric("Tenor points", "14")

    st.divider()

    # Waterfall scree plot
    # Each bar runs from previous cumulative total to the new one,
    # so bar tops ARE the cumulative variance — no second axis needed.
    st.subheader("Variance explained by PC (waterfall)")
    pc_x    = [f"PC{i+1}" for i in range(14)]
    var_pct = pca.var_share * 100   # incremental values
    cum_pct = pca.cum_var   * 100   # bar tops

    # Colour: blue up to the threshold PC, grey beyond
    bar_colours = [C['blue'] if i < n_pcs else C['grey'] for i in range(14)]

    # Simulate waterfall with go.Bar + base: each bar's bottom = previous
    # cumulative total, so bar tops ARE the running cumulative percentage.
    import numpy as _np
    bases = _np.concatenate([[0.0], cum_pct[:-1]]).tolist()

    fig_scree = go.Figure(go.Bar(
        x=pc_x,
        y=var_pct.tolist(),
        base=bases,
        marker_color=bar_colours,
        marker_line_width=0,
        text=[f"{v:.1f}%" for v in var_pct],
        textposition="outside",
        textfont=dict(size=10),
    ))

    # Threshold line — intersects at the cumulative total of the n_pcs-th PC
    fig_scree.add_hline(
        y=var_threshold * 100,
        line_dash="dot", line_color=C['grey'], line_width=1.5,
        annotation_text=f"{int(var_threshold*100)}%  ({n_pcs} PCs)",
        annotation_position="right",
        annotation_font=dict(size=11, color=C['grey']),
    )

    fig_scree.update_layout(
        **_LAYOUT,
        yaxis=dict(title="Cumulative variance (%)", range=[0, 108],
                   ticksuffix="%"),
        showlegend=False,
        height=360,
    )
    st.plotly_chart(fig_scree, use_container_width=True)

    # PC loadings
    st.subheader("PC loadings (original rate space)")
    pc_opts = [f"PC{i+1} ({pca.var_share[i]*100:.1f}%)" for i in range(8)]
    sel_pcs = st.multiselect("Select PCs", options=pc_opts,
                              default=pc_opts[:4])
    sel_idx = [int(s.split("PC")[1].split(" ")[0]) - 1 for s in sel_pcs]
    pal     = list(C.values())

    fig_load = go.Figure()
    for rank, idx in enumerate(sel_idx):
        fig_load.add_scatter(
            x=labels, y=pca.eigenvectors_original[:, idx],
            mode="lines+markers",
            name=f"PC{idx+1} ({pca.var_share[idx]*100:.1f}%)",
            line=dict(color=pal[rank % len(pal)], width=2),
            marker=dict(size=6),
        )
    fig_load.add_hline(y=0, line_dash="dot",
                       line_color=C['grey'], line_width=1)
    fig_load.update_layout(**_LAYOUT, yaxis_title="Loading",
                           xaxis_title="Tenor", height=340)
    st.plotly_chart(fig_load, use_container_width=True)

    with st.expander("Variance explained table"):
        import pandas as pd
        st.dataframe(pd.DataFrame({
            "PC":           [f"PC{i+1}" for i in range(14)],
            "Eigenvalue":   [f"{v:.6e}" for v in pca.eigenvalues],
            "Variance %":   [f"{v*100:.3f}%" for v in pca.var_share],
            "Cumulative %": [f"{v*100:.3f}%" for v in pca.cum_var],
        }), use_container_width=True, hide_index=True)




# ── TAB 2: TAIL DISTRIBUTION & ALCO SCENARIOS ─────────────────────────────────
with tab2:

    # ── Precompute presets (cheap — 7 × d² evaluations) ───────────────────────
    import pandas as pd
    presets = va.compute_presets(panel, pca)

    # ── Session state: slider values initialised to Parallel +100bp ───────────
    SLIDER_KEYS  = ['s_3mo', 's_5yr', 's_10yr', 's_20yr', 's_30yr']
    SLIDER_LBLS  = ['3Mo',   '5Yr',   '10Yr',   '20Yr',   '30Yr']
    SLIDER_RANGE = (-400, 400)

    def _init_sliders(bps: np.ndarray):
        for key, val in zip(SLIDER_KEYS, bps):
            st.session_state[key] = float(round(val, 1))

    if SLIDER_KEYS[0] not in st.session_state:
        _init_sliders(presets['Parallel +100bp']['anchor_bps_Q'])

    def _apply_preset(name):
        _init_sliders(presets[name]['anchor_bps_Q'])

    # ── Fit summary cards ──────────────────────────────────────────────────────
    st.subheader("Tail fit summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("k=5  ν* (QQ)", f"{fits.k5.nu:.2f}",
              help="Corrected QQ slope. Through-origin slope = 1.000. "
                   "Preferred for reduced-rank (escaping variance in PC6-14 "
                   "contaminates the MLE).")
    c2.metric("k=5  c = (ν-2)/ν", f"{fits.k5.c:.4f}")
    c3.metric("k=14 ν* (MLE)", f"{fits.k14.nu:.2f}",
              help="Corrected MLE. Full-rank, consistent with par-rate ν (~3.27). "
                   "No escaped-variance contamination.")
    c4.metric("k=14 c = (ν-2)/ν", f"{fits.k14.c:.4f}")

    st.divider()

    # ── QQ plots ──────────────────────────────────────────────────────────────
    st.subheader("QQ plots — d² vs corrected F(k, ν) quantiles")
    col_left, col_right = st.columns(2)

    def _make_qq(tail: va.TailFit, color: str, label: str):
        from scipy import stats as _stats
        d2_s  = tail.d2_sorted
        p_    = tail.p_emp
        step  = max(1, len(p_) // 1500)
        p_vis = p_[::step]
        d2_vis= d2_s[::step]
        q_vis = tail.c * tail.k * _stats.f.ppf(p_vis, dfn=tail.k, dfd=tail.nu)
        mask  = p_vis <= 0.999
        q_vis, d2_vis = q_vis[mask], d2_vis[mask]
        xy_max = float(np.percentile(d2_s, 99.5))
        fig = go.Figure()
        fig.add_scatter(x=[0, xy_max], y=[0, xy_max], mode="lines",
                        name="y = x", line=dict(color='grey', dash='dash', width=1.5))
        fig.add_scatter(x=q_vis, y=d2_vis, mode="markers", name=label,
                        marker=dict(color=color, size=3, opacity=0.5))
        fig.update_layout(**_LAYOUT,
                          title=dict(text=label, font=dict(size=12)),
                          xaxis=dict(title="Theoretical (log)", type="log"),
                          yaxis=dict(title="Empirical d² (log)", type="log"),
                          height=300)
        return fig

    with col_left:
        st.plotly_chart(_make_qq(fits.k5,  C['blue'],
                                 f"k=5 QQ   ν={fits.k5.nu:.2f}  "
                                 f"slope={fits.k5.slope_origin:.4f}"),
                        use_container_width=True)
    with col_right:
        st.plotly_chart(_make_qq(fits.k14, C['orange'],
                                 f"k=14 MLE  ν={fits.k14.nu:.2f}  "
                                 f"slope={fits.k14.slope_origin:.4f}"),
                        use_container_width=True)

    st.divider()

    # ── ALCO SCENARIO GENERATOR ────────────────────────────────────────────────
    st.subheader("ALCO scenario generator")

    _PRESET_NAMES = list(presets.keys())
    _ICONS = {
        'Parallel +100bp': '↕',
        'Bear Steepen':    '↗',
        'Bull Steepen':    '↘',
        'Bear Flatten':    '↙',
        'Bull Flatten':    '↖',
        'Bell':            '∩',
        'Bowl':            '∪',
    }

    # Read current anchor values from session state BEFORE rendering UI so the
    # chart always sits above the sliders and still reflects current state.
    L5 = va.build_interp_matrix(va.ANCHOR_LABELS, panel.tenor_labels,
                                  panel.tenor_years)
    anchor_arr = np.array([st.session_state.get(k, 100.0) for k in SLIDER_KEYS])
    full_bps_Q = va.anchor_bps_to_full(anchor_arr, L5)
    d2_scen    = va.scenario_d2(anchor_arr, L5, pca, panel)
    sev_k14    = va.scenario_severity(d2_scen, fits.k14)
    sev_k5     = va.scenario_severity(d2_scen, fits.k5)

    # ── Row 1: preset buttons (left) + severity score (right) ─────────────────
    col_btns, col_sev = st.columns([6, 1])
    with col_btns:
        btn_cols = st.columns(len(_PRESET_NAMES))
        for col, name in zip(btn_cols, _PRESET_NAMES):
            col.button(
                f"{_ICONS.get(name, '')} {name}",
                key=f"btn_{name.replace(' ', '_')}",
                on_click=_apply_preset,
                args=(name,),
                use_container_width=True,
            )
    with col_sev:
        sev_colour = (C['red']   if sev_k14 > 0.95
                      else C['amber'] if sev_k14 > 0.80
                      else C['green'])
        st.markdown(
            f"<div style='text-align:center;padding-top:2px'>"
            f"<div style='font-size:10px;color:#888;font-family:monospace;"
            f"text-transform:uppercase;letter-spacing:.06em'>Severity k=14</div>"
            f"<div style='font-size:38px;font-weight:300;line-height:1.1;"
            f"color:{sev_colour}'>{sev_k14*100:.1f}%</div>"
            f"<div style='font-size:10px;color:#888;font-family:monospace'>"
            f"k=5 → {sev_k5*100:.1f}%</div>"
            f"<div style='font-size:10px;color:#555;font-family:monospace'>"
            f"d²={d2_scen:.3f}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Row 2: full-width bar chart ────────────────────────────────────────────
    # Orange = anchor tenors (slider-controlled)
    # Gray   = interpolated tenors (derived by linear interpolation)
    is_anchor   = [lbl in va.ANCHOR_LABELS for lbl in panel.tenor_labels]
    bar_colours = [C['orange'] if a else '#555555' for a in is_anchor]

    fig_alco = go.Figure()
    fig_alco.add_bar(
        x=panel.tenor_labels,
        y=full_bps_Q.tolist(),
        marker_color=bar_colours,
        marker_line_width=0,
        text=[f"{v:+.0f}" if a else "" for v, a in zip(full_bps_Q, is_anchor)],
        textposition="outside",
        textfont=dict(size=10, color='rgba(255,255,255,0.7)'),
    )
    fig_alco.add_hline(y=0, line_color='rgba(255,255,255,0.15)', line_width=1)
    fig_alco.update_layout(
        **{**_LAYOUT, 'margin': dict(l=60, r=20, t=44, b=36)},
        yaxis_title="bp / quarter",
        xaxis_title=None,
        height=320,
        showlegend=False,
    )
    # Manual legend annotation
    fig_alco.add_annotation(
        x=0, y=1.10, xref='paper', yref='paper',
        text=(f'<span style="color:{C["orange"]}">&#9646;</span> anchor (controlled) '
              f'&nbsp;&nbsp;<span style="color:#555">&#9646;</span> interpolated'),
        showarrow=False, font=dict(size=11), align='left',
    )
    st.plotly_chart(fig_alco, use_container_width=True)

    # ── Row 3: five anchor sliders in a horizontal row ─────────────────────────
    st.markdown(
        "<div style='font-size:11px;color:#888;font-family:monospace;"
        "text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px'>"
        "Anchor controls — bp / quarter</div>",
        unsafe_allow_html=True,
    )
    slider_cols = st.columns(5)
    for col, key, lbl in zip(slider_cols, SLIDER_KEYS, SLIDER_LBLS):
        col.slider(
            lbl,
            min_value=float(SLIDER_RANGE[0]),
            max_value=float(SLIDER_RANGE[1]),
            step=5.0,
            key=key,
            format="%.0f",
        )

    with st.expander("Full scenario vector (all tenors)"):
        st.dataframe(
            pd.DataFrame({
                'Tenor':        panel.tenor_labels,
                'Anchor':       ['●' if a else '○' for a in is_anchor],
                'ΔT (yr)':     [f"{x:.4f}" for x in panel.dT],
                'bp / quarter': [f"{v:+.2f}" for v in full_bps_Q],
            }),
            use_container_width=True, hide_index=True,
        )