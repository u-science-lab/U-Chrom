| dataset | modality | metric | ExN | InN | Astro | Oligo | OPC | Micro | ExN - Oligo [95% CI] | Cliff | depth-adj. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hires_brain | scHi-C | contact ratio | 1.320 | 1.407 | 0.138 | -0.225 |  |  | +1.545 [+1.465, +1.648] | +1.00 | +1.526 [+1.440, +1.606] |
| gageseq_mouse_cortex | scHi-C | contact ratio | 1.692 | 1.625 | 0.455 | -0.089 | 0.994 | -0.576 | +1.780 [+1.718, +1.820] | +0.96 | +1.603 [+1.537, +1.669] |
| droplet_hic_mouse_cortex | scHi-C | contact ratio | 0.847 | 1.005 | 0.352 | 0.271 | 0.968 | -0.053 | +0.576 [+0.516, +0.629] | +0.59 | +0.440 [+0.398, +0.485] |
| paired_hic_mouse_cortex | scHi-C | pooled ratio | 0.944 | 1.132 | 0.242 | 0.224 | 0.749 | -0.256 | +0.720 [+0.690, +0.753] |  |  |
| dschic_aging_cortex | scHi-C | contact ratio | 1.389 | 1.549 | 0.492 | 0.169 | 1.000 | 0.007 | +1.220 [+1.200, +1.237] | +0.89 | +1.094 [+1.083, +1.105] |
| schicar_mouse_cortex | scHi-C | contact ratio | 0.735 | 0.796 | -0.096 | -0.368 | 0.335 | -0.746 | +1.103 [+1.056, +1.148] | +0.92 | +1.022 [+0.977, +1.067] |
| hicrna_mouse_brain | spatial Hi-C | contact ratio | 0.875 | 0.699 | 0.532 | 0.450 |  |  | +0.425 [+0.398, +0.448] | +0.86 | +0.356 [+0.330, +0.379] |
| tan2021_cortex | scHi-C | contact ratio | 1.598 | 1.804 | 0.566 | 0.149 | 1.142 | -0.337 | +1.449 [+1.357, +1.523] | +1.00 | +1.386 [+1.294, +1.484] |
| hicrna_mouse_brain_domains_r1 | spatial Hi-C | contact ratio | cortex 0.933 | WM 0.527 |  |  |  |  | +0.406 [+0.392, +0.424] | +0.92 | +0.378 [+0.367, +0.390] |
| liu2025_mop | imaging | dist ratio | 1.164 | 1.262 | 0.960 | 0.898 | 1.069 | 0.811 | +0.266 [+0.259, +0.274] | +0.79 | +0.255 [+0.247, +0.263] |
| takei2021_brain_labels | imaging | dist ratio | 1.305 | 1.339 | 0.951 | 1.113 |  | 0.696 | +0.192 [+0.085, +0.317] | +0.57 | +0.196 [+0.126, +0.260] |
| takei2021_brain_kmeans | imaging | dist ratio | 1.168 | 1.186 | 0.759 | 0.928 |  | 0.415 | +0.240 [+0.190, +0.304] | +0.71 | +0.260 [+0.202, +0.313] |
| tan2021_dipc_rep1 | 3-D models from contacts | dist ratio | 1.293 | 1.405 | 1.094 | 1.049 | 1.285 | 0.914 | +0.244 [+0.228, +0.264] | +1.00 | +0.248 [+0.234, +0.262] |

- Kendall's W sequencing_core4: 0.93 (8 datasets x 4 classes, P = 5.9e-05); mean ranks {"ExN": 3.25, "InN": 3.75, "Astro": 2.0, "Oligo": 1.0}
- Kendall's W sequencing_6: 0.97 (6 datasets x 6 classes, P = 2.4e-05); mean ranks {"ExN": 5.0, "InN": 5.83, "Astro": 3.0, "Oligo": 2.0, "OPC": 4.17, "Micro": 1.0}
- Kendall's W sequencing_plus_liu_core4: 0.93 (9 datasets x 4 classes, P = 1.4e-05); mean ranks {"ExN": 3.22, "InN": 3.78, "Astro": 2.0, "Oligo": 1.0}
- Kendall's W sequencing_plus_liu_6: 0.97 (7 datasets x 6 classes, P = 2.4e-06); mean ranks {"ExN": 5.0, "InN": 5.86, "Astro": 3.0, "Oligo": 2.0, "OPC": 4.14, "Micro": 1.0}
- Kendall's W sequencing_plus_imaging_core4: 0.90 (10 datasets x 4 classes, P = 5.9e-06); mean ranks {"ExN": 3.2, "InN": 3.8, "Astro": 1.9, "Oligo": 1.1}

| dataset | Astro - Oligo [95% CI] | Cliff |
|---|---|---|
| hires_brain | +0.363 [+0.209, +0.577] | +0.88 |
| gageseq_mouse_cortex | +0.543 [+0.477, +0.591] | +0.74 |
| droplet_hic_mouse_cortex | +0.081 [+0.002, +0.152] | +0.03 |
| dschic_aging_cortex | +0.324 [+0.301, +0.346] | +0.34 |
| schicar_mouse_cortex | +0.271 [+0.218, +0.322] | +0.51 |
| hicrna_mouse_brain | +0.082 [+0.052, +0.108] | +0.35 |
| tan2021_cortex | +0.417 [+0.281, +0.521] | +0.76 |
| liu2025_mop | +0.062 [+0.053, +0.075] | +0.25 |
| takei2021_brain_labels | -0.162 [-0.277, -0.046] | -0.39 |
| takei2021_brain_kmeans | -0.169 [-0.219, -0.093] | -0.38 |
| tan2021_dipc_rep1 | +0.045 [+0.021, +0.073] | +0.52 |
