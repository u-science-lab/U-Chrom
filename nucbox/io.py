import io
import gzip
import pandas as pd
import fire
import h5py

from cooler import Cooler


def open_file(path, mode="r"):
    if path.endswith(".gz"):
        mode += "b"
        return io.TextIOWrapper(gzip.open(path, mode))
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
    df = pd.read_csv(path, index_col=0, sep=",")
    df['chrom'] = df['chrom'].astype(str)
    return df


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
        ter_format = '%-6.6s%5.1d      %s %s%4.1d%s                                                     %10d\n'
    else:
        pdb_format = '%-6.6s%5.1d %4.4s%s%3.3s %s%4.1d%s   %8.3f%8.3f%8.3f%6.2f%6.2f          %2.2s  \n'
        ter_format = '%-6.6s%5.1d      %s %s%4.1d%s                                                     \n'

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


if __name__ == "__main__":
    fire.Fire({
        "particles_to_pdb": particles_to_pdb
    })
