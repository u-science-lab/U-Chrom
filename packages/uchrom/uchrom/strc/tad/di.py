# Directionality Index (DI) based TAD detection
# Reference: Dixon et al. (2012) Nature

import torch
import numpy as np


def get_device(device='auto'):
    """Get appropriate torch device."""
    if device == 'auto':
        if torch.cuda.is_available():
            return torch.device('cuda')
        elif torch.backends.mps.is_available():
            return torch.device('mps')
        else:
            return torch.device('cpu')
    return torch.device(device)


def get_dtype(device):
    """MPS only supports float32."""
    if device.type == 'mps':
        return torch.float32
    return torch.float64


def calc_directionality_index(contact_mat, window=50, device='auto'):
    """Calculate Directionality Index for each genomic bin."""
    dev = get_device(device)
    dtype = get_dtype(dev)
    mat = contact_mat.to(dtype=dtype, device=dev)
    n = mat.shape[0]

    di = torch.zeros(n, dtype=dtype, device=dev)

    for i in range(window, n - window):
        upstream_start = max(0, i - window)
        upstream = mat[i, upstream_start:i].sum()

        downstream_end = min(n, i + window + 1)
        downstream = mat[i, i+1:downstream_end].sum()

        a_count = i - upstream_start
        b_count = downstream_end - i - 1

        avg_a = upstream / a_count if a_count > 0 else 0
        avg_b = downstream / b_count if b_count > 0 else 0

        # chi-squared-like formula
        if avg_a != avg_b and (avg_a + avg_b) > 0:
            e = (avg_a + avg_b) / 2
            sign = 1 if (avg_b - avg_a) > 0 else -1
            di[i] = sign * ((avg_a - e)**2 / e + (avg_b - e)**2 / e)

    return di


def smooth_with_moving_average(signal, window_size):
    """Apply moving average smoothing via 1D convolution."""
    if window_size <= 1:
        return signal.clone()

    n = len(signal)
    device = signal.device
    dtype = signal.dtype

    padded = torch.nn.functional.pad(
        signal.unsqueeze(0).unsqueeze(0),
        (window_size // 2, window_size - window_size // 2 - 1),
        mode='reflect'
    ).squeeze()

    kernel = torch.ones(window_size, device=device, dtype=dtype) / window_size

    smoothed = torch.nn.functional.conv1d(
        padded.unsqueeze(0).unsqueeze(0),
        kernel.unsqueeze(0).unsqueeze(0)
    ).squeeze()

    return smoothed[:n]


def detect_tad_boundaries(di, min_size_frac=0.05):
    """Detect TAD boundaries from sign changes (negative -> positive)."""
    n = len(di)
    min_size = int(n * min_size_frac)
    di_cpu = di.cpu().numpy()

    domains = []
    start = 0
    prev_score = 0.0

    for i in range(n):
        score = di_cpu[i]
        if i == n - 1:
            domains.append((start, i))
        elif score > 0 and prev_score < 0 and (i - start) >= min_size:
            domains.append((start, i))
            start = i
        prev_score = score

    return domains


def get_domains(contact_mat, smoothing_param=0.1, min_size_frac=0.05,
                window=50, device='auto'):
    """Identify TADs: DI calculation -> smoothing -> boundary detection."""
    di = calc_directionality_index(contact_mat, window=window, device=device)
    n = len(di)
    smoothing_window = max(1, int(n * smoothing_param))
    di_smoothed = smooth_with_moving_average(di, smoothing_window)
    domains = detect_tad_boundaries(di_smoothed, min_size_frac)
    return domains


def calc_di_batch(contact_mat, window=50, device='auto'):
    """Batch-optimized DI calculation using matrix operations."""
    dev = get_device(device)
    dtype = get_dtype(dev)
    mat = contact_mat.to(dtype=dtype, device=dev)
    n = mat.shape[0]

    di = torch.zeros(n, dtype=dtype, device=dev)

    for i in range(window, n - window):
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
