"""Run the unmodified 2017 nuc_dynamics (tjs23/nuc_dynamics master) with per-stage wall-clock timing.

Only wraps ``anneal_genome`` to time it; the physics / restraints / schedule are the original code.
Usage: python orig_run.py NCC OUT.n3d --models M --cpu C --sizes 8 4 2 0.4 0.2 0.1 --seed S [--temps T]
"""
import argparse, json, os, resource, sys, time

HERE = os.environ.get("NUCDYN_MASTER_DIR", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import nuc_dynamics as nd  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ncc")
    ap.add_argument("out")
    ap.add_argument("--models", type=int, default=1)
    ap.add_argument("--cpu", type=int, default=1)
    ap.add_argument("--sizes", type=float, nargs="+", default=[8, 4, 2, 0.4, 0.2, 0.1])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--temps", type=int, default=500)
    ap.add_argument("--dyns", type=int, default=100)
    ap.add_argument("--serial", action="store_true",
                    help="anneal the models one after another in this process (the original anneal_model, "
                         "no process pool): exact single-core cost, velocities reproducible from --seed")
    ap.add_argument("--json")
    a = ap.parse_args()

    stages = []
    orig = nd.anneal_genome

    def timed(chromosomes, contact_dict, num_models, particle_size, *args, **kw):
        n_contacts = sum(v.shape[1] for d in contact_dict.values() for v in d.values())
        counters = getattr(nd.dyn_util, "reset_counters", None)  # only in an instrumented build
        if counters:
            counters()
        t0, c0 = time.perf_counter(), time.process_time()
        out = orig(chromosomes, contact_dict, num_models, particle_size, *args, **kw)
        dt, dc = time.perf_counter() - t0, time.process_time() - c0
        n_part = sum(len(v) for v in out[1].values())
        stages.append({"particle_size": int(particle_size), "n_particles": n_part, "n_contacts": int(n_contacts),
                       "n_models": num_models, "wall_s": dt, "cpu_s_this_process": dc,
                       "loadavg_1min_end": os.getloadavg()[0]})
        if counters and a.serial:
            stages[-1]["neighbour_list_counters"] = nd.dyn_util.get_counters()
            print("COUNTERS", stages[-1]["neighbour_list_counters"], flush=True)
        print(f"STAGE {int(particle_size)} particles={n_part} contacts={n_contacts} models={num_models} "
              f"wall={dt:.1f}s cpu={dc:.1f}s load={os.getloadavg()[0]:.1f}", flush=True)
        return out

    nd.anneal_genome = timed
    if a.serial:
        def serial_job(target_func, split_data, common_args, num_cpu=1, collect_output=True):
            out = [target_func(item, *common_args) for item in split_data]
            for r in out:
                if isinstance(r, Exception):
                    raise r
            return out
        nd.parallel_split_job = serial_job
    gp = {"dist_power_law": -0.33, "contact_dist_lower": 0.8, "contact_dist_upper": 1.2,
          "backbone_dist_lower": 0.1, "backbone_dist_upper": 1.1, "random_seed": a.seed, "random_radius": 10.0}
    ap_ = {"temp_start": 5000.0, "temp_end": 10.0, "temp_steps": a.temps, "dynamics_steps": a.dyns, "time_step": 0.001}
    sizes = sorted([s * 1e6 for s in a.sizes], reverse=True)
    t0 = time.perf_counter()
    nd.calc_genome_structure(a.ncc, a.out, gp, ap_, sizes, a.models, 2e6, "n3d", a.cpu, None, False)
    total = time.perf_counter() - t0
    ru_self = resource.getrusage(resource.RUSAGE_SELF)
    ru_ch = resource.getrusage(resource.RUSAGE_CHILDREN)
    res = {"ncc": a.ncc, "out": a.out, "models": a.models, "cpu": a.cpu, "sizes": sizes, "temps": a.temps,
           "dyns": a.dyns, "seed": a.seed, "serial": a.serial, "total_wall_s": total, "stages": stages,
           "maxrss_self_mb": ru_self.ru_maxrss / 2**20, "maxrss_children_mb": ru_ch.ru_maxrss / 2**20,
           "cpu_user_s": ru_self.ru_utime + ru_ch.ru_utime}
    print(json.dumps(res, indent=1))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
