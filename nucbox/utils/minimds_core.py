"""
miniMDS core algorithm implementation - faithful to original miniMDS.
Based on the original miniMDS code from https://github.com/seqcode/miniMDS
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Dict
from sklearn.manifold import MDS
import multiprocessing as mp
from scipy.spatial.distance import pdist, squareform


class ChromParameters:
    """Basic information on chromosome, inferred from input file"""
    def __init__(self, minPos: int, maxPos: int, res: int, name: str):
        self.minPos = minPos    # minimum genomic coordinate
        self.maxPos = maxPos    # maximum genomic coordinate
        self.res = res          # resolution (bp)
        self.name = name        # e.g. "chr22"

    def getLength(self) -> int:
        """Number of possible loci"""
        return int((self.maxPos - self.minPos) / self.res) + 1

    def getAbsoluteIndex(self, genCoord: int) -> Optional[int]:
        """Converts genomic coordinate into absolute index"""
        if genCoord < self.minPos or genCoord > self.maxPos + self.res:
            return None
        else:
            return int((genCoord - self.minPos) / self.res)

    def getGenCoord(self, abs_index: int) -> int:
        """Converts absolute index into genomic coordinate"""
        return self.minPos + self.res * abs_index

    def reduceRes(self, resRatio: int) -> 'ChromParameters':
        """Creates low-res version of this chromosome"""
        lowRes = self.res * resRatio
        lowMinPos = (self.minPos // lowRes) * lowRes
        lowMaxPos = (self.maxPos // lowRes) * lowRes
        return ChromParameters(lowMinPos, lowMaxPos, lowRes, self.name)


class Point:
    """Point in 3-D space"""
    def __init__(self, pos: Tuple[float, float, float], chrom: ChromParameters, 
                 absolute_index: int, relative_index: int):
        self.pos = pos                    # 3D coordinates
        self.chrom = chrom               # chromosome parameters
        self.absolute_index = absolute_index  # index relative to all points
        self.relative_index = relative_index  # index relative to non-zero points


class Structure:
    """Intrachromosomal structure of points or substructures in 3-D space"""
    def __init__(self, points: List[Point], structures: List, chrom: ChromParameters, offset: int):
        self.points = np.array(points, dtype=object)
        if len(structures) == 0 or structures is None:
            self.structures = []
        else:
            self.setstructures(structures)
        self.chrom = chrom
        self.offset = offset

    def getCoords(self) -> List[Tuple[float, float, float]]:
        """Get 3D coordinates of all non-zero points"""
        return [point.pos for point in self.getPoints()]

    def setCoords(self, coords: np.ndarray):
        """Set 3D coordinates for all non-zero points"""
        for coord, abs_index in zip(coords, self.nonzero_abs_indices()):
            self.points[abs_index - self.offset].pos = coord

    def nonzero_abs_indices(self) -> np.ndarray:
        """Absolute indices for all non-zero points"""
        return np.array([point.absolute_index for point in self.getPoints()])

    def getPoints(self) -> List[Point]:
        """All non-zero points"""
        return [point for point in self.points if point != 0]

    def getGenCoords(self) -> List[int]:
        """Non-zero genomic coordinates of structure"""
        return [self.chrom.getGenCoord(abs_index) for abs_index in self.nonzero_abs_indices()]

    def get_rel_index(self, genCoord: int) -> Optional[int]:
        """Converts genomic coordinate into relative index"""
        abs_index = self.chrom.getAbsoluteIndex(genCoord)
        if abs_index is None:
            return None
        else:
            abs_index -= self.offset
            if 0 <= abs_index < len(self.points):
                point = self.points[abs_index]
                if point == 0:
                    return None
                else:
                    return point.relative_index
            else:
                return None

    def setstructures(self, structures: List):
        """Set substructures"""
        self.structures = structures
        if len(structures) == 0:
            # If no structures, create empty points array
            self.points = np.zeros(0, dtype=object)
            return
        
        # Find maximum absolute index
        max_abs_index = 0
        for structure in self.structures:
            if len(structure.nonzero_abs_indices()) > 0:
                max_abs_index = max(max_abs_index, max(structure.nonzero_abs_indices()))
        
        self.points = np.zeros(max_abs_index + 1, dtype=object)
        for structure in self.structures:
            for point in structure.points:
                if point != 0:
                    self.points[point.absolute_index] = point

    def createSubstructure(self, points: List[Point], offset: int):
        """Creates substructure containing points"""
        substructure = Structure(points, [], self.chrom, offset)
        self.structures.append(substructure)

    def transform(self, r: np.ndarray, t: np.ndarray):
        """Rotates by r; translates by t"""
        if r is None:
            r = np.eye(3)
        if t is None:
            t = np.zeros(3)
        
        coords = np.array(self.getCoords())
        n = len(coords)
        
        # Ensure t is a column vector
        if t.ndim == 1:
            t = t.reshape(-1, 1)
        
        coords_transformed = (r @ coords.T + t).T
        
        for i, abs_index in enumerate(self.nonzero_abs_indices()):
            self.points[abs_index - self.offset].pos = tuple(coords_transformed[i])

    def set_rel_indices(self):
        """Relative indexing is index relative to non-zero points only"""
        for i, abs_index in enumerate(self.nonzero_abs_indices()):
            assert abs_index >= self.offset
            self.points[abs_index - self.offset].relative_index = i


def structureFromBed(path: str, size: Optional[int] = None, chrom: Optional[ChromParameters] = None,
                    start: Optional[int] = None, end: Optional[int] = None, offset: int = 0,
                    chrom_order: Optional[int] = None) -> Structure:
    """Initializes structure from intrachromosomal BED file"""
    if chrom is None:
        chrom = chromFromBed(path)

    if start is None:
        start = chrom.minPos
    if end is None:
        end = chrom.maxPos

    structure = Structure([], [], chrom, offset)
    structure.points = np.zeros(int((end - start) / chrom.res) + 1, dtype=object)

    # Add loci
    with open(path) as listFile:
        for line in listFile:
            line = line.strip().split()
            pos1 = int(line[1])
            pos2 = int(line[4])

            # Intrachromosomal
            if chrom_order is None:
                if start <= pos1 <= end and start <= pos2 <= end:
                    abs_index1 = structure.chrom.getAbsoluteIndex(pos1)
                    abs_index2 = structure.chrom.getAbsoluteIndex(pos2)
                    if abs_index1 != abs_index2:  # non-self-interacting
                        structure.points[int((pos1 - start) / chrom.res)] = Point((0, 0, 0), structure.chrom, abs_index1, 0)
                        structure.points[int((pos2 - start) / chrom.res)] = Point((0, 0, 0), structure.chrom, abs_index2, 0)
            elif chrom_order == 1:
                if start <= pos1 <= end:
                    abs_index = structure.chrom.getAbsoluteIndex(pos1)
                    structure.points[int((pos1 - start) / chrom.res)] = Point((0, 0, 0), structure.chrom, abs_index, 0)
            elif chrom_order == 2:
                if start <= pos2 <= end:
                    abs_index = structure.chrom.getAbsoluteIndex(pos2)
                    structure.points[int((pos2 - start) / chrom.res)] = Point((0, 0, 0), structure.chrom, abs_index, 0)

    structure.set_rel_indices()
    return structure


def chromFromBed(path: str, return_both: bool = False) -> ChromParameters:
    """Initialize ChromParams from BED file"""
    minPos1 = float('inf')
    maxPos1 = 0
    minPos2 = float('inf')
    maxPos2 = 0

    with open(path) as infile:
        for i, line in enumerate(infile):
            line = line.split()
            pos1 = int(line[1])
            pos2 = int(line[4])

            if i == 0:  # get info from first line
                name1 = line[0]
                res1 = int(line[2]) - pos1
                name2 = line[3]
                res2 = int(line[5]) - pos2

            if pos1 < minPos1:
                minPos1 = pos1
            if pos1 > maxPos1:
                maxPos1 = pos1

            if pos2 < minPos2:
                minPos2 = pos2
            if pos2 > maxPos2:
                maxPos2 = pos2

    def round_down(pos, res):
        return int(np.floor(float(pos) / res)) * res

    def round_up(pos, res):
        return int(np.ceil(float(pos) / res)) * res

    if return_both:
        return (ChromParameters(round_down(minPos1, res1), round_up(maxPos1, res1), res1, name1),
                ChromParameters(round_down(minPos2, res2), round_up(maxPos2, res2), res2, name2))
    else:
        return ChromParameters(round_down(min((minPos1, minPos2)), res1), 
                              round_up(max((maxPos1, maxPos2)), res1), res1, name1)


def matFromBed(path: str, size: Optional[int] = None, structure1: Optional[Structure] = None,
               structure2: Optional[Structure] = None) -> np.ndarray:
    """Converts BED file to matrix. Only includes loci in structure."""
    if structure1 is None:
        structure1 = structureFromBed(path, size)

    # Intrachromosomal
    if structure2 is None:
        structure2 = structure1
        intrachromosomal = True
    else:
        intrachromosomal = False

    mat = np.zeros((len(structure1.nonzero_abs_indices()), len(structure2.nonzero_abs_indices())))

    with open(path) as infile:
        for line in infile:
            line = line.strip().split()
            loc1 = int(line[1])
            loc2 = int(line[4])
            index1 = structure1.get_rel_index(loc1)
            index2 = structure2.get_rel_index(loc2)
            if index1 is not None and index2 is not None:
                val = float(line[6])
                mat[index1, index2] += val
                if intrachromosomal:
                    mat[index2, index1] += val

    rowsums = np.array([sum(row) for row in mat])
    assert len(np.where(rowsums == 0)[0]) == 0

    return mat


def get_expected(mat: np.ndarray) -> np.ndarray:
    """Calculate expected contact frequencies based on distance decay"""
    n = len(mat)
    if n <= 1:
        return np.array([1.0])  # Return default value for small matrices
    
    tots = np.zeros(n - 1)
    counts = np.zeros(n - 1)

    for i in range(n):
        for j in range(i):
            observed = mat[i, j]
            if observed != 0:
                s = i - j  # genomic distance
                if s > 0 and s <= len(tots):  # Bounds check
                    tots[s - 1] += observed
                    counts[s - 1] += 1

    avgs = np.ones(n - 1)  # Default to 1.0 instead of 0.0
    for i, count in enumerate(counts):
        if count != 0:
            avgs[i] = tots[i] / count

    return avgs


def contactToDist(contactMat: np.ndarray, alpha: float) -> np.ndarray:
    """Convert contact matrix to distance matrix"""
    distMat = np.zeros_like(contactMat)
    numRows = len(contactMat)
    for i in range(numRows):
        for j in range(i + 1):
            if contactMat[i, j] != 0:
                distMat[i, j] = contactMat[i, j] ** (-1. / alpha)
    return distMat


def makeSymmetric(mat: np.ndarray):
    """Make below-diagonal matrix symmetric, in place"""
    for row in range(len(mat)):
        for col in range(row):
            mat[col, row] = mat[row, col]


def getTransformation(structure1: Structure, structure2: Structure) -> Tuple[np.ndarray, np.ndarray]:
    """Recovers transformation needed to align structure1 with structure2"""
    abs_indices1 = structure1.nonzero_abs_indices()
    abs_indices2 = structure2.nonzero_abs_indices()

    intersection = [num for num in abs_indices1 if num in abs_indices2]

    a = []  # will hold 3D coords
    b = []
    for num in intersection:
        a.append(structure1.points[int(num) - int(structure1.offset)].pos)
        b.append(structure2.points[int(num) - int(structure2.offset)].pos)

    a = np.array(a)
    b = np.array(b)

    n = a.shape[0]  # number of points

    centroid_a = np.mean(a, axis=0)
    centroid_b = np.mean(b, axis=0)

    # center the points
    aa = a - np.tile(centroid_a, (n, 1))
    bb = b - np.tile(centroid_b, (n, 1))

    h = np.transpose(aa) @ bb

    u, s, vt = np.linalg.svd(h)

    r = vt.T @ u.T

    t = -r @ centroid_a.T + centroid_b.T

    return r, t


def radius_of_gyration(structure: Structure) -> float:
    """Calculate radius of gyration of structure"""
    coords = np.array(structure.getCoords())
    centroid = np.mean(coords, axis=0)
    dist_sum = sum([np.linalg.norm(coord - centroid) for coord in coords])
    return dist_sum / len(coords)


def highToLow(highstructure: Structure, resRatio: int) -> Structure:
    """Reduces resolution of structure"""
    lowChrom = highstructure.chrom.reduceRes(resRatio)

    low_n = int(len(highstructure.points) / resRatio) + 1

    lowstructure = Structure(np.zeros(low_n, dtype=object), [], lowChrom, highstructure.offset // resRatio)

    allPointsToMerge = [[] for i in range(low_n)]

    for highPoint in highstructure.getPoints():
        high_abs_index = highPoint.absolute_index - highstructure.offset
        low_abs_index = int(high_abs_index / resRatio)
        allPointsToMerge[low_abs_index].append(highPoint)

    index = lowstructure.offset
    for i, pointsToMerge in enumerate(allPointsToMerge):
        if len(pointsToMerge) > 0:
            meanCoord = np.mean(np.array([point.pos for point in pointsToMerge]), axis=0)
            lowstructure.points[i] = Point(tuple(meanCoord), lowChrom, i + lowstructure.offset, index)
            index += 1

    return lowstructure


def cmds(distMat: np.ndarray) -> np.ndarray:
    """Classical MDS implementation"""
    # Number of points
    n = len(distMat)

    # Centering matrix
    h = np.eye(n) - np.ones((n, n)) / n

    # YY^T
    b = -h @ (distMat ** 2) @ h / 2

    # Diagonalize
    evals, evecs = np.linalg.eigh(b)

    # Sort by eigenvalue in descending order
    idx = np.argsort(evals)[::-1]
    evals = evals[idx]
    evecs = evecs[:, idx]

    return np.array([evecs[:, 0] * evals[0] ** (1. / 2),
                     evecs[:, 1] * evals[1] ** (1. / 2),
                     evecs[:, 2] * evals[2] ** (1. / 2)]).T
