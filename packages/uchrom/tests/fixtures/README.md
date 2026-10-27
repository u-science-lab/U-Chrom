# Test fixtures

Small slices of real data the unit tests read offline.  Larger data come from the public atlas or
their sources through `uchrom.datasets` (tests that need them skip when they are absent).

| File | Content | Source |
|------|---------|--------|
| `cell1.pairs.gz` | 105,700 contact pairs of one haploid mESC G1 cell (`.pairs` columns without a header: read, chr1, pos1, chr2, pos2, strand1, strand2) | Stevens et al. 2017, *Nature* 544:59, GEO GSE80280 (the NucDynamics example cell) |
| `K562_chr21_30kb.cool` | K562 in situ Hi-C, chr21 at 30 kb (raw counts) | Ray et al. 2019, 4DN 4DNFI4QQPDMR (cut from the mcool); K562, not IMR90 |
| `mESC_Sox2_5cells_wnan.chromdata.zarr` | 5 traces x 41 loci of the Sox2 locus at 5 kb, 24 % of spots missing | Huang et al. 2021, *Nature Genetics*, doi:10.1038/s41588-021-00863-6 (via SnapFISH-IMPUTE's example) |
| `4DNFIFINA2U9.csv`, `4DNFIJ52NVDV.csv` | cell table (RNA counts, nuclear area) and nascent RNA spots of the 201 cells of the FOF-CT core table 4DNFIHF3JCBY | Takei et al. 2021, *Nature* 590:344, 4DN set 4DNESL2AY9CM |
| `fixture_barcode_only.ecsv`, `fixture_with_chrom.ecsv` | PyHiM ECSV traces | made from Bintu et al. 2018 IMR90 chr21 |
| `macs3/` | MACS3's own regression results (see its README) | MACS3, BSD-3-Clause |
| `fourdn_tracing/` | one 4DN FOF-CT experiment of each of four studies, cut to its first traces (Hafner: the traces of its first two fields of view) with the matching rows of its companion tables, headers kept as deposited: `<dataset>_<experiment>_<kind>_<file>.csv` | 4DN Data Portal: Bintu et al. 2018 (set 4DNESSXNNJUB), Hafner et al. 2023 (4DNESQ49IXDU), Mateo et al. 2019 (4DNESWM4U8RX), Murphy & Boettiger 2024 (4DNESTQ3UVYR) |
