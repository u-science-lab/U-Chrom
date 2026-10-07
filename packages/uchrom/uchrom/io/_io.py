import gzip
import pandas as pd
import h5py

from cooler import Cooler


def open_file(path, mode="r"):
    if path.endswith(".gz"):
        return gzip.open(path, mode + "t")
    return open(path, mode)


def read_pairs(path):
    assert path.endswith(".pairs") or path.endswith(".pairs.gz")
    with open_file(path) as f:
        df = pd.read_csv(f, sep="\t", header=None, comment="#")
    columns = ["read", "chr1", "pos1", "chr2", "pos2", "strand1", "strand2"]
    df = df.iloc[:, :len(columns)]
    df.columns = columns
    df['chr1'] = df['chr1'].astype(str)
    df['chr2'] = df['chr2'].astype(str)
    return df


def read_particles(path):
    """Read reconstruction output. Auto-detects format by extension.

    - ``.chromdata.zarr`` / ``.cdz`` → ChromData, returned as a flat
      DataFrame in the row order it was saved in (a ``.h5cd`` raises: convert
      it with ``python -m uchrom.io.upgrade``)
    - ``.csv`` or other   → CSV
    """
    from chromdata.zarrcd import container_kind

    kind = container_kind(path)
    if kind is not None:
        from chromdata import ChromData
        cd = ChromData.read(path, original_order=True)
        df = cd.to_dataframe()
        df['chrom'] = df['chrom'].astype(str)
        return df
    df = pd.read_csv(path, index_col=0, sep=",")
    df['chrom'] = df['chrom'].astype(str)
    return df


def save_particles(df, path, cell_id=None):
    """Save reconstruction output as a ChromData file or a CSV.

    Format inferred from file extension:

    - ``.csv``                        → CSV via ``df.to_csv``
    - ``.chromdata.zarr`` / ``.cdz``  → ChromData store (other suffixes raise)

    ``cell_id`` is only propagated into the ChromData branch (CSV has no
    dedicated cell column); it is passed through to
    :meth:`ChromData.from_dataframe`.
    """
    path_str = str(path)
    if path_str.endswith(".csv"):
        df.to_csv(path)
        return
    from chromdata import ChromData
    cd = ChromData.from_dataframe(df, cell_id=cell_id)
    cd.write(path)


def read_3dg(path):
    df = pd.read_csv(path, sep="\t", comment="#", header=None)
    df.columns = ["chrom", "start", "x", 'y', 'z']
    return df


def load_cool(path, pos='mid'):
    """Load pixels from cooler."""
    c = Cooler(path)
    with h5py.File(c.store) as f:
        c_root = f[c.uri.split("::")[1]] if "::" in c.uri else f
        c_bins = c_root['bins']
        bin_df = pd.DataFrame({
            'chrom': c.chromsizes.index[c_bins['chrom'][:]],
            'start': c_bins['start'][:],
            'end': c_bins['end'][:],
        })
        c_pixels = c_root['pixels']
        bin1 = bin_df.loc[c_pixels['bin1_id'][:]].reset_index(drop=True)
        bin2 = bin_df.loc[c_pixels['bin2_id'][:]].reset_index(drop=True)
        pixel_df = pd.DataFrame({
            'chr1': bin1.chrom,
            'start1': bin1.start,
            'end1': bin1.end,
            'chr2': bin2.chrom,
            'start2': bin2.start,
            'end2': bin2.end,
            'count': c_pixels['count'][:],
        })
        if pos == 'mid':
            pixel_df['pos1'] = (pixel_df['start1'] + pixel_df['end1']) / 2
            pixel_df['pos2'] = (pixel_df['start2'] + pixel_df['end2']) / 2
    return pixel_df


def load_hic(path, resolution, chrom=None, norm='KR'):
    """Load contact matrix from .hic file using hicstraw."""
    try:
        import hicstraw
    except ImportError:
        raise ImportError(
            "hicstraw is required to read .hic files. "
            "Install it with: pip install hic-straw"
        )

    hic = hicstraw.HiCFile(path)
    chromosomes = hic.getChromosomes()
    # build chrom name -> length lookup (skip 'All')
    chrom_info = {c.name: c.length for c in chromosomes if c.name != 'All'}

    if chrom is not None:
        # strip 'chr' prefix if needed to match hic file convention
        chrom_key = chrom
        if chrom_key not in chrom_info:
            chrom_key = chrom.replace('chr', '')
        if chrom_key not in chrom_info:
            raise ValueError(
                f"Chromosome {chrom} not found. "
                f"Available: {list(chrom_info.keys())}"
            )

        import numpy as np

        chrom_len = chrom_info[chrom_key]
        n_bins = (chrom_len + resolution - 1) // resolution

        # use getRecords API (strawAsMatrix segfaults on large chromosomes)
        mzd = hic.getMatrixZoomData(
            chrom_key, chrom_key, 'observed', norm, 'BP', resolution
        )
        records = mzd.getRecords(0, chrom_len, 0, chrom_len)

        matrix = np.zeros((n_bins, n_bins))
        for rec in records:
            i = rec.binX // resolution
            j = rec.binY // resolution
            if i < n_bins and j < n_bins:
                val = rec.counts
                if np.isfinite(val):
                    matrix[i, j] = val
                    matrix[j, i] = val

        # build bins dataframe
        starts = [i * resolution for i in range(n_bins)]
        ends = [min((i + 1) * resolution, chrom_len) for i in range(n_bins)]
        bins_df = pd.DataFrame({
            'chrom': chrom,
            'start': starts,
            'end': ends,
            'idx': range(n_bins),
        })

        return bins_df, matrix
    else:
        raise ValueError("Whole-genome mode not yet supported for .hic files. "
                         "Please specify --chrom.")


def load_hic_inter(path, resolution, chrom1, chrom2, norm='KR'):
    """Load inter-chromosomal contact matrix from .hic file."""
    try:
        import hicstraw
    except ImportError:
        raise ImportError(
            "hicstraw is required to read .hic files. "
            "Install it with: pip install hic-straw"
        )
    import numpy as np

    hic = hicstraw.HiCFile(path)
    chromosomes = hic.getChromosomes()
    chrom_info = {c.name: c.length for c in chromosomes if c.name != 'All'}

    # resolve chrom names
    def resolve(name):
        if name in chrom_info:
            return name
        alt = name.replace('chr', '')
        if alt in chrom_info:
            return alt
        raise ValueError(f"Chromosome {name} not found. Available: {list(chrom_info.keys())}")

    key1, key2 = resolve(chrom1), resolve(chrom2)
    len1, len2 = chrom_info[key1], chrom_info[key2]
    n1 = (len1 + resolution - 1) // resolution
    n2 = (len2 + resolution - 1) // resolution

    mzd = hic.getMatrixZoomData(key1, key2, 'observed', norm, 'BP', resolution)
    records = mzd.getRecords(0, len1, 0, len2)

    matrix = np.zeros((n1, n2))
    for rec in records:
        i = rec.binX // resolution
        j = rec.binY // resolution
        if i < n1 and j < n2:
            val = rec.counts
            if np.isfinite(val):
                matrix[i, j] = val

    return matrix


def load_hic_genome(path, resolution, chroms=None, norm='KR'):
    """Load whole-genome contact matrix (intra + inter) from .hic or .mcool.

    Returns:
        bins_df: DataFrame with chrom, start, end, idx for all bins
        matrix: N x N whole-genome contact matrix
        offsets: dict mapping chrom name -> start index in the matrix
        chrom_sizes: dict mapping chrom name -> number of bins
    """

    if path.endswith(('.mcool', '.cool')):
        return _load_genome_mcool(path, resolution, chroms)
    elif path.endswith('.hic'):
        return _load_genome_hic(path, resolution, chroms, norm)
    else:
        raise ValueError(f"Unsupported format: {path}. Use .hic, .mcool, or .cool")


def _load_genome_mcool(path, resolution, chroms=None):
    """Load whole-genome contact matrix from .mcool/.cool file."""
    import numpy as np
    from cooler import Cooler

    if '::' in path:
        clr = Cooler(path)
    else:
        clr = Cooler(f"{path}::resolutions/{resolution}")

    if chroms is None:
        skip = {'chrY', 'Y', 'chrMT', 'MT', 'chrM', 'M'}
        chroms = [c for c in clr.chromnames if c not in skip]

    # compute offsets and bins
    offsets = {}
    all_bins = []
    total = 0
    chrom_sizes = {}
    for c in chroms:
        chrom_bins = clr.bins().fetch(c)
        n_bins = len(chrom_bins)
        offsets[c] = total
        chrom_sizes[c] = n_bins
        for i in range(n_bins):
            all_bins.append({
                'chrom': c,
                'start': int(chrom_bins['start'].iloc[i]),
                'end': int(chrom_bins['end'].iloc[i]),
                'idx': total + i,
            })
        total += n_bins

    bins_df = pd.DataFrame(all_bins)
    matrix = np.zeros((total, total))

    # fill matrix block by block
    for i, c1 in enumerate(chroms):
        o1 = offsets[c1]
        n1 = chrom_sizes[c1]

        # intra-chromosomal
        intra = clr.matrix(balance=True).fetch(c1)
        intra = np.nan_to_num(intra, nan=0.0)
        matrix[o1:o1+n1, o1:o1+n1] = intra

        # inter-chromosomal
        for j in range(i + 1, len(chroms)):
            c2 = chroms[j]
            o2 = offsets[c2]
            n2 = chrom_sizes[c2]
            try:
                inter = clr.matrix(balance=True).fetch(c1, c2)
                inter = np.nan_to_num(inter, nan=0.0)
                matrix[o1:o1+n1, o2:o2+n2] = inter
                matrix[o2:o2+n2, o1:o1+n1] = inter.T
            except Exception:
                pass

    return bins_df, matrix, offsets, chrom_sizes


def _load_genome_hic(path, resolution, chroms=None, norm='KR'):
    """Load whole-genome contact matrix from .hic file."""
    try:
        import hicstraw
    except ImportError:
        raise ImportError("hicstraw is required. Install with: pip install hic-straw")
    import numpy as np

    hic = hicstraw.HiCFile(path)
    chrom_info_raw = {c.name: c.length for c in hic.getChromosomes()
                      if c.name != 'All'}

    if chroms is None:
        skip = {'Y', 'MT', 'M'}
        chroms = [c for c in chrom_info_raw if c not in skip
                  and c.replace('chr', '') not in skip]
        chroms = sorted(chroms, key=lambda x: (
            0 if x.replace('chr', '').isdigit() else 1,
            int(x.replace('chr', '')) if x.replace('chr', '').isdigit() else ord(x.replace('chr', ''))
        ))

    # compute offsets and bins
    offsets = {}
    all_bins = []
    total = 0
    chrom_sizes = {}
    for c in chroms:
        key = c if c in chrom_info_raw else c.replace('chr', '')
        clen = chrom_info_raw[key]
        n_bins = (clen + resolution - 1) // resolution
        offsets[c] = total
        chrom_sizes[c] = n_bins
        display_name = c if c.startswith('chr') else f'chr{c}'
        for i in range(n_bins):
            all_bins.append({
                'chrom': display_name,
                'start': i * resolution,
                'end': min((i + 1) * resolution, clen),
                'idx': total + i,
            })
        total += n_bins

    bins_df = pd.DataFrame(all_bins)
    matrix = np.zeros((total, total))

    # resolve chrom keys
    chrom_keys = {}
    for c in chroms:
        chrom_keys[c] = c if c in chrom_info_raw else c.replace('chr', '')

    # fill matrix (reuse single HiCFile object)
    for i, c1 in enumerate(chroms):
        key1 = chrom_keys[c1]
        n1 = chrom_sizes[c1]
        o1 = offsets[c1]
        len1 = chrom_info_raw[key1]

        # intra-chromosomal (diagonal block)
        mzd = hic.getMatrixZoomData(key1, key1, 'observed', norm, 'BP', resolution)
        records = mzd.getRecords(0, len1, 0, len1)
        for rec in records:
            ri = rec.binX // resolution
            rj = rec.binY // resolution
            if ri < n1 and rj < n1:
                val = rec.counts
                if np.isfinite(val):
                    matrix[o1+ri, o1+rj] = val
                    matrix[o1+rj, o1+ri] = val

        # inter-chromosomal (off-diagonal blocks)
        for j in range(i + 1, len(chroms)):
            c2 = chroms[j]
            key2 = chrom_keys[c2]
            n2 = chrom_sizes[c2]
            o2 = offsets[c2]
            len2 = chrom_info_raw[key2]
            try:
                mzd = hic.getMatrixZoomData(
                    key1, key2, 'observed', norm, 'BP', resolution)
                records = mzd.getRecords(0, len1, 0, len2)
                for rec in records:
                    ri = rec.binX // resolution
                    rj = rec.binY // resolution
                    if ri < n1 and rj < n2:
                        val = rec.counts
                        if np.isfinite(val):
                            matrix[o1+ri, o2+rj] = val
                            matrix[o2+rj, o1+ri] = val
            except Exception:
                pass  # some pairs may not have data

    return bins_df, matrix, offsets, chrom_sizes


def export_pdb_coords(file_path, particles, scale=1.0, extended=True):
    """
    Write chromosome particle coordinates as a PDB format file
    """

    alc = ' '
    ins = ' '
    prefix = 'HETATM'
    line_format = '%-80.80s\n'
    
    if extended:
        pdb_format = '%-6.6s%5.1d %4.4s%s%3.3s %s%4.1d%s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2.2s  %10d\n'
    else:
        pdb_format = '%-6.6s%5.1d %4.4s%s%3.3s %s%4.1d%s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2.2s  \n'

    file_obj = open(file_path, 'w')
    write = file_obj.write
    
    chromosomes = list(particles['chrom'].unique())
    
    sort_chromos = []
    for chromo in chromosomes:
        if chromo[:3].lower() == 'chr':
            key = chromo[3:]
        else:
            key = chromo
        
        if key.isdigit():
            key = '%03d' % int(key)
        
        sort_chromos.append((key, chromo))
    
    sort_chromos.sort()
    sort_chromos = [x[1] for x in sort_chromos]

    particle_size = particles.iloc[0]['end'] - particles.iloc[0]['start']
    
    title = 'Genome structure export'
    
    write(line_format % 'TITLE         %s' % title)
    write(line_format % 'REMARK 210') 
    write(line_format % 'REMARK 210 Atom type C is used for all particles')
    write(line_format % 'REMARK 210 Atom number increases every %s bases' % particle_size)
    write(line_format % 'REMARK 210 Residue code indicates chromosome')
    write(line_format % 'REMARK 210 Residue number represents which sequence Mb the atom is in')
    
    if extended:
        file_obj.write(line_format % 'REMARK 210 Extended PDB format with particle seq. pos. in last column')
    
    file_obj.write(line_format % 'REMARK 210')
    
    pos_chromo = {}

    m = 0
    line = 'MODEL     %4d' % (m+1)
    write(line_format    % line)
    
    c = 0
    j = 1
    seqPrev = None
    
    for k, chromo in enumerate(sort_chromos):
        chain_code = chr(ord('A')+k)                        
        
        tlc = chromo
        if tlc.lower().startswith("chr"):
            tlc = tlc[3:]
        while len(tlc) < 2:
            tlc = '_' + tlc
        
        if len(tlc) == 2:
            tlc = 'C' + tlc
        
        if len(tlc) > 3:
            tlc = tlc[:3]
        
        chrom_df = particles[particles['chrom'] == chromo]
        
        if chrom_df.shape[0] == 0:
            continue
        
        pos = chrom_df['start']
        
        for i, seqPos in enumerate(list(pos.values)):
            c += 1
 
            seqMb = int(seqPos//1e6) + 1
            
            if seqMb == seqPrev:
                j += 1
            else:
                j = 1
            
            el = 'C'
            a = 'C%d' % j
                
            aName = '%-3s' % a
            x, y, z = chrom_df[['x', 'y', 'z']].iloc[i]  #XYZ coordinates
            if scale != 1.0:
                x, y, z = [v*scale for v in [x, y, z]]
             
            seqPrev = seqMb
            pos_chromo[c] = chromo
            
            if extended:
                line = pdb_format % (prefix,c,aName,alc,tlc,chain_code,seqMb,ins,x,y,z,0.0,0.0,el,seqPos)
            else:
                line = pdb_format % (prefix,c,aName,alc,tlc,chain_code,seqMb,ins,x,y,z,0.0,0.0,el)
                
            write(line)
 
    write(line_format % 'ENDMDL')
 
    for i in range(c - 1):
        if pos_chromo[i+1] == pos_chromo[i+2]:
            line = 'CONECT%5.1d%5.1d' % (i+1, i+2)
            write(line_format    % line)
 
    write(line_format % 'END')
    file_obj.close()


def read_bintu_tracing(
    path,
    chrom: str,
    start_bp: int,
    resolution_bp: int = 30_000,
    skip_header_line: bool = True,
    cell_id_per_trace: bool = True,
    genome_assembly: str = "hg38",
):
    """Read a Bintu 2018-style chromatin-tracing CSV into a ChromData.

    Bintu et al. 2018 (*Science* 362, eaau1783) distribute their FISH
    imaging as simple CSVs with columns
    ``Chromosome index, Segment index, Z, X, Y`` (coordinates in nm).
    Each ``Chromosome index`` is one imaged chromatin fiber in one cell
    (they do not distinguish multiple alleles per cell), and segments
    are numbered 1..N along the genomic region.

    Parameters
    ----------
    path : str
        Path to the CSV (e.g. ``IMR90_chr21-18-20Mb.csv``).
    chrom : str
        Chromosome name for the output (e.g. ``'chr21'``).
    start_bp : int
        Genomic start of segment 1 (from the dataset's README — for
        ``IMR90_chr21-18-20Mb`` this is ``18_627_714`` in hg38).
    resolution_bp : int
        Genomic size of each segment (30 kb in Bintu 2018).
    skip_header_line : bool
        If True, skip the first descriptive line before the CSV header.
    cell_id_per_trace : bool
        If True, assign each trace to its own ``cell_id`` (one trace
        per cell — matches how Bintu 2018 published the data).
    genome_assembly : str
        The assembly of ``start_bp`` (recorded in ``uns``); e.g. ``"hg19"``
        with ``start_bp=20_000_032`` for the same IMR90 region.

    Returns
    -------
    ChromData
    """
    import pandas as pd
    import numpy as np
    from chromdata import ChromData

    raw = pd.read_csv(path, skiprows=1 if skip_header_line else 0)
    raw = raw.dropna(subset=['X', 'Y', 'Z'])
    raw = raw.rename(columns={
        'Chromosome index': 'trace_id',
        'Segment index': 'segment',
        'X': 'x', 'Y': 'y', 'Z': 'z',
    })
    raw['trace_id'] = raw['trace_id'].astype(int)
    raw['segment'] = raw['segment'].astype(int)
    raw['chrom'] = chrom
    raw['start'] = (raw['segment'] - 1) * resolution_bp + start_bp
    raw['end'] = raw['start'] + resolution_bp
    if cell_id_per_trace:
        raw['cell_id'] = raw['trace_id'].astype(str)

    coords = raw[['x', 'y', 'z']].to_numpy(dtype=np.float64)
    spots_cols = ['chrom', 'start', 'end', 'trace_id']
    if 'cell_id' in raw.columns:
        spots_cols.append('cell_id')
    spots = raw[spots_cols].reset_index(drop=True)
    return ChromData(
        coords=coords, spots=spots,
        uns={'xyz_unit': 'nm', 'genome_assembly': genome_assembly,
             'source': 'Bintu 2018 (Science 362, eaau1783)'},
    )


def particles_to_pdb(path_particles, path_pdb, split_by_chrom=False):
    df = read_particles(path_particles)
    if not split_by_chrom:
        export_pdb_coords(path_pdb, df)
    else:
        from os.path import splitext
        chroms = list(df['chrom'].unique())
        prefix, suffix = splitext(path_pdb)
        for chr in chroms:
            path = f"{prefix}.{chr}{suffix}"
            sdf = df[df['chrom'] == chr]
            export_pdb_coords(path, sdf)


def write_fofct(cd, path, *, cell_table=None, rna_table=None, **kwargs):
    """Write a ChromData as a 4DN FOF-CT core table (+ optional cell and
    RNA-spot tables) — :meth:`ChromData.to_fofct` as a function, the
    counterpart of :meth:`ChromData.from_fofct`."""
    return cd.to_fofct(path, cell_table=cell_table, rna_table=rna_table, **kwargs)
