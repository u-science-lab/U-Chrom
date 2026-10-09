"""Where each dataset comes from: the original sources (4DN, GEO, Zenodo, GitHub, UCSC, ...).

Paths are relative to the data directory (:func:`uchrom.datasets.data_dir`).  An entry has either
``filename`` + ``url`` (one file) or ``files``: ``(relative path, url)`` pairs (or a function returning
them); optional ``md5`` (relative path -> md5), ``extract`` ((destination, archive URL, member suffix):
one member streamed out of a .tar.gz), ``extract_many`` ((destination dir, archive URL, member regex)),
``parallel`` (concurrent downloads), ``size_mb``, ``description``, ``default`` (an input of the tutorials:
fetched by ``python -m uchrom.datasets fetch --default``; False unless set), ``fig3`` (an input of the paper's
Fig. 3), ``build`` (made by a function of ``_builders`` instead of downloaded).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from ._paths import data_dir


_GSE305439 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE305nnn/GSE305439/suppl"
_GEMFISH = ("https://raw.githubusercontent.com/ahmedabbas81/GEM-FISH/"
            "e83fdb46183586bcaecd6f13927283efb02dd646")
_BINTU = "https://raw.githubusercontent.com/BogdanBintu/ChromatinImaging/master/Data"
_SU2020 = "https://zenodo.org/records/3928890/files"
# Stevens et al. 2017 (GEO GSE80280): Cell 1-8 = GSM2219497-GSM2219504
_STEVENS = [(n, f"GSM{2219496 + n}") for n in range(1, 9)]

_GEO_SAMPLE = "https://ftp.ncbi.nlm.nih.gov/geo/samples"


def _gsm(name: str) -> str:
    """GEO per-sample supplementary URL of a file named 'GSM<id>_…'."""
    gsm = name.split("_", 1)[0]
    return f"{_GEO_SAMPLE}/{gsm[:-3]}nnn/{gsm}/suppl/{name}"


def _geo_filelist(gse: str, pattern: str = "", cache: Path | None = None) -> list:
    """Names of a GEO series' supplementary files (its ``filelist.txt``, fetched once and cached), GSM files
    included."""
    import re
    cache = cache or data_dir() / ".geo_filelists"
    path = cache / f"{gse}_filelist.txt"
    if not path.is_file():
        url = f"https://ftp.ncbi.nlm.nih.gov/geo/series/{gse[:-3]}nnn/{gse}/suppl/filelist.txt"
        req = urllib.request.Request(url, headers={"User-Agent": "u-chrom datasets"})
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode()
        cache.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    rows = [line.split("\t") for line in path.read_text().splitlines()[1:]]
    return [row[1] for row in rows if len(row) > 1 and row[1].startswith("GSM") and re.search(pattern, row[1])]


def _gse(gse: str, name: str) -> str:
    return f"https://ftp.ncbi.nlm.nih.gov/geo/series/{gse[:-3]}nnn/{gse}/suppl/{name}"


# Single-cell Hi-C / multi-omics cited by Guo et al. 2026 (Cell) -- the atlas' single-cell studies.
# HiRES (Liu et al. 2023, Science, doi:10.1126/science.adg3797), GEO GSE223917: 7,895 cells (mouse embryo
# E7.0-E9.5 + brain), per cell .pairs.gz and the authors' 20 kb diploid structure (.3dg), RNA UMI counts.
_HIRES_META = ["GSE223917_HiRES_emb_metadata.xlsx", "GSE223917_HiRES_brain_metadata.xlsx",
               "GSE223917_HiRES_emb.rna.umicount.tsv.gz", "GSE223917_HiRES_brain.rna.umicount.tsv.gz"]
# dscHi-C (Wu et al. 2025, Cell Discov., doi:10.1038/s41421-025-00770-8), GEO GSE285812 (super-series).
_DSCHIC_AGING = [f"{gsm}_b{m}-month-BC-dscHiC.{part}"
                 for gsm, m in (("GSM8709626", 3), ("GSM8698919", 12), ("GSM8709603", 23))
                 for part in ("contacts.pairs.gz", "metadata.txt.gz")]
# GAGE-seq (Zhou et al. 2024, Nat. Genet., doi:10.1038/s41588-024-01745-3), GEO GSE238001: mouse cortex (mBC)
# and human bone marrow CD34+ (CD) libraries, contacts + RNA per library.
_GAGESEQ = [f"{gsm}_{kind}_{lib}" for gsm, kind, lib in (
    ("GSM7657697", "RNA", "mBC-RNA-0716-1.tsv.gz"), ("GSM7657698", "contact", "mBC-HiC-0716-1.pairs.gz"),
    ("GSM7657699", "RNA", "mBC-RNA-0716-2.tsv.gz"), ("GSM7657700", "contact", "mBC-HiC-0716-2.pairs.gz"),
    ("GSM7657701", "RNA", "mBC-RNA-0814-1.tsv.gz"), ("GSM7657702", "contact", "mBC-HiC-0814-1.pairs.gz"),
    ("GSM7657703", "RNA", "CD-RNA-0722-1.tsv.gz"), ("GSM7657704", "contact", "CD-HiC-0722-1.pairs.gz"),
    ("GSM7657705", "RNA", "CD-RNA-0722-2.tsv.gz"), ("GSM7657706", "contact", "CD-HiC-0722-2.pairs.gz"),
    ("GSM7657707", "RNA", "CD-RNA-0722-4.tsv.gz"), ("GSM7657708", "contact", "CD-HiC-0722-4.pairs.gz"))]
# Droplet Hi-C (Chang et al. 2024, Nat. Biotechnol., doi:10.1038/s41587-024-02447-1), GEO GSE253407: mouse cortex
# Droplet Hi-C (LC462, LC716) and Paired Hi-C (Hi-C LC464 / LC465 / LC608 + RNA LC466 / LC467 / LC613).
_DROPLET_META = ["GSE253407_Droplet_Hi-C_mouse_ctx_metadata.xls.gz", "GSE253407_Paired_Hi-C_mouse_ctx_metadata.xls.gz"]
_DROPLET = [f"{gsm}_{name}" for gsm, name in (
    ("GSM8020244", "LC462_mm10.sc.pairs.gz"), ("GSM8020244", "LC462_valid_bc.txt.gz"),
    ("GSM8020245", "LC716_mm10.sc.pairs.gz"), ("GSM8020245", "LC716_valid_bc.txt.gz"),
    ("GSM8020251", "LC464_merged_mm10.sc.pairs.gz"), ("GSM8020251", "LC464_valid_bc.txt.gz"),
    ("GSM8020252", "LC466_raw_feature_bc_matrix.h5"), ("GSM8020252", "LC466_valid_bc.txt.gz"),
    ("GSM8020253", "LC465_mm10.sc.pairs.gz"), ("GSM8020253", "LC465_valid_bc.txt.gz"),
    ("GSM8020254", "LC467_raw_feature_bc_matrix.h5"), ("GSM8020254", "LC467_valid_bc.txt.gz"),
    ("GSM8020255", "LC608_mm10.sc.pairs.gz"), ("GSM8020255", "LC608_valid_bc.txt.gz"),
    ("GSM8020256", "LC613_raw_feature_bc_matrix.h5"), ("GSM8020256", "LC613_valid_bc.txt.gz"))]


# Spatial ATAC-Hi-C, mouse brain (Nat Methods 2026, doi:10.1038/s41592-026-03217-4), GEO GSE307620.
_SPATIAL_ATAC_HIC = [
    f"{gsm}_{part}"
    for gsm, tag, merged in (("GSM9228169", "MouseBrainR6", "MBR6merge"), ("GSM9228170", "MouseBrainR8", "MBR8merge"))
    for part in (f"{merged}.fragments.tsv.gz", f"{merged}.fragments.tsv.gz.tbi.gz",
                 f"{merged}.hic.fragments.sorted.header.tsv.gz", f"{merged}.hic.fragments.sorted.header.tsv.gz.tbi.gz",
                 f"{tag}_metadata.json.gz", f"{tag}_scalefactors_json.json.gz", f"{tag}_tissue_hires_image.png.gz",
                 f"{tag}_tissue_lowres_image.png.gz", f"{tag}_tissue_positions_list.csv.gz")
]

# Spatial Hi-C-RNA (Guo et al. 2026, Cell, doi:10.1016/j.cell.2026.07.039), GEO GSE311199 — processed files
# only; the per-sample .pairs (6.6–159 GB each, ~680 GB) are not fetched.
# Spatial Hi-C, mouse embryo / brain (Chen, Guo et al. 2026, Nat Methods, doi:10.1038/s41592-026-03218-3).
# Processed data: Zenodo 17961135 (CC-BY-4.0): one per-read cis BEDPE (E13.5 embryo) and Seurat objects (.qs)
# of the spatial Hi-C (ssA/B scores) and spatial RNA; raw reads are in GSA CRA016676 (not fetched).
# The authors' code (Zenodo 22144954, MIT) holds the spot barcode tables used to place spots.
_ZENODO_CHEN2026 = "https://zenodo.org/records/17961135/files"
_SPATIAL_HIC_CHEN2026 = {  # file -> md5
    "cis.E13all.R1_hicup_dedup.sort.bedpe.gz": "55599bdd125b3bfeced8fd12fbb4b5f1",
    "seurat_Cere_hic_adult_final_20um.qs": "1834c5d50219f5309f1e2f3391d1fcec",
    "seurat_Cere_rna_adult_final_20um.qs": "1514a14101c11d44e39a838ca818eb2f",
    "seurat_E13_hic_embyro_final_50um.qs": "8d47fd98cab885abac9fc1ffa41da0b6",
    "seurat_E13_rna_embyro_final_50um.qs": "7e1304bf60cf83999ff67f361945b9ff",
    "seurat_brain_hic_cortex_final_10um.qs": "72299bf9f7e70640e4b09c5efabf84af",
    "seurat_brain_hic_embyro_final_10um.qs": "8715a7429a7fb5564fa0f2d47e55528d",
    "seurat_brain_hic_embyro_final_20um.qs": "da104d556cc13b56fca612a6dce6cbf2",
    "seurat_brain_hic_hippo_final_10um.qs": "3b10fd9655ffa36b0ab2d0883edb4078",
    "seurat_brain_rna_cortex_final_10um.qs": "fd04a9e6fbb95c7a4ab98cdbc5dab8b4",
    "seurat_brain_rna_embyro_final_10um.qs": "cb18bb1b342d25c553cb8eebb66cb28d",
    "seurat_brain_rna_empyro_final_20um.qs": "93aeee208ebadc52a9f6976510d40dcb",
    "seurat_brain_rna_hippo_final_10um.qs": "6d1d25f9955bebfe8349c61f8c42feaa",
}
_CHEN2026_CODE = ("spatial_hic_chen2026/raw/code/Spatial-Hi-C-v1.0.0.zip",
                  "https://zenodo.org/records/22144954/files/Monie820/Spatial-Hi-C-v1.0.0.zip",
                  "17ddcfbb9636dda9fb2dedb0fa8edc1f")

_SPATIAL_HICRNA = [
    "GSM9320916_mouse_brain_r1_HIC_RNA.h5ad.gz", "GSM9320917_mouse_brain_r1_Image.tar.gz",
    "GSM9320917_mouse_brain_r1_RNA.tar.gz", "GSM9320919_mouse_brain_r2_Image.tar.gz",
    "GSM9320919_mouse_brain_r2_RNA.tar.gz", "GSM9320920_mouse_embryo_E11.5_HIC_RNA.h5ad.gz",
    "GSM9320921_mouse_embryo_E11.5_Image.tar.gz", "GSM9320921_mouse_embryo_E11.5_RNA.tar.gz",
    "GSM9320922_Human_melanoma_HIC_RNA.h5ad.gz", "GSM9320923_Human_melanoma_Image.tar.gz",
    "GSM9320923_Human_melanoma_RNA.tar.gz", "GSM9320924_Human_melanoma_ATAC_Image.tar.gz",
    "GSM9738330_Human_melanoma_RNA_r2.tar.gz", "GSM9738330_Human_melanoma_r2_Image.tar.gz",
    "GSM9738332_mouse_embryo_E13.5_RNA_r1.tar.gz", "GSM9738332_mouse_embryo_E13.5_r1_Image.tar.gz",
    "GSM9738334_mouse_embryo_E13.5_RNA_r2.tar.gz", "GSM9738334_mouse_embryo_E13.5_r2_Image.tar.gz",
]

_BIL_MERFISH_MOP = (
    "https://download.brainimagelibrary.org/cf/1c/cf1c1a431ef8d021/processed_data"
)

# ---- matched-modality comparison (benchmarks/screcon/matched.py) ----
# Nagano et al. 2017 (Nature 547:61) haploid mESC single-cell Hi-C: the authors' per-cell fend-pair
# tables (schic2 S3 bucket, linked from github.com/tanaylab/schic2); fend coordinates (mm9) only ship
# inside the 5 GB misha database archive, so GATC.fends is streamed out of it (nothing else is kept).
_SCHIC2 = "https://schic2.s3.eu-west-1.amazonaws.com"
_GSE94489 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE94nnn/GSE94489/suppl"
# Tan et al. 2021 (Cell 184:741) Dip-C, adult cortex (P56 / P309 / P347, >= 100 k contacts): 510 cells
# listed in tan2021_adult_cortex_cells.tsv next to this module (a copy of benchmarks/screcon/data/...);
# per-GSM files of GSE146397.
_TAN_CELLS = Path(__file__).resolve().parent / "tan2021_adult_cortex_cells.tsv"
_TAN_SUFFIXES = ("contacts.pairs", "impute.pairs", "20k.1.clean.3dg", "20k.2.clean.3dg", "20k.3.clean.3dg",
                 "20k.4.clean.3dg", "20k.5.clean.3dg")


def _tan2021_files() -> list[tuple[str, str]]:
    if not _TAN_CELLS.exists():
        return []
    rows = [line.rstrip("\n").split("\t") for line in _TAN_CELLS.open()][1:]
    return [(f"tan2021_cortex/cells/{name}/{name}.{suf}.txt.gz", _gsm(f"{gsm}_{name}.{suf}.txt.gz"))
            for gsm, name, *_ in rows for suf in _TAN_SUFFIXES]


_TAKEI_BRAIN = "https://zenodo.org/records/4708112/files"

# Tan et al. 2018 (Science 361:924) Dip-C, GM12878 (GEO GSE117876): 17 cells.  Per cell the hickit
# re-processing (GSM3314359 + k - 1: tarball with the imputed phased pairs and hickit's 3dg) and the
# published Dip-C structures (impute3.round4.clean.3dg of the "Cell k" / "Cell k-1" GSM, plus its rep1 /
# rep2 replicate runs).  Cells 10-17 were sequenced in two libraries; the files sit on the "-1" GSM.
_TAN18_DIPC_GSM = [3271347 + k for k in range(9)] + [3271356 + 2 * k for k in range(8)]


# Wu et al. 2025 (Nat Genet, doi:10.1038/s41588-025-02247-6) scMicro-C, GM12878 (GEO GSE281150 SuperSeries,
# scMicro-C SubSeries GSE192759, 355 cells, hg38).  The 12 cells with the largest hickit phased-pairs files
# (GEO filelist.txt, 2026-10-04; contacts counted after download) -- the deepest public diploid single-cell
# data with phase columns.  Per cell: ``GSM<id>_cell_<nnn>.impute.pairs.gz`` (hickit pairs, phase0 / phase1
# + phase_prob00..11).  The authors' hickit structures (5 / 10 / 20 kb .3dg) exist only inside the 102 GB
# series tarball; it is streamed once and only these cells' members are kept.
_GSE192759 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE192nnn/GSE192759/suppl"
_WU25_CELLS = [("GSM5764669", 35), ("GSM5764658", 24), ("GSM5764954", 320), ("GSM5764660", 26),
               ("GSM5764662", 28), ("GSM5764651", 17), ("GSM5764681", 47), ("GSM5764683", 49),
               ("GSM5764666", 32), ("GSM5764661", 27), ("GSM5764648", 14), ("GSM5764685", 51)]
_WU25_3DG_RE = r"cell_(" + "|".join(f"{n:03d}" for _, n in _WU25_CELLS) + r")(?![0-9])"


def _tan2018_files() -> list[tuple[str, str]]:
    # GEO has no hickit re-processing for cells 4, 8 and 16, and no Dip-C structure for cell 8
    out = []
    for k in range(1, 18):
        cell = f"gm12878_{k:02d}"
        if k not in (4, 8, 16):
            hick = f"GSM{3314358 + k}_{cell}.tar.gz"
            out.append((f"tan2018_gm12878/{hick}", _gsm(hick)))
        if k == 8:
            continue
        g = f"GSM{_TAN18_DIPC_GSM[k - 1]}"
        for pre in ("", "rep1_", "rep2_"):
            name = f"{g}_{pre}{cell}.impute3.round4.clean.3dg.txt.gz"
            out.append((f"tan2018_gm12878/{name}", _gsm(name)))
        # Dip-C's contacts after its 3-D phase imputation (4 rounds): phases inferred from the structure
        name = f"{g}_{cell}.impute3.round4.con.txt.gz"
        out.append((f"tan2018_gm12878/{name}", _gsm(name)))
    return out


DATASETS = {
    "takei": {
        "filename": "4DNFIHF3JCBY.csv",
        "url": (
            "https://4dn-open-data-public.s3.amazonaws.com/"
            "fourfront-webprod/wfoutput/"
            "e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv"
        ),
        "md5": {
                "4DNFIHF3JCBY.csv": "c2f5a8db66bfc5ba9cbe6870b415aaa1"},
        "default": True,
        "size_mb": 22,
        "description": "Takei 2021 mESC FOF-CT chromatin tracing",
    },
    # Takei 2021 mESC DNA seqFISH+ at 1 Mb (2,460 loci genome-wide), replicate 1;
    # both homologs per (cell, chromosome) trace.  Single-cell Hi-C simulation truth
    # (benchmarks/screcon).
    "takei2021_1mb": {
        "filename": "4DNFIFLJGGNR.csv",
        "url": (
            "https://4dn-open-data-public.s3.amazonaws.com/"
            "fourfront-webprod/wfoutput/"
            "8189709b-f1e7-4f0b-bf68-89eb9fd0afcf/4DNFIFLJGGNR.csv"
        ),
        "md5": {"4DNFIFLJGGNR.csv": "da9826551f13f944815fe35a33a8e9c1"},
        "size_mb": 47,
        "default": False,
        "description": "Takei 2021 mESC FOF-CT 1 Mb genome-wide tracing (4DN 4DNFIFLJGGNR)",
    },
    "seqfish": {
        "filename": "DNAseqFISH+.zip",
        "url": (
            "https://zenodo.org/records/3735329/files/"
            "DNAseqFISH%2B.zip?download=1"
        ),
        "md5": {
                "DNAseqFISH+.zip": "c4e7b23df669bbc7ef9b1436712b4a2c"},
        "default": True,
        "size_mb": 144,
        "description": "Takei 2021 raw seqFISH+ spot detections",
    },
    "bintu_imr90": {
        "filename": "IMR90_chr21-18-20Mb.csv",
        "url": (
            "https://raw.githubusercontent.com/BogdanBintu/"
            "ChromatinImaging/master/Data/IMR90_chr21-18-20Mb.csv"
        ),
        "md5": {
                "IMR90_chr21-18-20Mb.csv": "9ccf988c6e0c90967d152b88741b0598"},
        "default": True,
        "size_mb": 2,
        "description": "Bintu 2018 IMR90 chr21 chromatin tracing",
    },
    # scHiCAR mouse brain (Wei et al. 2026, Nat Biotechnol), GEO GSE305439.
    "schicar_rna": {
        "files": [
            (f"schicar_mop/raw/GSE305439/{name}", f"{_GSE305439}/{name}")
            for name in (
                "GSE305439_RNA.matrix.mtx.gz",
                "GSE305439_RNA.barcodes.tsv.gz",
                "GSE305439_RNA.features.tsv.gz",
                "GSE305439_mouse_brain_scHiCAR_1_RNA_metadata.txt.gz",
            )
        ],
        "size_mb": 61,
        "description": "scHiCAR mouse brain RNA matrix + cell metadata (GSE305439)",
    },
    "schicar_dna": {
        "files": [
            (f"schicar_mop/raw/GSE305439/{name}", f"{_GSE305439}/{name}")
            for name in ("GSE305439_DNA.dedup.pairs.gz",)
        ],
        "size_mb": 1470,
        "default": False,
        "description": "scHiCAR mouse brain contact pairs (GSE305439)",
    },
    # ATAC fragments + UCSC mm10 refGene (gene windows for ATAC gene activity)
    "schicar_atac": {
        "files": [
            ("schicar_mop/raw/GSE305439/GSE305439_DNA.ATAC.tsv.gz",
             f"{_GSE305439}/GSE305439_DNA.ATAC.tsv.gz"),
            ("schicar_mop/raw/mm10.refGene.gtf.gz",
             "https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz"),
        ],
        "size_mb": 1366,
        "default": False,
        "description": "scHiCAR mouse brain ATAC fragments (GSE305439) + UCSC mm10 refGene GTF",
    },
    # Takei et al. 2025 (Nature) cerebellum DNA seqFISH+, rep 1, all FOVs
    # (Zenodo 7693825, CC-BY-4.0).  Consumed by build_takei2025_cerebellum.py
    # and benchmarks/fig2/.  The locus map + clustering CSVs come from the
    # CaiGroup GitHub repo (same URLs as build_takei2025_fov0.py).
    "takei2025_cerebellum": {
        "files": [
            ("takei2025_cerebellum/cerebellum_rep1.tar.gz",
             "https://zenodo.org/records/7693825/files/cerebellum_rep1.tar.gz"),
            ("takei2025_cerebellum/LC1-100k-09022022-mm10-25kb-meta.csv",
             "https://media.githubusercontent.com/media/CaiGroup/"
             "dna-seqfish-plus-multi-omics/main/data/annotation/"
             "LC1-100k-09022022-mm10-25kb-meta.csv"),
            ("takei2025_cerebellum/cerebellum_mRNA_cluster_nuc_vol_filtered.csv",
             "https://media.githubusercontent.com/media/CaiGroup/"
             "dna-seqfish-plus-multi-omics/main/data/cerebellum/clustering/"
             "100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv"),
        ],
        "md5": {"takei2025_cerebellum/cerebellum_rep1.tar.gz":
                "758ebb152de837493a9c4d84471d62b4"},
        "size_mb": 2854,
        "default": False,
        "description": "Takei 2025 cerebellum DNA seqFISH+ rep 1, all FOVs (Zenodo 7693825)",
    },
    "takei2025_cerebellum_rep2": {
        "files": [
            ("takei2025_cerebellum/cerebellum_rep2.tar.gz",
             "https://zenodo.org/records/7693825/files/cerebellum_rep2.tar.gz"),
            ("takei2025_cerebellum/LC1-100k-09022022-mm10-25kb-meta.csv",
             "https://media.githubusercontent.com/media/CaiGroup/"
             "dna-seqfish-plus-multi-omics/main/data/annotation/"
             "LC1-100k-09022022-mm10-25kb-meta.csv"),
            ("takei2025_cerebellum/cerebellum_mRNA_cluster_nuc_vol_filtered.csv",
             "https://media.githubusercontent.com/media/CaiGroup/"
             "dna-seqfish-plus-multi-omics/main/data/cerebellum/clustering/"
             "100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv"),
        ],
        "md5": {"takei2025_cerebellum/cerebellum_rep2.tar.gz":
                "411edf7e4ebcfaf6e6619c5c8d30c415"},
        "size_mb": 5290,
        "default": False,
        "description": "Takei 2025 cerebellum DNA seqFISH+ rep 2, all FOVs (Zenodo 7693825)",
    },
    # the RNA seqFISH spot tables of every Takei 2025 sample (aggregated into the linked AnnData of
    # uchrom.io.load_takei2025_cerebellum)
    "takei2025_rna": {
        "files": [("takei2025_cerebellum/transcriptomic-data.zip",
                   "https://zenodo.org/records/7693825/files/transcriptomic-data.zip")],
        "md5": {"takei2025_cerebellum/transcriptomic-data.zip": "c29594d9ed0f4dfea67c0140c56050a1"},
        "size_mb": 462,
        "default": False,
        "description": "Takei 2025 RNA seqFISH spot tables, all samples (Zenodo 7693825)",
    },
    # Liu et al. 2025 (Sci Adv) DNA-MERFISH of 2,000 loci in mouse MOp, WT,
    # 4DN experiment 4DNEXBUVZYLI (set 4DNESMTNNB3N): the largest released
    # wild-type FOF-CT core table on the 4DN portal + its cell table.
    "liu2025_mop": {
        "files": [
            ("liu2025_mop/4DNFID46OABK.csv",
             "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/"
             "wfoutput/7c153998-3e92-4dbe-8e35-7a09570e6ed3/4DNFID46OABK.csv"),
            ("liu2025_mop/4DNFICX8IVEK.csv",
             "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/"
             "wfoutput/ad72715d-57cc-4d68-8ddb-536b94ed9bb0/4DNFICX8IVEK.csv"),
        ],
        "md5": {"liu2025_mop/4DNFID46OABK.csv": "e2234c8d77d933a1b737c2fec75a4abb",
                "liu2025_mop/4DNFICX8IVEK.csv": "f66afc5a37f24a876ccf26701728e5e5"},
        "size_mb": 1701,
        "default": False,
        "description": "Liu 2025 mouse MOp DNA-MERFISH FOF-CT core + cell table (4DN)",
    },
    # ---- Fig. 3 (u-chrom-paper/manuscripts/full/figures/fig3/PLAN.md): bridges between contacts and geometry ----
    # Stevens et al. 2017 (Nature 544:59) haploid mESC single-cell Hi-C, GEO
    # GSE80280: per-cell contact pairs + the paper's own 10-model 100 kb
    # structures (.pdb) -- the NucDynamics reference.  GEO gives no md5.
    "stevens2017": {
        "files": [
            (f"stevens2017_mesc/{gsm}_Cell_{n}_{kind}",
             f"https://ftp.ncbi.nlm.nih.gov/geo/samples/{gsm[:7]}nnn/{gsm}/suppl/{gsm}_Cell_{n}_{kind}")
            for n, gsm in _STEVENS
            for kind in ("contact_pairs.txt.gz", "genome_structure_model.pdb.gz")
        ],
        "md5": {
                "stevens2017_mesc/GSM2219497_Cell_1_contact_pairs.txt.gz": "5d8bbde8f8d89f4d3e88fdb627f1d451",
                "stevens2017_mesc/GSM2219497_Cell_1_genome_structure_model.pdb.gz": "b12b1a0073be5658087125907926ff7d",
                "stevens2017_mesc/GSM2219498_Cell_2_contact_pairs.txt.gz": "de5abfd3c4f63bcf7fd764ac316548c4",
                "stevens2017_mesc/GSM2219498_Cell_2_genome_structure_model.pdb.gz": "61dd368a724ed12ff9857ae440c38e5e",
                "stevens2017_mesc/GSM2219499_Cell_3_contact_pairs.txt.gz": "46f6719d5bcbe116eda7ad3d2bdd13b5",
                "stevens2017_mesc/GSM2219499_Cell_3_genome_structure_model.pdb.gz": "e8dc8a5c34e251fda4e1257556a851ec",
                "stevens2017_mesc/GSM2219500_Cell_4_contact_pairs.txt.gz": "65833188550102409dc38c938ac508de",
                "stevens2017_mesc/GSM2219500_Cell_4_genome_structure_model.pdb.gz": "06532a28bbb9f7b6ec37e283e9be8528",
                "stevens2017_mesc/GSM2219501_Cell_5_contact_pairs.txt.gz": "43f156069bebda79b50c453de8421814",
                "stevens2017_mesc/GSM2219501_Cell_5_genome_structure_model.pdb.gz": "872fa2034be918a7e222755b9386dcd0",
                "stevens2017_mesc/GSM2219502_Cell_6_contact_pairs.txt.gz": "524f40396e5a36801e0ad79592e2afb8",
                "stevens2017_mesc/GSM2219502_Cell_6_genome_structure_model.pdb.gz": "eb0fe6c6f9ef75609c4a28a9e051fac3",
                "stevens2017_mesc/GSM2219503_Cell_7_contact_pairs.txt.gz": "87043180bb03d79b8534378a0be57689",
                "stevens2017_mesc/GSM2219503_Cell_7_genome_structure_model.pdb.gz": "bdfea7c0f62c9a16e4d952aaaa8a63eb",
                "stevens2017_mesc/GSM2219504_Cell_8_contact_pairs.txt.gz": "8c7aa644db31f89f2c8c753be451d949",
                "stevens2017_mesc/GSM2219504_Cell_8_genome_structure_model.pdb.gz": "64ef4fa840883265f0fe2d7267507a36"},
        "size_mb": 43,
        "default": True,
        "fig3": True,
        "description": "Stevens 2017 mESC scHi-C contacts + published structures, 8 cells (GEO GSE80280)",
    },
    # Bintu et al. 2018 (Science 362:eaau1783) chr21:28-30 Mb tracing in IMR90
    # and K562 (the 18.6-20.6 Mb IMR90 file is the "bintu_imr90" entry above).
    "bintu2018": {
        "files": [
            (f"bintu2018/{name}", f"{_BINTU}/{name}")
            for name in ("IMR90_chr21-28-30Mb.csv", "K562_chr21-28-30Mb.csv")
        ],
        "size_mb": 28,
        "default": False,
        "fig3": True,
        "description": "Bintu 2018 chr21:28-30 Mb tracing, IMR90 + K562 (GitHub)",
    },
    # Su et al. 2020 (Cell 182:1641) IMR90 whole-chr21 tracing (651 x 50 kb)
    # + the authors' Rao 2014 Hi-C summed into the imaged bins (Zenodo 3928890).
    "su2020_chr21": {
        "files": [
            ("su2020_imr90/chromosome21.tsv", f"{_SU2020}/chromosome21.tsv?download=1"),
            ("su2020_imr90/Hi-C_contacts_chromosome21.tsv",
             f"{_SU2020}/Hi-C_contacts_chromosome21.tsv?download=1"),
            ("su2020_imr90/README_August_2020.txt", f"{_SU2020}/README_August%202020.txt?download=1"),
        ],
        "md5": {"su2020_imr90/chromosome21.tsv": "170d9d8b081edaa5f4ccaad8aad25eff",
                "su2020_imr90/Hi-C_contacts_chromosome21.tsv": "7842ef3149e139fe08c6de7df13b3084",
                "su2020_imr90/README_August_2020.txt": "a93629f38fcc11acdb46ced5fc74bee1"},
        "size_mb": 262,
        "default": True,
        "fig3": True,
        "description": "Su 2020 IMR90 chr21 chromatin tracing + binned Hi-C (Zenodo 3928890)",
    },
    # Su et al. 2020 genome-scale DNA-MERFISH (Zenodo 3928890, CC-BY-4.0): 1,041 loci x 1,787 IMR90
    # cells, both homologs resolved, distance to lamina; + the authors' Rao 2014 Hi-C summed into
    # 500 kb bins centred on the loci (2.8 MB, also checked in).  Bulk deconvolution benchmark truth.
    "su2020_genome": {
        "files": [
            ("su2020_imr90/genomic-scale.tsv", f"{_SU2020}/genomic-scale.tsv?download=1"),
            ("su2020_imr90/Hi-C_contacts_genome-scale.tsv",
             f"{_SU2020}/Hi-C_contacts_genome-scale.tsv?download=1"),
            ("su2020_imr90/README_August_2020.txt", f"{_SU2020}/README_August%202020.txt?download=1"),
        ],
        "md5": {"su2020_imr90/genomic-scale.tsv": "a1d79c2ba047c20411547431a728b621",
                "su2020_imr90/Hi-C_contacts_genome-scale.tsv": "13e3607efab2d889e82b10f36e71ce5a",
                "su2020_imr90/README_August_2020.txt": "a93629f38fcc11acdb46ced5fc74bee1"},
        "size_mb": 203,
        "default": False,
        "description": "Su 2020 IMR90 genome-scale DNA-MERFISH (1,041 loci, homologs) + binned Hi-C (Zenodo 3928890)",
    },
    # Rao et al. 2014 IMR90 in situ Hi-C reprocessed by 4DN on GRCh38 (set 4DNES1ZEJNRU): the
    # whole-genome input of the bulk deconvolution benchmark (20 kb built from the 10 kb level).
    "rao2014_imr90_4dn": {
        "files": [("rao2014_imr90/4DNFIR1JDZH7.mcool",
                   "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                   "d10655ab-5bdf-4449-ab5a-82188af29868/4DNFIR1JDZH7.mcool")],
        "md5": {"rao2014_imr90/4DNFIR1JDZH7.mcool": "f91b77fa61acdc58360911c80b007646"},
        "size_mb": 4640,
        "default": False,
        "description": "Rao 2014 IMR90 in situ Hi-C, 4DN GRCh38 mcool (4DNFIR1JDZH7; Sherlock only)",
    },
    # Bonev et al. 2017 mESC Hi-C (G1-sorted ES), 4DN GRCm38 mcool (set 4DNESDXUWBD9) - Takei 2021's
    # comparison Hi-C; whole-genome input of the mESC deconvolution benchmark.
    "bonev2017_mesc_4dn": {
        "files": [("bonev2017_mesc/4DNFIC21MG3U.mcool",
                   "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                   "2b448d99-d3fb-4bb9-a126-386ccb99a6fd/4DNFIC21MG3U.mcool")],
        "md5": {"bonev2017_mesc/4DNFIC21MG3U.mcool": "dda4ed67a1179f917721fb81b1adebe0"},
        "size_mb": 12551,
        "default": False,
        "description": "Bonev 2017 mESC Hi-C, 4DN mm10 mcool (4DNFIC21MG3U; Sherlock only)",
    },
    # GEM-FISH (Abbas et al. 2019, Nat Commun 10:2049) repo data, MIT licence,
    # pinned commit: Wang et al. 2016 FISH of chr20/21/22 TADs in IMR90, the
    # hg19 TAD windows, Rao 2014 IMR90 chr20 / per-TAD 5 kb Hi-C, and the
    # paper's final 5 kb models (reference structures).
    "abbas2019_gemfish": {
        "files": [
            (f"abbas2019_gemfish/{name}", f"{_GEMFISH}/{name}")
            for name in ("complete_example.zip", "GEM-FISH_TAD-level-resolution.zip",
                         "GEM-FISH_TAD-conformations.zip", "validation_tests_final_models.zip")
        ],
        "md5": {"abbas2019_gemfish/complete_example.zip": "6af7dd785744d594ac8a925ffaaabb3b",
                "abbas2019_gemfish/GEM-FISH_TAD-level-resolution.zip": "0cad10dd88d378ea15be2583873bdac4",
                "abbas2019_gemfish/GEM-FISH_TAD-conformations.zip": "7a9c04dd4e911057c0caec235444f919",
                "abbas2019_gemfish/validation_tests_final_models.zip": "31d5e7164675680b0dcfbf3183a02fad"},
        "size_mb": 40,
        "default": False,
        "fig3": True,
        "description": "GEM-FISH repo data: Wang 2016 FISH, TADs, Hi-C, final models (GitHub, MIT)",
    },
    # 4DN 4DNFI4QQPDMR: K562 in situ Hi-C (Ray et al. 2019, set 4DNESU95RUNO).
    # K562_chr21_30kb.cool was cut from this file -- it is K562, not IMR90.
    "ray2019_k562": {
        "files": [("ray2019_k562/4DNFI4QQPDMR.mcool",
                   "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                   "1c856462-1e76-4850-bfa6-defcf1524d42/4DNFI4QQPDMR.mcool")],
        "md5": {"ray2019_k562/4DNFI4QQPDMR.mcool": "84f4e708e2e7b55078b670ed4b8db709"},
        "size_mb": 849,
        "default": False,
        "description": "K562 in situ Hi-C mcool (4DN 4DNFI4QQPDMR; source of K562_chr21_30kb.cool)",
    },
    # BICCN MERFISH mouse MOp atlas (Zhang et al. 2021, Nature), BIL doi:10.35077/g.21.
    "merfish_mop": {
        "files": [
            (f"schicar_mop/raw/merfish_mop/{name}", f"{_BIL_MERFISH_MOP}/{name}")
            for name in ("counts.h5ad", "cell_labels.csv")
        ],
        "size_mb": 332,
        "description": "MERFISH mouse MOp cell x gene counts + cell labels (BIL g.21)",
    },
    "spatial_atac_hic": {
        "files": [(f"spatial_atac_hic/raw/GSE307620/{n}", _gsm(n)) for n in _SPATIAL_ATAC_HIC],
        "size_mb": 9500,
        "default": False,
        "description": "Spatial ATAC-Hi-C mouse brain, 2 sections: ATAC + Hi-C fragments, spots, images (GSE307620)",
    },
    # Nagano 2017 diploid serum mESC: the single cells SnapHiC called loops from (Yu et al. 2021); the GATC fends
    # and the mm9 -> mm10 chain go where nagano2017_hap puts them (shared, fetched once)
    "nagano2017_dip_serum": {
        "files": [
            ("nagano2017_dip/schic_hyb_1CDS1_adj_files.tar.gz", f"{_SCHIC2}/schic_hyb_1CDS1_adj_files.tar.gz"),
            ("nagano2017_dip/schic_hyb_1CDS2_adj_files.tar.gz", f"{_SCHIC2}/schic_hyb_1CDS2_adj_files.tar.gz"),
            ("nagano2017_dip/GSE94489_serum_diploids_features_table.txt.gz",
             f"{_GSE94489}/GSE94489_serum_diploids_features_table.txt.gz"),
            ("nagano2017_hap/mm9ToMm10.over.chain.gz",
             "https://hgdownload.soe.ucsc.edu/goldenPath/mm9/liftOver/mm9ToMm10.over.chain.gz"),
        ],
        "md5": {"nagano2017_dip/schic_hyb_1CDS1_adj_files.tar.gz": "fa1f498f25c3ee19788583b4bc2975ea",
                "nagano2017_dip/schic_hyb_1CDS2_adj_files.tar.gz": "fa594c9750f16da95e13d97edf6b6c15",
                "nagano2017_dip/GSE94489_serum_diploids_features_table.txt.gz": "f0b506709c078f5ce5252ae4ed17a27a"},
        "extract": [("nagano2017_hap/GATC.fends", f"{_SCHIC2}/schic2_mm9_db.tar.gz", "seq/redb/GATC.fends")],
        "size_mb": 1965,
        "default": False,
        "description": "Nagano 2017 diploid serum mESC scHi-C fend pairs (SnapHiC's cells) + mm9 GATC fends + mm9->mm10 chain",
    },
    # SnapHiC (Yu et al. 2021, Nat Methods 18:1056): the paper's source data — its loops by number of cells
    # (MOESM4) and the mESC reference loop lists (MOESM6) — and the regions SnapHiC excludes (GitHub, GPL-3.0)
    "yu2021_snaphic": {
        "files": [(f"yu2021_snaphic/41592_2021_1231_MOESM{k}_ESM.xlsx",
                   "https://static-content.springer.com/esm/art%3A10.1038%2Fs41592-021-01231-2/MediaObjects/"
                   f"41592_2021_1231_MOESM{k}_ESM.xlsx") for k in (4, 6)],
        "md5": {"yu2021_snaphic/41592_2021_1231_MOESM4_ESM.xlsx": "9e7359602088134e7dc72b17b865ec03",
                "yu2021_snaphic/41592_2021_1231_MOESM6_ESM.xlsx": "bf83659f56dda7c78be08c8a634bea50"},
        "size_mb": 34,
        "default": False,
        "description": "SnapHiC paper source data: loops from 10-742 mES cells, mESC reference loop lists (xlsx)",
    },
    "snaphic_filter_regions": {
        "files": [(f"snaphic/{g}_filter_regions.txt",
                   "https://raw.githubusercontent.com/HuMingLab/SnapHiC/782dc2bc7e5a9e3c376bac4a61666a1a02d061b8/"
                   f"ext/{g}_filter_regions.txt") for g in ("mm10", "hg19")],
        "md5": {"snaphic/mm10_filter_regions.txt": "2a951b44284a6edcfaee9d44e0e1d3a7",
                "snaphic/hg19_filter_regions.txt": "af7bec820c35f8fb773175ca255a1ada"},
        "size_mb": 4,
        "default": False,
        "description": "SnapHiC's excluded 10-kb bins (low mappability, blacklist), mm10 + hg19",
    },
    "nagano2017_hap": {
        "files": [
            ("nagano2017_hap/schic_hap_serum_adj_files.tar.gz", f"{_SCHIC2}/schic_hap_serum_adj_files.tar.gz"),
            ("nagano2017_hap/schic_hap_2i_adj_files.tar.gz", f"{_SCHIC2}/schic_hap_2i_adj_files.tar.gz"),
            ("nagano2017_hap/GSE94489_haploids_features_table.txt.gz",
             f"{_GSE94489}/GSE94489_haploids_features_table.txt.gz"),
            ("nagano2017_hap/GSE94489_README.txt", f"{_GSE94489}/GSE94489_README.txt"),
            ("nagano2017_hap/mm9ToMm10.over.chain.gz",
             "https://hgdownload.soe.ucsc.edu/goldenPath/mm9/liftOver/mm9ToMm10.over.chain.gz"),
        ],
        # (destination, archive URL, member path suffix): streamed, only the member is written
        "extract": [("nagano2017_hap/GATC.fends", f"{_SCHIC2}/schic2_mm9_db.tar.gz", "seq/redb/GATC.fends")],
        "size_mb": 1386,
        "default": False,
        "description": "Nagano 2017 haploid mESC scHi-C fend pairs (2i + serum) + mm9 GATC fends + mm9->mm10 chain",
    },
    "takei2021_brain": {
        "files": [(f"takei2021_brain/{n}", f"{_TAKEI_BRAIN}/{n}?download=1") for n in (
            "TableS5_brain_RNA_profiles_2762cells.csv",
            "TableS7_brain_DNAseqFISH_1Mb_voxel_coordinates_2762cells.csv",
            "TableS8_brain_DNAseqFISH_25kb_voxel_coordinates_2762cells.csv",
            "TableS10-median-radial-score-per-celltype-1Mb-resolution.csv")],
        "size_mb": 597,
        "default": False,
        "description": "Takei 2021 Science mouse cortex DNA seqFISH+ 1 Mb / 25 kb spots, RNA, radial scores (Zenodo 4708112)",
    },
    "tan2018_gm12878": {
        "files": _tan2018_files,
        "size_mb": 700,
        "default": False,
        "description": "Tan 2018 Dip-C GM12878, 17 cells: hickit imputed phased pairs + 3dg, Dip-C clean 3dg x 3 (GEO GSE117876)",
    },
    "wu2025_scmicroc": {
        "files": [(f"wu2025_scmicroc/{g}_cell_{n:03d}.impute.pairs.gz", _gsm(f"{g}_cell_{n:03d}.impute.pairs.gz"))
                  for g, n in _WU25_CELLS],
        # (destination dir, archive URL, member-name regex): one streamed pass, matching members kept
        "extract_many": [("wu2025_scmicroc/3dg", f"{_GSE192759}/GSE192759_5kb_10kb_20kb_3dg_files.tar.gz",
                          _WU25_3DG_RE)],
        "size_mb": 3100,
        "default": False,
        "description": "Wu 2025 scMicro-C GM12878, 12 deepest cells: hickit phased pairs + 5/10/20 kb 3dg (GSE192759)",
    },
    "tan2021_cortex": {
        "files": _tan2021_files,
        "size_mb": 13000,
        "default": False,
        "description": "Tan 2021 Dip-C adult cortex, 510 cells: contacts / impute pairs + 5 clean 3dg (GEO GSE146397)",
    },
    "spatial_hicrna": {
        "files": [(f"spatial_hicrna/raw/GSE311199/{n}", _gsm(n)) for n in _SPATIAL_HICRNA],
        "size_mb": 2300,
        "default": False,
        "description": "Spatial Hi-C-RNA brain / embryo / melanoma: processed h5ad, RNA, images (GSE311199)",
    },
    "spatial_hic_chen2026": {
        "files": [(f"spatial_hic_chen2026/raw/zenodo17961135/{n}", f"{_ZENODO_CHEN2026}/{n}")
                  for n in _SPATIAL_HIC_CHEN2026] + [_CHEN2026_CODE[:2]],
        "md5": {**{f"spatial_hic_chen2026/raw/zenodo17961135/{n}": m for n, m in _SPATIAL_HIC_CHEN2026.items()},
                _CHEN2026_CODE[0]: _CHEN2026_CODE[2]},
        "size_mb": 15920,
        "default": False,
        "description": "Spatial Hi-C mouse embryo / brain (Chen et al. 2026): E13.5 cis BEDPE, Seurat .qs, code (Zenodo)",
    },
    "hires2023_meta": {
        "files": [(f"hires2023/raw/GSE223917/{n}", _gse("GSE223917", n)) for n in _HIRES_META],
        "size_mb": 70,
        "default": False,
        "description": "HiRES cell metadata + RNA UMI counts, embryo and brain (GSE223917)",
    },
    "hires2023": {
        "files": lambda: [(f"hires2023/raw/GSE223917/cells/{n}", _gsm(n))
                          for n in _geo_filelist("GSE223917", r"\.(pairs\.gz|20k(\.0\.clean)?\.3dg\.txt\.gz)$")],
        "size_mb": 76000,
        "default": False,
        "parallel": 2,
        "description": "HiRES per-cell contact pairs + 20 kb structures, 7,895 cells (GSE223917)",
    },
    "dschic2025_aging": {
        "files": [(f"dschic2025/raw/GSE285812/{n}", _gsm(n)) for n in _DSCHIC_AGING],
        "size_mb": 44000,
        "default": False,
        "description": "dscHi-C mouse cortex at 3 / 12 / 23 months: contacts + metadata (GSE285812)",
    },
    "gageseq2024": {
        "files": [(f"gageseq2024/raw/GSE238001/{n}", _gsm(n)) for n in _GAGESEQ] + [
            # the authors' cell-type annotation (GitHub ma-compbio/GAGE-seq, MIT), pinned commit
            (f"gageseq2024/raw/github/{n}", f"https://raw.githubusercontent.com/ma-compbio/GAGE-seq/"
                                            f"360cea7a17d232f0ea24b3a86cf1337e4d7d3740/meta_info/cell_type_annotation/{n}")
            for n in ("meta-Seurat_mBC_complete_mm10_filtered.csv", "meta-python_CD_complete_hg38_filtered.csv")] + [
            # gene symbols of the Ensembl ids of the RNA (Ensembl 98 = the 10x 2020-A references)
            (f"gageseq2024/raw/ensembl98/{n}", f"https://ftp.ensembl.org/pub/release-98/gtf/{sp}/{n}")
            for sp, n in (("mus_musculus", "Mus_musculus.GRCm38.98.gtf.gz"),
                          ("homo_sapiens", "Homo_sapiens.GRCh38.98.gtf.gz"))],
        "size_mb": 38000,
        "default": False,
        "parallel": 2,
        "description": "GAGE-seq mouse cortex + human bone marrow CD34+: contacts + RNA (GSE238001)",
    },
    "unic2025": {
        # Uni-C (Gao et al. 2025, Nat. Commun., doi:10.1038/s41467-025-62215-w), GEO GSE267873: deeply sequenced
        # single cells (GM12878, COLO320DM, PDX and KPC circulating tumour cells, MC38) and bulk libraries,
        # deduplicated contact pairs (GRCh37 / GRCm38); the per-cell VCFs are not fetched
        "files": lambda: [(f"unic2025/raw/GSE267873/{n}", _gsm(n)) for n in _geo_filelist("GSE267873", r"\.pairs\.gz$")],
        "size_mb": 110000,
        "default": False,
        "parallel": 3,
        "description": "Uni-C single-cell and bulk contact pairs, human and mouse (GSE267873)",
    },
    "droplet_hic2024_meta": {
        "files": [(f"droplet_hic2024/raw/GSE253407/{n}", _gse("GSE253407", n)) for n in _DROPLET_META],
        "size_mb": 4,
        "default": False,
        "description": "Droplet Hi-C / Paired Hi-C mouse cortex cell metadata (GSE253407)",
    },
    "droplet_hic2024": {
        "files": [(f"droplet_hic2024/raw/GSE253407/{n}", _gsm(n)) for n in _DROPLET],
        "size_mb": 72000,
        "default": False,
        "parallel": 2,
        "description": "Droplet Hi-C + Paired Hi-C mouse cortex: contacts, barcodes, RNA (GSE253407)",
    },
}


# ---- inputs of the tutorials (besides the entries above) ----
_TAKEI_4DN = "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput"
DATASETS.update({
    # Takei et al. 2021 (Nature 590:344) mESC, 4DN set 4DNESL2AY9CM: the cell table and the nascent RNA
    # spots that accompany the core table "takei" (4DNFIHF3JCBY; same 201 cells)
    "takei_tables": {
        "files": [("4DNFIFINA2U9.csv", f"{_TAKEI_4DN}/c5bafa92-d08b-4e20-84de-6e75103c016d/4DNFIFINA2U9.csv"),
                  ("4DNFIJ52NVDV.csv", f"{_TAKEI_4DN}/4b66ffc5-50e0-4832-99c2-0020c934ff24/4DNFIJ52NVDV.csv")],
        "md5": {
                "4DNFIFINA2U9.csv": "799c25d9bf53ab0104911b47946d9920",
                "4DNFIJ52NVDV.csv": "ef8022344853a82c93b1f59e0129e2e4"},
        "default": True,
        "size_mb": 1,
        "description": "Takei 2021 mESC FOF-CT cell table + RNA spot table (4DN 4DNFIFINA2U9, 4DNFIJ52NVDV)",
    },
    # Kim et al. 2020 (Nat Commun 11:6386) sci-Hi-C, H1 ES + HFF cells at 500 kb (topic-model benchmark)
    "kim2020_scihic": {
        "files": [("kim2020_scihic/H1Esc-HFF.R1.tar.gz",
                   "https://noble.gs.washington.edu/proj/schic-topic-model/data/matrix_files/H1Esc-HFF.R1.tar.gz"),
                  ("kim2020_scihic/H1Esc-HFF.R1.labeled",
                   "https://noble.gs.washington.edu/proj/schic-topic-model/data/matrix_labels/H1Esc-HFF.R1.labeled")],
        "md5": {
                "kim2020_scihic/H1Esc-HFF.R1.tar.gz": "42afd5847a05fc9d00105f3dbdeabdf3",
                "kim2020_scihic/H1Esc-HFF.R1.labeled": "fa4e17e0edb1a8d892b46338217a1c5f"},
        "size_mb": 128,
        "default": True,
        "description": "Kim 2020 sci-Hi-C, H1 ES + HFF (Noble lab)",
    },
    # Huang et al. 2021 (Nat Genet) mESC Sox2 locus ORCA-style tracing at 5 kb with missing loci, as shipped
    # with SnapFISH-IMPUTE (github.com/hyuyu104/SnapFISH-IMPUTE, MIT; pinned commit): coordinates + locus table
    "huang2021_sox2": {
        "files": [(f"huang2021_sox2/{n}", f"https://raw.githubusercontent.com/hyuyu104/SnapFISH-IMPUTE/"
                                          f"7f7f1a703aaf6db98147183588a9da6ee1d1c7be/data/{n}")
                  for n in ("mESC_Sox2_coor_wnan.txt", "mESC_Sox2_ann.txt")],
        "md5": {"huang2021_sox2/mESC_Sox2_coor_wnan.txt": "ab391637b75e412eec39d4082e6e3f8d",
                "huang2021_sox2/mESC_Sox2_ann.txt": "c28b7b7e0f590a424f255388997f54bc"},
        "default": True,
        "size_mb": 7,
        "description": "Huang 2021 mESC Sox2 tracing with missing loci (SnapFISH-IMPUTE data, GitHub)",
    },
    # UCSC mm10: chromosome 19 sequence and the refGene annotation (features tutorial)
    "mm10_chr19": {
        "files": [("genomes/mm10/chr19.fa.gz", "https://hgdownload.soe.ucsc.edu/goldenPath/mm10/chromosomes/chr19.fa.gz")],
        "md5": {"genomes/mm10/chr19.fa.gz": "4394207eabb880eeff44535321d6dd33"},
        "size_mb": 19,
        "default": True,
        "description": "UCSC mm10 chromosome 19 sequence",
    },
    # UCSC hg19 chromosome sequences: GC content to orient Hi-C compartments (A = GC-rich)
    "hg19_chr21": {
        "files": [("genomes/hg19/chr21.fa.gz", "https://hgdownload.soe.ucsc.edu/goldenPath/hg19/chromosomes/chr21.fa.gz")],
        "md5": {"genomes/hg19/chr21.fa.gz": "26cdd5a3a539b63930752604feb2912b"},
        "size_mb": 12,
        "default": False,
        "description": "UCSC hg19 chromosome 21 sequence",
    },
    "hg19_chr1": {
        "files": [("genomes/hg19/chr1.fa.gz", "https://hgdownload.soe.ucsc.edu/goldenPath/hg19/chromosomes/chr1.fa.gz")],
        "md5": {"genomes/hg19/chr1.fa.gz": "e103808b81f7d0a52353dee92d2ff164"},
        "size_mb": 74,
        "default": False,
        "description": "UCSC hg19 chromosome 1 sequence",
    },
    # UCSC whole-genome sequences (bigZips, soft-masked; md5 from the folder's md5sum.txt): the CpG frequency of
    # every bin, the reference of single-cell compartment values (uchrom.strc.comp.single_cell_compartments)
    "mm10_genome": {
        "files": [("genomes/mm10/mm10.fa.gz", "https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/mm10.fa.gz")],
        "md5": {"genomes/mm10/mm10.fa.gz": "db005b65828db31735f384e4c5787be5"},
        "size_mb": 830,
        "default": False,
        "description": "UCSC mm10 whole-genome sequence (bigZips mm10.fa.gz)",
    },
    "hg19_genome": {
        "files": [("genomes/hg19/hg19.fa.gz", "https://hgdownload.soe.ucsc.edu/goldenPath/hg19/bigZips/hg19.fa.gz")],
        "md5": {"genomes/hg19/hg19.fa.gz": "806c02398f5ac5da8ffd6da2d1d5d1a9"},
        "size_mb": 905,
        "default": False,
        "description": "UCSC hg19 whole-genome sequence (bigZips hg19.fa.gz)",
    },
    "hg38_genome": {
        "files": [("genomes/hg38/hg38.fa.gz", "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz")],
        "md5": {"genomes/hg38/hg38.fa.gz": "1c9dcaddfa41027f17cd8f7a82c7293b"},
        "size_mb": 938,
        "default": False,
        "description": "UCSC hg38 whole-genome sequence (bigZips hg38.fa.gz)",
    },
    # UCSC liftOver chain hg38 -> hg19: hg38 single-cell maps next to the hg19 Rao 2014 maps
    "hg38_to_hg19_chain": {
        "files": [("genomes/liftover/hg38ToHg19.over.chain.gz",
                   "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/liftOver/hg38ToHg19.over.chain.gz")],
        "md5": {"genomes/liftover/hg38ToHg19.over.chain.gz": "ff3031d93792f4cbb86af44055efd903"},
        "size_mb": 1.2,
        "default": False,
        "description": "UCSC liftOver chain hg38 -> hg19",
    },
    "mm10_refgene": {
        "files": [("genomes/mm10/mm10.refGene.gtf.gz",
                   "https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz")],
        "md5": {
                "genomes/mm10/mm10.refGene.gtf.gz": "954bb1999f12d10ba61917ecfa430068"},
        "size_mb": 13,
        "default": True,
        "description": "UCSC mm10 refGene gene annotation (GTF)",
    },
    "hg38_refgene": {
        "files": [("genomes/hg38/hg38.refGene.gtf.gz",
                   "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/genes/hg38.refGene.gtf.gz")],
        "md5": {"genomes/hg38/hg38.refGene.gtf.gz": "a35c6a276a5cf1d9f200266a82176897"},
        "size_mb": 24,
        "default": False,
        "description": "UCSC hg38 refGene gene annotation (GTF)",
    },
    # Cell-cycle genes of Tirosh et al. 2016 (Science 352:189), S phase (43) and G2/M (54), with the 2019 HGNC
    # symbols, as Seurat ships them (satijalab/seurat, data/cc.genes.updated.2019.rda, at a fixed commit; an R
    # list of two character vectors): benchmarks/spatial_variable (stage cellcycle)
    "seurat_cc_genes_2019": {
        "files": [("reference/seurat/cc.genes.updated.2019.rda",
                   "https://raw.githubusercontent.com/satijalab/seurat/d28233a843ede385acdee1cae7e9fb9d70e76078/"
                   "data/cc.genes.updated.2019.rda")],
        "md5": {"reference/seurat/cc.genes.updated.2019.rda": "55d7e35793436d5e91646d774d9f86c4"},
        "size_mb": 0.001,
        "default": False,
        "description": "Tirosh et al. 2016 cell-cycle genes (S, G2/M), 2019 symbols, from Seurat (.rda)",
    },
})

# ---- built from their sources (hicstraw over HTTP; see _builders.slice_hic) ----
DATASETS.update({
    # Takei et al. 2025 (Nature) cerebellum rep 1, field of view 0: the first 400,000 rows (47 whole cells)
    # streamed out of the Zenodo tarball, + the locus map and the cell clustering (import tutorial)
    "takei2025_fov0": {
        "build": ("seqfish_fov_head", {
            "tarball": "https://zenodo.org/records/7693825/files/cerebellum_rep1.tar.gz",
            "member": "cerebellum_rep1/cerebellum_rep1_pos0.csv", "rows": 400_000,
            "sidecars": [
                ("LC1-100k-09022022-mm10-25kb-meta.csv",
                 "https://media.githubusercontent.com/media/CaiGroup/dna-seqfish-plus-multi-omics/main/"
                 "data/annotation/LC1-100k-09022022-mm10-25kb-meta.csv"),
                ("cerebellum_mRNA_cluster_nuc_vol_filtered.csv",
                 "https://media.githubusercontent.com/media/CaiGroup/dna-seqfish-plus-multi-omics/main/"
                 "data/cerebellum/clustering/100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv")]}),
        "files": [("takei2025_fov0/cerebellum_rep1_pos0_cells.csv",
                   "https://zenodo.org/records/7693825/files/cerebellum_rep1.tar.gz"),
                  ("takei2025_fov0/LC1-100k-09022022-mm10-25kb-meta.csv",
                   "https://media.githubusercontent.com/media/CaiGroup/dna-seqfish-plus-multi-omics/main/"
                   "data/annotation/LC1-100k-09022022-mm10-25kb-meta.csv"),
                  ("takei2025_fov0/cerebellum_mRNA_cluster_nuc_vol_filtered.csv",
                   "https://media.githubusercontent.com/media/CaiGroup/dna-seqfish-plus-multi-omics/main/"
                   "data/cerebellum/clustering/100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv")],
        "md5": {"takei2025_fov0/cerebellum_rep1_pos0_cells.csv": "def6f22123b6fa7461320f819765770b"},
        "size_mb": 280,
        "default": True,
        "description": "Takei 2025 cerebellum rep 1, FOV 0: first 47 cells streamed from Zenodo 7693825 (built)",
    },
    # Rao et al. 2014 (Cell 159:1665) IMR90 in situ Hi-C, chr21 at 5 kb, hg19 (GEO GSE63525, combined map):
    # GEM-FISH and bulk reconstruction tutorials, Fig. 3
    "rao2014_imr90_chr21": {
        "build": ("slice_hic", {"cell": "IMR90", "chroms": ["21"], "res": 5000}),
        "files": [("rao2014_imr90/IMR90_chr21_5kb_hg19.cool", "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl/GSE63525_IMR90_combined.hic")],
        "size_mb": 4,
        "default": True,
        "fig3": True,
        "description": "Rao 2014 IMR90 Hi-C chr21 at 5 kb, sliced over HTTP from the GEO .hic (built)",
    },
    "rao2014_imr90_chr1": {
        "build": ("slice_hic", {"cell": "IMR90", "chroms": ["1"], "res": 5000}),
        "files": [("rao2014_imr90/IMR90_chr1_5kb_hg19.cool", "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl/GSE63525_IMR90_combined.hic")],
        "size_mb": 40,
        "default": False,
        "description": "Rao 2014 IMR90 Hi-C chr1 at 5 kb (the largest chromosome: performance checks), sliced over HTTP (built)",
    },
    "rao2014_gm12878_chr21": {
        "build": ("slice_hic", {"cell": "GM12878", "chroms": ["21"], "res": 5000}),
        "files": [("rao2014_gm12878/GM12878_chr21_5kb_hg19.cool",
                   "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl/GSE63525_GM12878_insitu_primary+replicate_combined.hic")],
        "size_mb": 6,
        "default": False,
        "description": "Rao 2014 GM12878 Hi-C chr21 at 5 kb, sliced over HTTP from the GEO .hic (built)",
    },
    # the authors' loop (HiCCUPS) and domain (Arrowhead) calls of Rao et al. 2014, the reference the Hi-C
    # structure callers are validated against
    "rao2014_annotations": {
        "files": [(f"rao2014_annotations/{n}", f"https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl/{n}") for n in (
            "GSE63525_IMR90_HiCCUPS_looplist.txt.gz", "GSE63525_IMR90_Arrowhead_domainlist.txt.gz",
            "GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz",
            "GSE63525_GM12878_primary+replicate_Arrowhead_domainlist.txt.gz")],
        "md5": {"rao2014_annotations/GSE63525_IMR90_HiCCUPS_looplist.txt.gz": "326c6dbafcb860ad1e726c544f71a5a6",
                "rao2014_annotations/GSE63525_IMR90_Arrowhead_domainlist.txt.gz": "6129d35df3b6726ddab38056170e3482",
                "rao2014_annotations/GSE63525_GM12878_primary+replicate_HiCCUPS_looplist.txt.gz":
                    "2195f24061059dca3cb190b73af3bd6e",
                "rao2014_annotations/GSE63525_GM12878_primary+replicate_Arrowhead_domainlist.txt.gz":
                    "42a23da326be4379b042ae9658ed6a0b"},
        "size_mb": 2,
        "default": False,
        "description": "Rao 2014 HiCCUPS loop and Arrowhead domain lists, IMR90 and GM12878 (GEO GSE63525)",
    },
    "rao2014_k562_chr21": {
        "build": ("slice_hic", {"cell": "K562", "chroms": ["21"], "res": 5000}),
        "files": [("rao2014_k562/K562_chr21_5kb_hg19.cool", "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE63nnn/GSE63525/suppl/GSE63525_K562_combined.hic")],
        "size_mb": 4,
        "default": False,
        "fig3": True,
        "description": "Rao 2014 K562 Hi-C chr21 at 5 kb, sliced over HTTP from the GEO .hic (built)",
    },
})
