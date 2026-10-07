"""Natural chromosome order (``uchrom.io.sort_chroms``)."""

import pandas as pd

from uchrom.io import chrom_sort_key, sort_chroms


def test_sort_chroms():
    names = pd.Series(["chr10", "chrX", "chr2", "chr1", "chr2", "chrM", "chrY", "chr19"], dtype="category")
    assert sort_chroms(names) == ["chr1", "chr2", "chr10", "chr19", "chrX", "chrY", "chrM"]
    assert sort_chroms(["10", "2", "X", "1"]) == ["1", "2", "10", "X"]
    assert chrom_sort_key("chr7") < chrom_sort_key("chr11") < chrom_sort_key("chrX") < chrom_sort_key("MT")
