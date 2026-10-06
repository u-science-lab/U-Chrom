# Export the Seurat objects of Chen, Guo et al. 2026 (Nat Methods; Zenodo 17961135) to plain files
# that build_spatial_hic_chen2026.py assembles into .chromdata.zarr stores.
#
#   Rscript apps/atlas/recipes/spatial_hic_chen2026_export.R <file.qs> <out_dir>
#
# A .qs holds one Seurat object or a named list of them (one per tissue section).  For every
# section <out_dir>/<section>/ receives:
# A section is a list entry, or one image of an object that merges several sections.
#   object.txt        name of the Seurat object the section comes from (embeddings are per object)
#   factors.txt       meta.csv columns that are factors (clusters, annotations)
#   meta.csv          spot metadata (meta.data) + spot, grid column/row parsed from the spot name
#                     ("<col>x<row>") and the image coordinates of GetTissueCoordinates()
#   image.png         the section's tissue image (spot coordinates are in its pixels, scale 1);
#   image.txt         the image class and scale factors
#   red_<name>.csv    cell embeddings of each reduction (pca, umap, ...)
#   assay_<name>/     the assay's "counts" layer (its "data" layer when counts is empty, named in
#                     layer.txt) as a compressed sparse column matrix (features x spots):
#                     features.txt, spots.txt, p.i32, i.i32, x.f32, shape.txt
# SCT, spARC_* (smoothed) and *_scale assays are derivatives and are not exported.
# Bin names are normalised to chrN:start-end with start < end (one section writes them reversed).
# Needs R packages qs (0.27.3 from the CRAN archive) and Seurat >= 5.

suppressMessages({ library(qs); library(Seurat); library(Matrix) })

args <- commandArgs(TRUE)
stopifnot(length(args) == 2)
obj <- qread(args[1], nthreads = 4)
out <- args[2]
if (inherits(obj, "Seurat")) {
  obj <- setNames(list(obj), sub("\\.qs$", "", basename(args[1])))
}

fix_bin <- function(f) {
  m <- regmatches(f, regexec("^(chr[^:]+):([0-9]+)-([0-9]+)$", f))
  vapply(m, function(x) {
    if (length(x) != 4) return(NA_character_)
    a <- as.numeric(x[3]); b <- as.numeric(x[4])
    sprintf("%s:%.0f-%.0f", x[2], min(a, b), max(a, b))
  }, character(1))
}

write_csc <- function(mat, dir, features, spots) {
  dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  mat <- as(mat, "CsparseMatrix")
  if (!inherits(mat, "dgCMatrix")) mat <- as(mat, "dgCMatrix")
  writeLines(features, file.path(dir, "features.txt"))
  writeLines(spots, file.path(dir, "spots.txt"))
  writeLines(as.character(dim(mat)), file.path(dir, "shape.txt"))
  writeBin(as.integer(mat@p), file.path(dir, "p.i32"), size = 4)
  writeBin(as.integer(mat@i), file.path(dir, "i.i32"), size = 4)
  writeBin(as.numeric(mat@x), file.path(dir, "x.f32"), size = 4)
}

skip_assay <- function(a) a == "SCT" || grepl("^spARC", a) || grepl("_scale$", a)

# one entry per tissue section: (object name, section name, spots); an object that merges several
# sections (one image each) is split by image
units <- list()
for (on in names(obj)) {
  o <- obj[[on]]
  imgs <- Images(o)
  if (length(imgs) > 1) {
    for (img in imgs) units[[length(units) + 1]] <- list(obj = on, sec = img, cells = Cells(o[[img]]), image = img)
  } else {
    sec <- if (length(names(obj)) > 1 || !length(imgs)) on else imgs[1]
    units[[length(units) + 1]] <- list(obj = on, sec = sec, cells = colnames(o), image = if (length(imgs)) imgs[1] else NA)
  }
}

for (u in units) {
  o <- obj[[u$obj]]
  cells <- u$cells
  d <- file.path(out, u$sec)
  dir.create(d, recursive = TRUE, showWarnings = FALSE)
  writeLines(u$obj, file.path(d, "object.txt"))
  md <- o@meta.data[cells, , drop = FALSE]
  md$spot <- cells
  grid <- do.call(rbind, strsplit(sub(".*_", "", cells), "x", fixed = TRUE))
  md$grid_col <- as.integer(grid[, 1])
  md$grid_row <- as.integer(grid[, 2])
  md$image <- u$image
  if (!is.na(u$image)) {
    tc <- GetTissueCoordinates(o, image = u$image)
    if ("cell" %in% colnames(tc)) rownames(tc) <- tc$cell
    tc <- tc[cells, , drop = FALSE]
    for (cn in colnames(tc)) if (is.numeric(tc[[cn]])) md[[paste0("image_", cn)]] <- tc[[cn]]
    im <- o@images[[u$image]]
    png::writePNG(im@image, file.path(d, "image.png"))
    sf <- unlist(im@scale.factors)
    writeLines(c(class(im)[1], paste(names(sf), sf)), file.path(d, "image.txt"))
  }
  write.csv(md, file.path(d, "meta.csv"), row.names = FALSE)
  writeLines(names(md)[vapply(md, is.factor, logical(1))], file.path(d, "factors.txt"))
  for (r in Reductions(o)) {
    e <- Embeddings(o, reduction = r)
    e <- e[intersect(cells, rownames(e)), , drop = FALSE]
    write.csv(data.frame(spot = rownames(e), e, check.names = FALSE), file.path(d, paste0("red_", r, ".csv")),
              row.names = FALSE)
  }
  used <- c()
  for (a in Assays(o)) {
    if (skip_assay(a)) next  # SCT-corrected, smoothed or scaled derivatives of an exported assay
    layer <- "counts"
    x <- suppressWarnings(GetAssayData(o, assay = a, layer = "counts"))
    if (!all(dim(x) > 0)) { layer <- "data"; x <- GetAssayData(o, assay = a, layer = "data") }
    x <- x[, cells, drop = FALSE]
    f <- rownames(x)
    if (all(grepl("^chr[^:]+:[0-9]+-[0-9]+$", f))) f <- fix_bin(f)
    write_csc(x, file.path(d, paste0("assay_", a)), f, colnames(x))
    writeLines(layer, file.path(d, paste0("assay_", a), "layer.txt"))
    used <- c(used, paste0(a, "[", layer, "]"))
  }
  cat(sprintf("%s (%s): %d spots, assays %s, reductions %s\n", u$sec, u$obj, length(cells),
              paste(used, collapse = ","), paste(Reductions(o), collapse = ",")))
}
