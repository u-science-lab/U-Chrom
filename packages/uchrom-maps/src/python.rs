//! Python bindings (`uchrom_maps._kernels`).

use crate::gauss::Arith;
use crate::{gauss, hiccups, mustache, pairwise, rwr, with_threads};
use numpy::ndarray::Array2;
use numpy::{IntoPyArray, PyArray2, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

fn slice<'a, T: numpy::Element>(a: &'a PyReadonlyArray1<'_, T>, name: &str) -> PyResult<&'a [T]> {
    a.as_slice().map_err(|_| PyValueError::new_err(format!("{name}: a contiguous 1-D array is needed")))
}

/// HiCCUPS scoring of one chromosome (`uchrom.strc.loop.hiccups._score_chrom`).
///
/// Returns a dict: ``hist`` (list of four int64 arrays, λ-chunk x count; donut, vertical, horizontal,
/// lowleft), ``i``, ``j``, ``count`` (int64) and ``lam`` (list of four float64 arrays) of the candidates,
/// ``n_tested``.
#[pyfunction]
#[pyo3(signature = (n, bi, bj, count, weight, expected, p, w, max_diag, tile_rows, edges, cmin, n_threads=0))]
#[allow(clippy::too_many_arguments)]
fn hiccups_score<'py>(
    py: Python<'py>,
    n: usize,
    bi: PyReadonlyArray1<'py, i64>,
    bj: PyReadonlyArray1<'py, i64>,
    count: PyReadonlyArray1<'py, f64>,
    weight: PyReadonlyArray1<'py, f64>,
    expected: PyReadonlyArray1<'py, f64>,
    p: usize,
    w: usize,
    max_diag: usize,
    tile_rows: usize,
    edges: PyReadonlyArray1<'py, f64>,
    cmin: PyReadonlyArray1<'py, i64>,
    n_threads: usize,
) -> PyResult<Bound<'py, PyDict>> {
    let inp = hiccups::Input {
        n,
        bi: slice(&bi, "bi")?,
        bj: slice(&bj, "bj")?,
        count: slice(&count, "count")?,
        weight: slice(&weight, "weight")?,
        expected: slice(&expected, "expected")?,
        p,
        w,
        max_diag,
        tile_rows,
        edges: slice(&edges, "edges")?,
        cmin: slice(&cmin, "cmin")?,
    };
    let res = py
        .detach(|| with_threads(n_threads, || hiccups::score_chrom(&inp)))
        .map_err(PyValueError::new_err)?
        .map_err(PyValueError::new_err)?;
    let d = PyDict::new(py);
    let hiccups::Output { hist, hist_shape, i, j, cnt, lam, n_tested } = res;
    let hl = PyList::empty(py);
    for (h, shape) in hist.into_iter().zip(hist_shape) {
        let a = Array2::from_shape_vec(shape, h).map_err(|e| PyValueError::new_err(e.to_string()))?;
        hl.append(a.into_pyarray(py))?;
    }
    d.set_item("hist", hl)?;
    d.set_item("i", i.into_pyarray(py))?;
    d.set_item("j", j.into_pyarray(py))?;
    d.set_item("count", cnt.into_pyarray(py))?;
    let ll = PyList::empty(py);
    for l in lam {
        ll.append(l.into_pyarray(py))?;
    }
    d.set_item("lam", ll)?;
    d.set_item("n_tested", n_tested)?;
    Ok(d)
}

/// The Mustache scale-space scan of one chromosome (`uchrom.strc.loop.mustache._scan`).
///
/// ``weights``: per octave a list of the ``scales + 2`` correlation weights scipy uses
/// (``_gaussian_kernel1d(sigma, 0, radius)[::-1]``); ``fma``, ``block``, ``min_terms``: scipy's
/// accumulation scheme (``uchrom_maps.scipy_arithmetic()``).  Returns ``(best, layer, st_sum, st_cnt,
/// st_min)``.
#[pyfunction]
#[pyo3(signature = (x, y, z, ex, ey, n, max_diag, min_diag, fill, weights, halo, tile, fma, block=0, min_terms=0, n_threads=0))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn mustache_scan<'py>(
    py: Python<'py>,
    x: PyReadonlyArray1<'py, i64>,
    y: PyReadonlyArray1<'py, i64>,
    z: PyReadonlyArray1<'py, f64>,
    ex: PyReadonlyArray1<'py, i64>,
    ey: PyReadonlyArray1<'py, i64>,
    n: usize,
    max_diag: usize,
    min_diag: i64,
    fill: f64,
    weights: Vec<Vec<Vec<f64>>>,
    halo: usize,
    tile: usize,
    fma: bool,
    block: usize,
    min_terms: usize,
    n_threads: usize,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let inp = mustache::Input {
        x: slice(&x, "x")?,
        y: slice(&y, "y")?,
        z: slice(&z, "z")?,
        ex: slice(&ex, "ex")?,
        ey: slice(&ey, "ey")?,
        n,
        max_diag,
        min_diag,
        fill,
        weights: &weights,
        halo,
        tile,
        arith: Arith { fma, block, min_terms },
    };
    let res = py
        .detach(|| with_threads(n_threads, || mustache::scan(&inp)))
        .map_err(PyValueError::new_err)?
        .map_err(PyValueError::new_err)?;
    Ok((
        res.best.into_pyarray(py).into_any(),
        res.layer.into_pyarray(py).into_any(),
        res.st_sum.into_pyarray(py).into_any(),
        res.st_cnt.into_pyarray(py).into_any(),
        res.st_min.into_pyarray(py).into_any(),
    ))
}

/// ``scipy.ndimage.gaussian_filter(img, sigma, mode="reflect", truncate=...)`` given scipy's correlation
/// weights; ``fma``, ``block``, ``min_terms``: the accumulation scheme of the scipy build (fused
/// multiply-adds, except the first ``block * floor(s / block)`` of ``s >= min_terms`` terms).
#[pyfunction]
#[pyo3(signature = (img, weights, fma, block=0, min_terms=0))]
fn gaussian_filter<'py>(
    py: Python<'py>,
    img: PyReadonlyArray2<'py, f64>,
    weights: Vec<f64>,
    fma: bool,
    block: usize,
    min_terms: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    if weights.len() % 2 == 0 {
        return Err(PyValueError::new_err("weights: an odd number of values"));
    }
    let a = img.as_array();
    let (h, w) = (a.shape()[0], a.shape()[1]);
    let data: Vec<f64> = a.iter().cloned().collect();
    let out = py.detach(|| gauss::gaussian_filter(&data, h, w, &weights, Arith { fma, block, min_terms }));
    let arr = Array2::from_shape_vec((h, w), out).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(arr.into_pyarray(py))
}

/// ``np.sum`` of a float64 array (numpy's pairwise summation), bit for bit.
#[pyfunction]
fn pairwise_sum(a: PyReadonlyArray1<'_, f64>) -> PyResult<f64> {
    Ok(pairwise::np_sum(slice(&a, "a")?))
}

/// The RWR band of one cell's chromosome (``uchrom.fea.impute_rwr.rwr_band``): ``(n, max_diag + 1)``
/// float64, ``out[i, d] = R(i, i + d)`` (NaN beyond the chromosome).  ``window = 0``: the whole chromosome.
/// ``holes``: leave at 0 the pixels SnapHiC v0.2's sliding windows never set (comparisons with its code).
#[pyfunction]
#[pyo3(signature = (n, i, j, rp, window, step, max_diag, min_sep=2, chain=true, n_threads=0, holes=false))]
#[allow(clippy::too_many_arguments)]
fn rwr_band<'py>(
    py: Python<'py>,
    n: usize,
    i: PyReadonlyArray1<'py, i64>,
    j: PyReadonlyArray1<'py, i64>,
    rp: f64,
    window: usize,
    step: usize,
    max_diag: usize,
    min_sep: usize,
    chain: bool,
    n_threads: usize,
    holes: bool,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let (ci, cj) = (slice(&i, "i")?, slice(&j, "j")?);
    let p = rwr::RwrParams { rp, window, step, max_diag, min_sep, chain, holes };
    let band = py
        .detach(|| with_threads(n_threads, || rwr::rwr_band(n, ci, cj, &p)))
        .map_err(PyValueError::new_err)?
        .map_err(PyValueError::new_err)?;
    let a = Array2::from_shape_vec((n, max_diag + 1), band).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(a.into_pyarray(py))
}

/// SnapHiC's per-diagonal z-scores of an RWR band (``uchrom.fea.impute_rwr.zscore_band``): a new
/// ``(n, max_diag + 1)`` array.
#[pyfunction]
#[pyo3(signature = (band, edge=5, trim=0.01, min_sd=1e-6, n_threads=0))]
fn zscore_band<'py>(
    py: Python<'py>,
    band: PyReadonlyArray2<'py, f64>,
    edge: usize,
    trim: f64,
    min_sd: f64,
    n_threads: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let a = band.as_array();
    let (n, w) = (a.shape()[0], a.shape()[1]);
    if w == 0 {
        return Err(PyValueError::new_err("band: at least one column"));
    }
    let mut data: Vec<f64> = a.iter().cloned().collect();
    py.detach(|| with_threads(n_threads, || rwr::zscore_band(&mut data, n, w - 1, edge, trim, min_sd)))
        .map_err(PyValueError::new_err)?;
    let out = Array2::from_shape_vec((n, w), data).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(out.into_pyarray(py))
}

/// SnapHiC's local background of every pixel (``uchrom.strc.loop.snaphic``): ``(n, out_diag + 1)``.
#[pyfunction]
#[pyo3(signature = (z, out_diag, inner=2, outer=5, n_threads=0))]
fn local_background<'py>(
    py: Python<'py>,
    z: PyReadonlyArray2<'py, f64>,
    out_diag: usize,
    inner: usize,
    outer: usize,
    n_threads: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let a = z.as_array();
    let (n, w) = (a.shape()[0], a.shape()[1]);
    if w == 0 || out_diag + 1 > w {
        return Err(PyValueError::new_err("z: needs at least out_diag + 1 columns"));
    }
    let data: Vec<f64> = a.iter().cloned().collect();
    let lb = py
        .detach(|| with_threads(n_threads, || rwr::local_background(&data, n, w - 1, out_diag, inner, outer)))
        .map_err(PyValueError::new_err)?;
    let out = Array2::from_shape_vec((n, out_diag + 1), lb).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(out.into_pyarray(py))
}

/// SnapHiC's sums over cells for one chromosome (``uchrom.strc.loop.snaphic``).  ``i``, ``j``: the contacts
/// of all cells concatenated, cell ``c`` at ``cell_ptr[c] : cell_ptr[c + 1]``.  Returns a dict of
/// ``(n, out_diag + 1)`` arrays ``sum_z``, ``sum_l``, ``sum_d``, ``sum_dd`` (float64), ``n_out`` (int64).
#[pyfunction]
#[pyo3(signature = (n, i, j, cell_ptr, rp, window, step, max_diag, out_diag, edge=5, trim=0.01, min_sd=1e-6,
                    inner=2, outer=5, outlier=1.96, min_sep=2, chain=true, batch=0, n_threads=0, holes=false))]
#[allow(clippy::too_many_arguments)]
fn snaphic_chrom<'py>(
    py: Python<'py>,
    n: usize,
    i: PyReadonlyArray1<'py, i64>,
    j: PyReadonlyArray1<'py, i64>,
    cell_ptr: PyReadonlyArray1<'py, i64>,
    rp: f64,
    window: usize,
    step: usize,
    max_diag: usize,
    out_diag: usize,
    edge: usize,
    trim: f64,
    min_sd: f64,
    inner: usize,
    outer: usize,
    outlier: f64,
    min_sep: usize,
    chain: bool,
    batch: usize,
    n_threads: usize,
    holes: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let (ci, cj, cp) = (slice(&i, "i")?, slice(&j, "j")?, slice(&cell_ptr, "cell_ptr")?);
    if cp.is_empty() || cp[0] != 0 || cp[cp.len() - 1] as usize != ci.len() || cp.windows(2).any(|w| w[1] < w[0]) {
        return Err(PyValueError::new_err("cell_ptr: non-decreasing offsets from 0 to len(i)"));
    }
    let cells: Vec<(&[i64], &[i64])> =
        cp.windows(2).map(|w| (&ci[w[0] as usize..w[1] as usize], &cj[w[0] as usize..w[1] as usize])).collect();
    let rw = rwr::RwrParams { rp, window, step, max_diag, min_sep, chain, holes };
    let sp = rwr::SnapParams { edge, trim, min_sd, inner, outer, out_diag, outlier, batch };
    let acc = py
        .detach(|| with_threads(n_threads, || rwr::snaphic_chrom(n, &cells, &rw, &sp)))
        .map_err(PyValueError::new_err)?
        .map_err(PyValueError::new_err)?;
    let d = PyDict::new(py);
    let shape = (n, out_diag + 1);
    let to2 = |v: Vec<f64>| Array2::from_shape_vec(shape, v).map_err(|e| PyValueError::new_err(e.to_string()));
    d.set_item("sum_z", to2(acc.sum_z)?.into_pyarray(py))?;
    d.set_item("sum_l", to2(acc.sum_l)?.into_pyarray(py))?;
    d.set_item("sum_d", to2(acc.sum_d)?.into_pyarray(py))?;
    d.set_item("sum_dd", to2(acc.sum_dd)?.into_pyarray(py))?;
    let no = Array2::from_shape_vec(shape, acc.n_out).map_err(|e| PyValueError::new_err(e.to_string()))?;
    d.set_item("n_out", no.into_pyarray(py))?;
    d.set_item("n_cells", acc.n_cells)?;
    Ok(d)
}

/// Threads of rayon's global pool (``RAYON_NUM_THREADS`` or the number of cores).
#[pyfunction]
fn default_threads() -> usize {
    rayon::current_num_threads()
}

#[pymodule]
fn _kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", crate::VERSION)?;
    m.add_function(wrap_pyfunction!(hiccups_score, m)?)?;
    m.add_function(wrap_pyfunction!(mustache_scan, m)?)?;
    m.add_function(wrap_pyfunction!(gaussian_filter, m)?)?;
    m.add_function(wrap_pyfunction!(pairwise_sum, m)?)?;
    m.add_function(wrap_pyfunction!(default_threads, m)?)?;
    m.add_function(wrap_pyfunction!(rwr_band, m)?)?;
    m.add_function(wrap_pyfunction!(zscore_band, m)?)?;
    m.add_function(wrap_pyfunction!(local_background, m)?)?;
    m.add_function(wrap_pyfunction!(snaphic_chrom, m)?)?;
    Ok(())
}
