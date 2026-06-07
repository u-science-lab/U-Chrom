"""I/O helpers with lazy optional-dependency imports."""

_EXPORTS = {
    "read_pairs": ("._io", "read_pairs"),
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
    "read_seqfish_multiomics": (".seqfish_multiomics", "read_seqfish_multiomics"),
    "read_seqfish_transcriptome": (".seqfish_multiomics", "read_seqfish_transcriptome"),
    "load_seqfish_multiomics_linked": (".seqfish_multiomics", "load_seqfish_multiomics_linked"),
    "load_takei2025_cerebellum": (".seqfish_multiomics", "load_takei2025_cerebellum"),
    "create_particles_from_pairs": (".particles", "create_particles_from_pairs"),
    "create_contacts_from_pairs": (".particles", "create_contacts_from_pairs"),
    "create_particles_from_cool": (".particles", "create_particles_from_cool"),
    "create_contacts_from_cool": (".particles", "create_contacts_from_cool"),
    "count_contacts": (".particles", "count_contacts"),
    "filter_contacts": (".particles", "filter_contacts"),
    "remove_violated_contacts": (".particles", "remove_violated_contacts"),
    "filter_outliers": (".particles", "filter_outliers"),
    "random_pos": (".particles", "random_pos"),
    "GenomeRange": (".genome", "GenomeRange"),
    "pairs_df_to_higashi": (".contacts", "pairs_df_to_higashi"),
    "make_higashi_config": (".contacts", "make_higashi_config"),
    "write_label_info": (".contacts", "write_label_info"),
    "write_higashi_inputs": (".contacts", "write_higashi_inputs"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value
