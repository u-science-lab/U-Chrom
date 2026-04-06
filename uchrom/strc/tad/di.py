"""
Directionality Index (DI) based TAD detection.
GPU-accelerated implementation using PyTorch.

Reference: Dixon et al. (2012) Nature
"""

import torch
import numpy as np
from typing import List, Tuple, Optional


def get_device(device: str = 'auto') -> torch.device:
    """Get appropriate torch device."""
    if device == 'auto':
        if torch.cuda.is_available():
            return torch.device('cuda')
        elif torch.backends.mps.is_available():
            return torch.device('mps')
        else:
            return torch.device('cpu')
    return torch.device(device)


def get_dtype(device: torch.device) -> torch.dtype:
    """Get appropriate dtype for device. MPS only supports float32."""
    if device.type == 'mps':
        return torch.float32
    return torch.float64


def calc_directionality_index(
    contact_mat: torch.Tensor,
    window: int = 50,
    device: str = 'auto'
) -> torch.Tensor:
    """
    Calculate Directionality Index for each genomic bin.
    
    DI measures the degree of upstream vs downstream interaction bias.
    Positive DI = more downstream interactions (start of TAD)
    Negative DI = more upstream interactions (end of TAD)
    
    Reference: Dixon et al. (2012) Nature - Supplementary
    """
    dev = get_device(device)
    dtype = get_dtype(dev)
    mat = contact_mat.to(dtype=dtype, device=dev)
    n = mat.shape[0]
    
    di = torch.zeros(n, dtype=dtype, device=dev)
    
    # Vectorized computation where possible
    for i in range(window, n - window):
        # Upstream: bins [i-window, i)
        upstream_start = max(0, i - window)
        upstream = mat[i, upstream_start:i].sum()
        
        # Downstream: bins (i, i+window]
        downstream_end = min(n, i + window + 1)
        downstream = mat[i, i+1:downstream_end].sum()
        
        # Count valid bins
        a_count = i - upstream_start
        b_count = downstream_end - i - 1
        
        # Average
        avg_a = upstream / a_count if a_count > 0 else 0
        avg_b = downstream / b_count if b_count > 0 else 0
        
        # Calculate DI using chi-squared-like formula
        if avg_a != avg_b and (avg_a + avg_b) > 0:
            e = (avg_a + avg_b) / 2
            sign = 1 if (avg_b - avg_a) > 0 else -1
            di[i] = sign * ((avg_a - e)**2 / e + (avg_b - e)**2 / e)
    
    return di


def smooth_with_moving_average(
    signal: torch.Tensor,
    window_size: int
) -> torch.Tensor:
    """
    Apply moving average smoothing to signal.
    
    Args:
        signal: 1D tensor to smooth
        window_size: Size of smoothing window
        
    Returns:
        Smoothed signal
    """
    if window_size <= 1:
        return signal.clone()
    
    n = len(signal)
    device = signal.device
    dtype = signal.dtype
    
    # Pad signal for convolution
    padded = torch.nn.functional.pad(
        signal.unsqueeze(0).unsqueeze(0), 
        (window_size // 2, window_size - window_size // 2 - 1),
        mode='reflect'
    ).squeeze()
    
    # Moving average kernel
    kernel = torch.ones(window_size, device=device, dtype=dtype) / window_size
    
    # Convolve
    smoothed = torch.nn.functional.conv1d(
        padded.unsqueeze(0).unsqueeze(0),
        kernel.unsqueeze(0).unsqueeze(0)
    ).squeeze()
    
    return smoothed[:n]


def detect_tad_boundaries(
    di: torch.Tensor,
    min_size_frac: float = 0.05
) -> List[Tuple[int, int]]:
    """
    Detect TAD boundaries from Directionality Index.
    
    TAD boundaries occur at sign changes (negative → positive).
    
    Args:
        di: Directionality Index tensor
        min_size_frac: Minimum TAD size as fraction of total length
        
    Returns:
        List of (start, end) tuples for each TAD
    """
    n = len(di)
    min_size = int(n * min_size_frac)
    
    # Move to CPU for boundary detection
    di_cpu = di.cpu().numpy()
    
    domains = []
    start = 0
    prev_score = 0.0
    
    for i in range(n):
        score = di_cpu[i]
        
        if i == n - 1:
            # End of chromosome, close remaining TAD
            domains.append((start, i))
            
        elif score > 0 and prev_score < 0 and (i - start) >= min_size:
            # Sign change from negative to positive = TAD boundary
            domains.append((start, i))
            start = i
        
        prev_score = score
    
    return domains


def get_domains(
    contact_mat: torch.Tensor,
    smoothing_param: float = 0.1,
    min_size_frac: float = 0.05,
    window: int = 50,
    device: str = 'auto'
) -> List[Tuple[int, int]]:
    """
    Identify TADs in contact matrix.
    
    Full pipeline: DI calculation → smoothing → boundary detection
    
    Args:
        contact_mat: N x N contact matrix
        smoothing_param: Smoothing factor (larger = more smoothing)
        min_size_frac: Minimum TAD size as fraction of total
        window: Window size for DI calculation
        device: Compute device
        
    Returns:
        List of (start_idx, end_idx) tuples for each TAD
    """
    # Calculate DI
    di = calc_directionality_index(contact_mat, window=window, device=device)
    
    # Smooth
    n = len(di)
    smoothing_window = max(1, int(n * smoothing_param))
    di_smoothed = smooth_with_moving_average(di, smoothing_window)
    
    # Detect boundaries
    domains = detect_tad_boundaries(di_smoothed, min_size_frac)
    
    return domains


def calc_di_batch(
    contact_mat: torch.Tensor,
    window: int = 50,
    device: str = 'auto'
) -> torch.Tensor:
    """
    Batch-optimized DI calculation using matrix operations.
    
    Faster for large matrices on GPU.
    
    Args:
        contact_mat: N x N contact matrix
        window: Window size
        device: Compute device
        
    Returns:
        N-length DI tensor
    """
    dev = get_device(device)
    dtype = get_dtype(dev)
    mat = contact_mat.to(dtype=dtype, device=dev)
    n = mat.shape[0]
    
    di = torch.zeros(n, dtype=dtype, device=dev)
    
    # Create upstream and downstream masks
    for i in range(window, n - window):
        # Use slicing for efficiency
        upstream = mat[i, i-window:i]
        downstream = mat[i, i+1:i+window+1]
        
        a = upstream.sum()
        b = downstream.sum()
        
        avg_a = a / window
        avg_b = b / window
        
        if avg_a + avg_b > 0 and avg_a != avg_b:
            e = (avg_a + avg_b) / 2
            sign = torch.sign(avg_b - avg_a)
            di[i] = sign * ((avg_a - e)**2 / e + (avg_b - e)**2 / e)
    
    return di
