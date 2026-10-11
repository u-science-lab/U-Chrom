| dataset | modality | metric | ExN | InN | Astro | Oligo | OPC | Micro | ExN - Oligo [95% CI] | Cliff | depth-adj. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hires_brain | scHi-C | contact ratio | 1.320 | 1.407 | 0.138 | -0.225 |  |  | +1.545 [+1.465, +1.648] | +1.00 | +1.526 [+1.440, +1.606] |
| gageseq_mouse_cortex | scHi-C | contact ratio | 1.692 | 1.625 | 0.455 | -0.089 | 0.994 | -0.576 | +1.780 [+1.716, +1.822] | +0.96 | +1.603 [+1.527, +1.667] |
| droplet_hic_mouse_cortex | scHi-C | contact ratio | 0.847 | 1.005 | 0.352 | 0.271 | 0.968 | -0.053 | +0.576 [+0.519, +0.625] | +0.59 | +0.440 [+0.397, +0.486] |
| paired_hic_mouse_cortex | scHi-C | pooled ratio | 0.944 | 1.132 | 0.242 | 0.224 | 0.749 | -0.256 | +0.720 [+0.688, +0.752] |  |  |
| dschic_aging_cortex | scHi-C | contact ratio | 1.389 | 1.549 | 0.492 | 0.169 | 1.000 | 0.007 | +1.220 [+1.201, +1.237] | +0.89 | +1.094 [+1.083, +1.106] |
| schicar_mouse_cortex | scHi-C | contact ratio | 0.735 | 0.796 | -0.096 | -0.368 | 0.335 | -0.746 | +1.103 [+1.054, +1.145] | +0.92 | +1.022 [+0.974, +1.067] |
| hicrna_mouse_brain | spatial Hi-C | contact ratio | 0.875 | 0.699 | 0.532 | 0.450 |  |  | +0.425 [+0.397, +0.445] | +0.86 | +0.356 [+0.331, +0.380] |
| tan2021_cortex | scHi-C | contact ratio | 1.598 | 1.804 | 0.566 | 0.149 | 1.142 | -0.337 | +1.449 [+1.358, +1.520] | +1.00 | +1.386 [+1.297, +1.496] |
| hicrna_mouse_brain_domains_r1 | spatial Hi-C | contact ratio | cortex 0.933 | WM 0.527 |  |  |  |  | +0.406 [+0.391, +0.424] | +0.92 | +0.378 [+0.367, +0.389] |
| takei2021_brain_labels | imaging | dist ratio | 1.250 | 1.279 | 0.902 | 1.050 |  | 0.659 | +0.200 [+0.145, +0.293] | +0.59 | +0.200 [+0.143, +0.254] |
| takei2021_brain_kmeans | imaging | dist ratio | 1.123 | 1.134 | 0.727 | 0.895 |  | 0.431 | +0.228 [+0.194, +0.292] | +0.70 | +0.252 [+0.197, +0.305] |
| tan2021_dipc_rep1 | 3-D models from contacts | dist ratio | 1.234 | 1.349 | 1.037 | 0.995 | 1.225 | 0.869 | +0.239 [+0.217, +0.254] | +1.00 | +0.237 [+0.222, +0.251] |

- Kendall's W sequencing_core4: 0.93 (8 datasets x 4 classes, P = 5.9e-05); mean ranks {"ExN": 3.25, "InN": 3.75, "Astro": 2.0, "Oligo": 1.0}
- Kendall's W sequencing_6: 0.97 (6 datasets x 6 classes, P = 2.4e-05); mean ranks {"ExN": 5.0, "InN": 5.83, "Astro": 3.0, "Oligo": 2.0, "OPC": 4.17, "Micro": 1.0}
- Kendall's W sequencing_plus_imaging_labels_core4: 0.89 (9 datasets x 4 classes, P = 2.4e-05); mean ranks {"ExN": 3.22, "InN": 3.78, "Astro": 1.89, "Oligo": 1.11}
