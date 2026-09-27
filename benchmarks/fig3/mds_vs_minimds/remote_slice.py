"""Read one chromosome at one resolution from a remote 4DN mcool via HTTP range
requests (fsspec + h5py), without downloading the full file.
usage: remote_slice.py URL RES CHROM OUT.cool"""
import sys, time, fsspec, h5py, cooler, numpy as np
url, res, chrom, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
t = time.time()
fs = fsspec.filesystem('http', block_size=4 * 2**20)
with fs.open(url, 'rb', cache_type='blockcache') as fh:
    with h5py.File(fh, 'r') as h:
        print('resolutions:', sorted(int(k) for k in h['resolutions'].keys()))
        c = cooler.Cooler(h[f'resolutions/{res}'])
        print(c.info.get('genome-assembly'), c.info.get('sum'), c.info.get('nnz'))
        bins = c.bins().fetch(chrom).reset_index(drop=True)
        pix = c.matrix(balance=False, as_pixels=True).fetch(chrom)
        off = c.offset(chrom)
        pix['bin1_id'] -= off; pix['bin2_id'] -= off
        print('chrom raw sum', pix['count'].sum(), 'n pixels', len(pix), 'weights finite', np.isfinite(bins['weight']).sum() if 'weight' in bins else None)
        cooler.create_cooler(out, bins[['chrom', 'start', 'end'] + (['weight'] if 'weight' in bins else [])],
                             pix[['bin1_id', 'bin2_id', 'count']], assembly=c.info.get('genome-assembly'))
print('done in', round(time.time() - t, 1), 's')
