"""chromdata.settings: the free memory is bounded by the job's limit (Slurm environment, cgroup)."""

import sys

from chromdata.settings import _available_ram, _job_memory_limit

settings_module = sys.modules["chromdata.settings"]          # the module (chromdata.settings is also the object)


def test_slurm_limit_bounds_available_ram(monkeypatch):
    for k in ("SLURM_MEM_PER_NODE", "SLURM_MEM_PER_CPU", "SLURM_CPUS_ON_NODE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(settings_module, "open", lambda *a, **k: (_ for _ in ()).throw(OSError()), raising=False)
    assert _job_memory_limit() is None
    monkeypatch.setenv("SLURM_MEM_PER_NODE", "1024")                  # MB
    assert _job_memory_limit() == 1024 << 20
    assert _available_ram() <= 1024 << 20
    monkeypatch.delenv("SLURM_MEM_PER_NODE")
    monkeypatch.setenv("SLURM_MEM_PER_CPU", "512")
    monkeypatch.setenv("SLURM_CPUS_ON_NODE", "4")
    assert _job_memory_limit() == 2048 << 20


def test_cgroup_v2_limit(monkeypatch, tmp_path):
    for k in ("SLURM_MEM_PER_NODE", "SLURM_MEM_PER_CPU", "SLURM_CPUS_ON_NODE"):
        monkeypatch.delenv(k, raising=False)
    files = {"/proc/self/cgroup": "0::/job_1\n", "/sys/fs/cgroup/job_1/memory.max": "3221225472\n",
             "/sys/fs/cgroup/job_1/memory.current": "1073741824\n"}
    real_open = open

    def fake_open(path, *a, **k):
        if path in files:
            p = tmp_path / path.strip("/").replace("/", "_")
            p.write_text(files[path])
            return real_open(p, *a, **k)
        raise OSError(path)

    monkeypatch.setattr(settings_module, "open", fake_open, raising=False)
    assert _job_memory_limit() == 2 << 30                            # limit - usage
