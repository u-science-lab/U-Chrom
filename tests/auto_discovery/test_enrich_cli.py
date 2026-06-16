import numpy as np
import pandas as pd


def test_enrich_cli_adds_reusable_feature_layers(tmp_path):
    from uchrom import ChromData
    from uchrom.auto_discovery.__main__ import main

    cdata = ChromData(
        np.zeros((4, 3), dtype=float),
        pd.DataFrame({
            "chrom": ["chr1", "chr1", "chr1", "chr1"],
            "start": [0, 4, 8, 12],
            "end": [4, 8, 12, 16],
            "trace_id": ["t1", "t1", "t1", "t1"],
        }),
        tracks=pd.DataFrame({"signal": [0.0, 10.0, 11.0, 0.0]}),
        results={
            "tads": pd.DataFrame({
                "chrom": ["chr1"],
                "start": [0],
                "end": [16],
            }),
        },
        uns={"genome_assembly": "toy"},
    )
    input_path = tmp_path / "input.h5cd"
    output_path = tmp_path / "enriched.h5cd"
    fasta = tmp_path / "toy.fa"
    fasta.write_text(">chr1\nACGTGGGGCCCCAAAA\n")
    gtf = tmp_path / "genes.gtf"
    gtf.write_text(
        'chr1\ttest\tgene\t5\t12\t.\t+\t.\tgene_id "g1"; gene_name "Gene1";\n'
    )
    cdata.write(input_path)

    rc = main([
        "enrich",
        str(input_path),
        str(output_path),
        "--fasta",
        str(fasta),
        "--gtf",
        str(gtf),
        "--peak-track",
        "signal",
        "--peak-threshold",
        "9",
        "--project-existing-structure",
        "--store-schema",
    ])

    assert rc == 0
    out = ChromData.read(output_path)
    assert "seq.gc_fraction" in out.tracks
    assert "gtf.gene_body_overlap_fraction" in out.tracks
    assert "strc.distance_to_tad_boundary" in out.tracks
    assert "peak.signal_overlap" in out.tracks
    assert "peaks:signal" in out.results
    schema = out.discovery_schema
    assert schema["modalities"]["sequence_features"]["present"]
    assert schema["modalities"]["genome_annotations"]["present"]
    assert schema["modalities"]["structure_annotations"]["present"]
    assert schema["modalities"]["peak_features"]["present"]
