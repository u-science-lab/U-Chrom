"""I/O helpers with lazy optional-dependency imports."""

_EXPORTS = {
    "read_pairs": ("._io", "read_pairs"),
    "read_phased_pairs": (".phased", "read_phased_pairs"),
    "write_phased_pairs": (".phased", "write_phased_pairs"),
    "load_cool": ("._io", "load_cool"),
    "load_hic": ("._io", "load_hic"),
    "load_hic_inter": ("._io", "load_hic_inter"),
    "load_hic_genome": ("._io", "load_hic_genome"),
    "read_particles": ("._io", "read_particles"),
    "save_particles": ("._io", "save_particles"),
    "read_3dg": ("._io", "read_3dg"),
    "open_file": ("._io", "open_file"),
    "export_pdb_coords": ("._io", "export_pdb_coords"),
    "particles_to_pdb": ("._io", "particles_to_pdb"),
    "read_bintu_tracing": ("._io", "read_bintu_tracing"),
    "read_su2020_tracing": (".su2020", "read_su2020_tracing"),
    "read_su2020_hic": (".su2020", "read_su2020_hic"),
    "write_locus_cool": (".cool", "write_locus_cool"),
    "write_fofct": ("._io", "write_fofct"),
    "write_pyhim_trace": (".pyhim", "write_pyhim_trace"),
    "read_snapfish": (".snapfish", "read_snapfish"),
    "read_seqfish_detections": (".seqfish_detections", "read_seqfish_detections"),
    "read_seqfish_multiomics": (".seqfish_multiomics", "read_seqfish_multiomics"),
    "read_seqfish_transcriptome": (".seqfish_multiomics", "read_seqfish_transcriptome"),
    "load_seqfish_multiomics_linked": (".seqfish_multiomics", "load_seqfish_multiomics_linked"),
    "load_takei2025_cerebellum": (".seqfish_multiomics", "load_takei2025_cerebellum"),
    "count_contacts": (".particles", "count_contacts"),
    "GenomeRange": (".genome", "GenomeRange"),
    "sort_chroms": (".genome", "sort_chroms"),
    "chrom_sort_key": (".genome", "chrom_sort_key"),
    "pairs_df_to_higashi": (".contacts", "pairs_df_to_higashi"),
    "genome_bins": (".pairs_maps", "genome_bins"),
    "iter_pairs": (".pairs_maps", "iter_pairs"),
    "bin_pairs": (".pairs_maps", "bin_pairs"),
    "pairs_to_scool": (".pairs_maps", "pairs_to_scool"),
    "pairs_chromsizes": (".pairs_maps", "pairs_chromsizes"),
    "read_juicer_loops": (".juicer_lists", "read_juicer_loops"),
    "read_juicer_domains": (".juicer_lists", "read_juicer_domains"),
    "make_higashi_config": (".contacts", "make_higashi_config"),
    "write_label_info": (".contacts", "write_label_info"),
    "write_higashi_inputs": (".contacts", "write_higashi_inputs"),
    "upgrade_h5cd": (".upgrade", "upgrade_h5cd"),
    "file_format_version": (".upgrade", "file_format_version"),
    "convert_chromdata": (".upgrade", "convert"),
}

__all__ = sorted(_EXPORTS)


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value
