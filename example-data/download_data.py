"""Pre-stage every large dataset used by the tutorials.

Idempotent: files already present are skipped.  Normally you don't need
to run this — each tutorial auto-downloads what it needs on first use.
It's convenient for offline / CI setups or when you want everything
ready before running nbconvert.

Usage::

    python example-data/download_data.py           # fetch all default datasets
    python example-data/download_data.py --takei   # just Takei 2021 FOF-CT
    python example-data/download_data.py --seqfish # just seqFISH+ zip
    python example-data/download_data.py --schicar_dna  # opt-in, ~1.5 GB pairs
    python example-data/download_data.py --schicar_atac # opt-in, ~1.4 GB ATAC + mm10 GTF
    python example-data/download_data.py --spatial_atac_hic  # opt-in, ~9.5 GB (GSE307620)
    python example-data/download_data.py --spatial_hicrna    # opt-in, ~2.3 GB processed (GSE311199)
    python example-data/download_data.py --takei2025_cerebellum  # opt-in, 2.8 GB tarball
    python example-data/download_data.py --liu2025_mop           # opt-in, 1.7 GB FOF-CT

Datasets marked ``"default": False`` are large and only fetched when
requested explicitly.  Multi-file datasets list ``files`` as
``(relative path, url)`` pairs.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent

_GSE305439 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE305nnn/GSE305439/suppl"
_GEO_SAMPLE = "https://ftp.ncbi.nlm.nih.gov/geo/samples"


def _gsm(name: str) -> str:
    """GEO per-sample supplementary URL of a file named 'GSM<id>_…'."""
    gsm = name.split("_", 1)[0]
    return f"{_GEO_SAMPLE}/{gsm[:-3]}nnn/{gsm}/suppl/{name}"


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

DATASETS = {
    "takei": {
        "filename": "4DNFIHF3JCBY.csv",
        "url": (
            "https://4dn-open-data-public.s3.amazonaws.com/"
            "fourfront-webprod/wfoutput/"
            "e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv"
        ),
        "size_mb": 22,
        "description": "Takei 2021 mESC FOF-CT chromatin tracing",
    },
    "seqfish": {
        "filename": "DNAseqFISH+.zip",
        "url": (
            "https://zenodo.org/records/3735329/files/"
            "DNAseqFISH%2B.zip?download=1"
        ),
        "size_mb": 144,
        "description": "Takei 2021 raw seqFISH+ spot detections",
    },
    "bintu_imr90": {
        "filename": "IMR90_chr21-18-20Mb.csv",
        "url": (
            "https://raw.githubusercontent.com/BogdanBintu/"
            "ChromatinImaging/master/Data/IMR90_chr21-18-20Mb.csv"
        ),
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
    "spatial_hicrna": {
        "files": [(f"spatial_hicrna/raw/GSE311199/{n}", _gsm(n)) for n in _SPATIAL_HICRNA],
        "size_mb": 2300,
        "default": False,
        "description": "Spatial Hi-C-RNA brain / embryo / melanoma: processed h5ad, RNA, images (GSE311199)",
    },
}


def _download(url: str, dest: Path, description: str, size_mb: int) -> None:
    if dest.exists():
        print(f"[skip] {dest.name} already present ({description})")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"[pull] {description} (~{size_mb} MB) → {dest}")
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        print(f"[fail] {dest.name}: {exc}", file=sys.stderr)
        raise


def _md5(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    for key, info in DATASETS.items():
        ap.add_argument(
            f"--{key}", action="store_true",
            help=f"fetch {info['description']} ({info['size_mb']} MB)",
        )
    args = ap.parse_args()
    selected = [k for k in DATASETS if getattr(args, k)]
    if not selected:
        selected = [k for k, info in DATASETS.items() if info.get("default", True)]

    for key in selected:
        info = DATASETS[key]
        files = info.get("files") or [(info["filename"], info["url"])]
        for rel, url in files:
            _download(url, HERE / rel, info["description"], info["size_mb"])
            want = info.get("md5", {}).get(rel)
            if want and _md5(HERE / rel) != want:
                raise SystemExit(f"[fail] md5 mismatch for {rel} (expected {want})")

    print(f"\nAll requested datasets staged under: {HERE}")


if __name__ == "__main__":
    main()
