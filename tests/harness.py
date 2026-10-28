import importlib, json
from pathlib import Path
import fakes


def run(tmp, ct=None, other=None, staff=None, directory_up=True, extra_args=(), overrides_rows=None):
    import talentpool.common as common, talentpool.directory as directory, talentpool.sources as sources, talentpool.run as run_mod
    common.REQUEST_FAILURES.clear()
    sources.STATS.clear()
    d_ct, d_other = fakes.default_works()
    directory.SESSION = fakes.FakeSession(staff, directory_up)
    sources.get = fakes.make_get(ct if ct is not None else d_ct, other if other is not None else d_other)
    sources.post_json = fakes.post_json
    tmp = Path(tmp)
    ov = tmp / "overrides.csv"
    if overrides_rows is not None or not ov.exists():
        from talentpool.review import OVERRIDE_FIELDS
        from talentpool.common import write_csv
        write_csv(ov, overrides_rows or [], OVERRIDE_FIELDS)
    args = ["--out", str(tmp / "out"), "--site-dir", str(tmp / "site"), "--data-dir", str(tmp / "data"),
            "--overrides", str(ov), "--faculty-extra", str(tmp / "faculty_extra.csv"), *extra_args]
    payload = run_mod.main(args)
    report = json.loads((tmp / "out" / "run_report.json").read_text())
    return payload, report
