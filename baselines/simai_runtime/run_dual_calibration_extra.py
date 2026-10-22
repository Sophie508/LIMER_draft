from dual_calibration_library import run, ROOT
import json

cases=[('ecn_v1_dual_b10_healthy',200,20,False),('ecn_v1_dual_a20_b10_stay',40,20,False)]
(ROOT/'logs/dual_plane_extra_registration.json').write_text(json.dumps(cases,indent=2)+'\n')
results=[run(*case) for case in cases]
(ROOT/'logs/dual_plane_extra_summary.json').write_text(json.dumps(results,indent=2)+'\n')
