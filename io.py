import pandas as pd
import fire


def read_particles(path):
    df = pd.read_csv(path, index_col=0, sep=",")
    return df


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
    write(line_format % 'REMARK 210 Chain letter is different every chromosome, where Chr1=a, Chr2=b etc.')
    
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
            x, y, z = chrom_df[['x', 'y', 'z']].iloc[i] #XYZ coordinates
             
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


def particles_to_pdb(path_particles, path_pdb):
    df = read_particles(path_particles)
    export_pdb_coords(path_pdb, df)


if __name__ == "__main__":
    fire.Fire()