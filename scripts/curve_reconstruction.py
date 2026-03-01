"""
curve_reconstruction.py
=======================
Reconstruct continuous yield curves from bootstrap parameters.

For each scheme, we use the actual forward rate functions to compute
discount factors at dense points, then derive spot rates.

This gives mathematically correct curves instead of linear interpolation.
"""

import numpy as np
from typing import Tuple, Optional

# ============================================================================
# FORWARD RATE RECONSTRUCTION
# ============================================================================

def reconstruct_scheme1_forward(T_nodes, f_params, t_eval):
    """
    Reconstruct piecewise constant forward curve (Scheme 1)
    
    Args:
        T_nodes: Tenor endpoints where parameters apply (only used tenors)
        f_params: Constant forward rates for each interval
        t_eval: Dense time grid for evaluation
    
    Returns:
        f_values: Forward rates at t_eval points
    """
    f_values = np.zeros_like(t_eval)
    
    T_start = 0.0
    for i, (T_end, f_i) in enumerate(zip(T_nodes, f_params)):
        if not np.isfinite(f_i):
            continue
        
        # f(t) = f_i for T_start <= t < T_end
        mask = (t_eval >= T_start) & (t_eval < T_end)
        f_values[mask] = f_i
        
        T_start = T_end
    
    # Extend last forward rate to end
    if len(T_nodes) > 0 and np.isfinite(f_params[-1]):
        mask = t_eval >= T_nodes[-1]
        f_values[mask] = f_params[-1]
    
    return f_values


def reconstruct_scheme2_forward(T_nodes, a_params, b_params, t_eval):
    """
    Reconstruct piecewise linear forward curve (Scheme 2)
    
    Args:
        T_nodes: Tenor endpoints where parameters apply
        a_params: Linear slope coefficients
        b_params: Intercept coefficients
        t_eval: Dense time grid for evaluation
    
    Returns:
        f_values: Forward rates at t_eval points
    """
    f_values = np.zeros_like(t_eval)
    
    T_start = 0.0
    for i, (T_end, a_i, b_i) in enumerate(zip(T_nodes, a_params, b_params)):
        if not (np.isfinite(a_i) and np.isfinite(b_i)):
            continue
        
        # f(t) = a_i * (t - T_start) + b_i for T_start <= t < T_end
        mask = (t_eval >= T_start) & (t_eval < T_end)
        dt = t_eval[mask] - T_start
        f_values[mask] = a_i * dt + b_i
        
        T_start = T_end
    
    # Extend last segment
    if len(T_nodes) > 0 and np.isfinite(a_params[-1]) and np.isfinite(b_params[-1]):
        mask = t_eval >= T_nodes[-1]
        dt = t_eval[mask] - T_nodes[-1]
        # Forward at end of last interval
        f_end = a_params[-1] * (T_nodes[-1] - (T_nodes[-2] if len(T_nodes) > 1 else 0.0)) + b_params[-1]
        f_values[mask] = f_end
    
    return f_values


def reconstruct_scheme3_forward(T_nodes, a_params, b_params, c_params, d_params, t_eval):
    """
    Reconstruct monotone cubic forward curve (Scheme 3)
    
    Args:
        T_nodes: Tenor endpoints where parameters apply
        a_params, b_params, c_params, d_params: Cubic coefficients
        t_eval: Dense time grid for evaluation
    
    Returns:
        f_values: Forward rates at t_eval points
    """
    f_values = np.zeros_like(t_eval)
    
    T_start = 0.0
    for i, (T_end, a_i, b_i, c_i, d_i) in enumerate(zip(T_nodes, a_params, b_params, c_params, d_params)):
        if not (np.isfinite(a_i) and np.isfinite(b_i) and np.isfinite(c_i) and np.isfinite(d_i)):
            continue
        
        # f(t) = a_i*t³ + b_i*t² + c_i*t + d_i for T_start <= t < T_end
        # where t is measured from T_start
        mask = (t_eval >= T_start) & (t_eval < T_end)
        dt = t_eval[mask] - T_start
        f_values[mask] = a_i * dt**3 + b_i * dt**2 + c_i * dt + d_i
        
        T_start = T_end
    
    # Extend last segment (flat extension at endpoint value)
    if len(T_nodes) > 0 and np.isfinite(a_params[-1]):
        mask = t_eval >= T_nodes[-1]
        dt_end = T_nodes[-1] - (T_nodes[-2] if len(T_nodes) > 1 else 0.0)
        f_end = a_params[-1] * dt_end**3 + b_params[-1] * dt_end**2 + c_params[-1] * dt_end + d_params[-1]
        f_values[mask] = f_end
    
    return f_values


# ============================================================================
# DISCOUNT FACTOR RECONSTRUCTION
# ============================================================================

def integrate_forward_to_discount(f_values, t_eval):
    """
    Integrate forward rates to get discount factors
    
    P(T) = exp(-∫₀ᵀ f(s) ds)
    
    Uses trapezoidal rule for numerical integration
    
    Args:
        f_values: Forward rates at t_eval points
        t_eval: Time grid
    
    Returns:
        P_values: Discount factors at t_eval points
    """
    # Cumulative integral using trapezoidal rule
    dt = np.diff(t_eval)
    f_avg = (f_values[:-1] + f_values[1:]) / 2.0
    
    integral = np.zeros(len(t_eval))
    integral[1:] = np.cumsum(f_avg * dt)
    
    # P(t) = exp(-integral)
    P_values = np.exp(-integral)
    
    return P_values


def compute_spot_from_discount(P_values, t_eval, f_values):
    """
    Compute spot (zero) rates from discount factors
    
    z(T) = -log(P(T)) / T
    
    For t→0, use L'Hôpital's rule: lim(t→0) z(t) = f(0)
    
    Args:
        P_values: Discount factors at t_eval points
        t_eval: Time grid
        f_values: Forward rates (for t=0 limit)
    
    Returns:
        z_values: Spot rates at t_eval points
    """
    z_values = np.zeros_like(t_eval)
    
    # Compute spot rates where t > 0
    mask = t_eval > 1e-6
    z_values[mask] = -np.log(P_values[mask]) / t_eval[mask]
    
    # At t=0, z(0) = f(0) (L'Hôpital's rule)
    z_values[~mask] = f_values[~mask]
    
    return z_values


# ============================================================================
# MAIN RECONSTRUCTION FUNCTION
# ============================================================================

def reconstruct_curves(data, date_idx, num_points=1000):
    """
    Reconstruct all curves (forward, discount, spot) from bootstrap parameters
    
    Args:
        data: Dictionary from load_npz_data()
        date_idx: Index of date to reconstruct
        num_points: Number of evaluation points for smooth curves
    
    Returns:
        dict with keys:
            't_dense': Dense time grid
            'forward_dense': Forward rates at dense grid
            'discount_dense': Discount factors at dense grid
            'spot_dense': Spot rates at dense grid
            'T_nodes': Original tenor grid points (for markers)
            'forward_nodes': Forward at tenor nodes
            'discount_nodes': Discount at tenor nodes
            'spot_nodes': Spot at tenor nodes
    """
    method = data['method']
    
    # Get tenor grid (only used tenors)
    T_all = data['tenor_years']
    used_mask = np.isfinite(data['spot_rates'][date_idx])
    T_nodes = T_all[used_mask]
    
    if len(T_nodes) == 0:
        return None
    
    # Create dense evaluation grid
    T_max = T_nodes[-1] * 1.02  # Extend slightly beyond last tenor
    t_dense = np.linspace(0, T_max, num_points)
    
    # Reconstruct forward curve based on scheme
    if 'S1' in method:
        # Load Scheme 1 parameters
        f_all = data.get('s1_f', None)
        if f_all is None:
            return None
        
        f_params = f_all[date_idx][used_mask]
        forward_dense = reconstruct_scheme1_forward(T_nodes, f_params, t_dense)
        
    elif 'S2' in method:
        # Load Scheme 2 parameters
        a_all = data.get('s2_a', None)
        b_all = data.get('s2_b', None)
        if a_all is None or b_all is None:
            return None
        
        a_params = a_all[date_idx][used_mask]
        b_params = b_all[date_idx][used_mask]
        forward_dense = reconstruct_scheme2_forward(T_nodes, a_params, b_params, t_dense)
        
    elif 'S3' in method:
        # Load Scheme 3 parameters
        a_all = data.get('s3_a', None)
        b_all = data.get('s3_b', None)
        c_all = data.get('s3_c', None)
        d_all = data.get('s3_d', None)
        if a_all is None or b_all is None or c_all is None or d_all is None:
            return None
        
        a_params = a_all[date_idx][used_mask]
        b_params = b_all[date_idx][used_mask]
        c_params = c_all[date_idx][used_mask]
        d_params = d_all[date_idx][used_mask]
        forward_dense = reconstruct_scheme3_forward(
            T_nodes, a_params, b_params, c_params, d_params, t_dense
        )
    else:
        return None
    
    # Compute discount and spot from forward
    discount_dense = integrate_forward_to_discount(forward_dense, t_dense)
    spot_dense = compute_spot_from_discount(discount_dense, t_dense, forward_dense)
    
    # Get values at original tenor nodes (for markers)
    forward_nodes = data['forward_rates'][date_idx][used_mask]
    discount_nodes = data['discount_factors'][date_idx][used_mask]
    spot_nodes = data['spot_rates'][date_idx][used_mask]
    
    return {
        't_dense': t_dense,
        'forward_dense': forward_dense,
        'discount_dense': discount_dense,
        'spot_dense': spot_dense,
        'T_nodes': T_nodes,
        'forward_nodes': forward_nodes,
        'discount_nodes': discount_nodes,
        'spot_nodes': spot_nodes,
    }
