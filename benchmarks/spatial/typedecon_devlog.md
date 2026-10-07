# Type deconvolution (PREREG §14) — development log

Development units only (POOL-dev tissues).  Every variant tried and every number goes here, dated.

## 2026-10-07 — setup

* Code and tests written; synthetic toys only (three toy types with flipped compartments: TD, NNLS and
  dominant pooling all recover them; the random-composition control does not).  Not evidence on data.
* Composition-noise levels calibrated on the composition generator (PREREG §14.3).
* Timing with fake contacts of the real size (600 / 150 spots, 8.5 / 11.6 M contacts): 1 Mb TD 0.2 s per EM
  iteration, NNLS 2 s; 250 kb TD 0.65 s per iteration, NNLS 66 s (laptop).
* No run on data: Sherlock access was denied at registration (needs a new login).
