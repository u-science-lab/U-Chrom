"""``uchrom_recon`` -> the frozen EMber engine build ``dipfrozen`` (tag ember-diploid-frozen), which predates the
rename and installs as ``uchrom_nucdyn``.  The screcon runners differ from that build's only by the import name
(``run_diploid.py``, ``run_robust.py``, ``run_nucdyn.py``); recon.sbatch puts this folder ahead of the build."""
import sys

import uchrom_nucdyn

sys.modules[__name__] = uchrom_nucdyn
