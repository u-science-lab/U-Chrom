"""
TAD (Topologically Associating Domain) detection algorithm from miniMDS.
Based on directionality index calculation and domain identification.
"""

import numpy as np
from typing import List, Tuple
from .minimds_core import Structure


def calcScore(abs_index: int, points: List, contactMat: np.ndarray, numPoints: int) -> float:
    """Calculates directionality score for locus. Positive=downstream. Negative=upstream."""
    a = 0      # initialize
    b = 0
    aCount = 0
    bCount = 0
    avg_a = 0
    avg_b = 0
    currIndex = points[abs_index].relative_index

    # upstream
    upstreamIndexFound = False
    numPointsUpstream = numPoints  # max separation from curr point to include
    while not upstreamIndexFound and numPointsUpstream > 0:
        if points[abs_index - numPointsUpstream] != 0:
            upstreamIndexFound = True
            minIndex = points[abs_index - numPointsUpstream].relative_index
        else:
            numPointsUpstream -= 1

    if upstreamIndexFound:
        for i in range(minIndex, currIndex):
            a += contactMat[currIndex][i]
            aCount += 1
        if aCount != 0:
            avg_a = a / aCount

    # downstream
    downstreamIndexFound = False
    numPointsDownstream = numPoints  # max separation from curr point to include
    while not downstreamIndexFound and numPointsDownstream > 0:
        if points[abs_index + numPointsDownstream] != 0:
            downstreamIndexFound = True
            maxIndex = points[abs_index + numPointsDownstream].relative_index
        else:
            numPointsDownstream -= 1

    if downstreamIndexFound:
        for i in range(currIndex + 1, maxIndex):
            b += contactMat[i][currIndex]
            bCount += 1
        if bCount != 0:
            avg_b = b / bCount

    if aCount != 0 and bCount != 0 and avg_a != avg_b:
        e = (avg_a + avg_b) / 2
        score = (avg_b - avg_a) / abs(avg_b - avg_a) * ((avg_a - e) ** 2 / e + (avg_b - e) ** 2 / e)
    else:
        score = 0

    return score


def allScores(contactMat: np.ndarray, structure: Structure, maxNumPoints: int) -> List[float]:
    """Calculates all directionality scores for chromosome"""
    scores = []
    totNumLoc = len(contactMat)
    for abs_index in structure.nonzero_abs_indices():
        i = structure.points[abs_index - structure.offset].relative_index
        numPoints = min((maxNumPoints, totNumLoc - 1 - i, i))  # avoid going out of range
        scores.append(calcScore(abs_index, structure.points, contactMat, numPoints))
    return scores


def domainsFromScores(scores: List[float], minSizeFraction: float) -> np.ndarray:
    """Extract domains from directionality scores"""
    minNumLoc = minSizeFraction * len(scores)
    start = 0  # initialize
    prevScore = 0
    domains = []
    for i in range(len(scores)):
        score = scores[i]
        if i == len(scores) - 1:  # at end of scores, close remaining TAD
            end = i
            domains.append([start, end])
        elif score > 0 and prevScore < 0 and i - start >= minNumLoc:  # current is downstream, previous was upstream
            end = i
            domains.append([start, end])
            start = i
        prevScore = score
    return np.array(domains)


def movingAverage(signal: List[float], size_of_window: int) -> np.ndarray:
    """Moving average smoothing"""
    if len(signal) == 0:
        return np.array([])
    
    # If signal is shorter than window, return the signal as is
    if len(signal) < size_of_window:
        return np.array(signal)
    
    window = np.ones(size_of_window)
    return np.roll(np.convolve(window / size_of_window, signal, "valid"), int(size_of_window / 2))


def smoothWithMovingAverage(signal: List[float], size_of_window: int) -> np.ndarray:
    """Smooth signal with moving average"""
    if len(signal) == 0:
        return np.array([])
    
    # If signal is too short for smoothing, return as is
    if len(signal) < size_of_window:
        return np.array(signal)
    
    smoothed = movingAverage(signal, size_of_window)
    signal_size = len(signal)
    remainder = signal[signal_size - size_of_window + 1: signal_size]  # end of signal
    smoothed_remainder = np.zeros_like(remainder)
    remainder_size = size_of_window - 1
    for i in range(remainder_size):
        smoothed_remainder[i] = movingAverage(remainder[i:remainder_size], remainder_size - i)
    return np.concatenate((smoothed, smoothed_remainder))


def getDomains(contactMat: np.ndarray, structure: Structure, sizeParameter: float, minSizeFraction: float) -> np.ndarray:
    """Identify TADs in contact matrix"""
    scores = allScores(contactMat, structure, 50)  # 50 is from Dixon 2012 supplemental
    smoothingFactor = max((int(len(contactMat) * sizeParameter), 1))  # must be >= 1
    smoothed = smoothWithMovingAverage(scores, smoothingFactor)
    return domainsFromScores(smoothed, minSizeFraction)


def substructuresFromTads(structure: Structure, tads: np.ndarray):
    """Create substructures from TAD domains"""
    abs_indices = structure.nonzero_abs_indices()
    offset = 0  # initialize
    for td in tads:
        start = abs_indices[td[0]]  # convert from relative index to absolute index
        end = abs_indices[td[1]]
        points = structure.points[start - structure.offset:end - structure.offset]
        structure.createSubstructure(points, offset)
        offset = end  # update
