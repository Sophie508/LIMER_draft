"""Create presentation-ready scientific figures from derived archived evidence."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
d = json.loads((ROOT / 'analysis.json').read_text())
c = d['cases']
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 15,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'svg.fonttype': 'none'})
order = [
    ('Healthy A + B', 'full-ring-healthy-G11-benefit', '#2b8a78'),
    ('Blackhole, A only', 'full-ring-blackhole-A_ONLY-always', '#8c929b'),
    ('Blackhole, direct recovery', 'full-ring-blackhole-G11-always', '#3675b5'),
    ('Weak loss, direct recovery', 'full-ring-weak_loss-G11-always', '#3675b5'),
    ('Weak loss, benefit gate', 'full-ring-weak_loss-G11-benefit', '#d18137'),
]
fig, ax = plt.subplots(figsize=(12.8, 7.2))
fig.subplots_adjust(left=.30, right=.96, top=.80, bottom=.30)
for i, (label, key, color) in enumerate(order):
    val = c[key]['communication_ms']
    ax.barh(i, val, color=color, height=.58)
    ax.text(val + 12, i, f'{val:.1f}', va='center', fontsize=16)
ax.set_yticks(range(len(order)), [x[0] for x in order])
ax.invert_yaxis()
ax.set_xlim(0, 1110)
ax.set_xlabel('Communication completion time (ms), lower is better', labelpad=13)
ax.spines['left'].set_visible(False)
ax.tick_params(axis='y', length=0, pad=12)
ax.set_axisbelow(True)
ax.grid(axis='x', color='#e7e8eb', linewidth=.8)
fig.text(.04, .93, 'Recovery performance and the healthy reference',
         fontsize=23, weight='bold')
fig.text(.04, .865, 'Blackhole recovery retains 52.9% of healthy whole-job goodput', fontsize=19)
fig.text(.04, .10, '16 logical GPUs, 30 phases, 15 GiB logical payload, 10 Gb/s per plane.\n'
         'One registered development run per arm. A-only uses A for all business traffic.\n'
         'Simulation results. Detection latency is a separate metric.', fontsize=12, color='#555d66')
for ext in ('png', 'svg'):
    fig.savefig(ROOT / f'completion_comparison.{ext}', dpi=180, facecolor='white')
plt.close(fig)

x = c['full-ring-blackhole-G11-always']
healthy_phase = c['full-ring-healthy-G11-benefit']['phases_3_to_29_mean_ms']
wait = x['helper_wait_mean_ms']
setup = x['probe_and_setup_mean_ms']
activation = wait + setup
end = x['phases_3_to_29_mean_ms']
fig, ax = plt.subplots(figsize=(12.8, 7.2))
fig.subplots_adjust(left=.18, right=.96, top=.78, bottom=.30)
ax.barh(1, healthy_phase, color='#2b8a78', height=.45)
ax.text(healthy_phase / 2, 1, f'Healthy completion\n{healthy_phase:.1f} ms',
        va='center', ha='center', color='white', fontsize=16)
segments = [(0, wait, '#9ba6b5', f'Helpers do their own work\n{wait:.1f} ms'),
            (wait, setup, '#d18137', f'Setup\n{setup:.1f} ms'),
            (activation, end - activation, '#3675b5', 'B\u2032 carries data')]
for start, width, color, label in segments:
    ax.barh(0, width, left=start, color=color, height=.45)
    ax.text(start + width / 2, 0, label, va='center', ha='center', fontsize=15, color='white')
ax.set_yticks([0, 1], ['Blackhole\nrecovery', 'Healthy\nA + B'])
ax.set_xlim(0, 34)
ax.set_ylim(-.65, 1.65)
ax.spines['left'].set_visible(False)
ax.tick_params(axis='y', length=0, pad=10)
ax.set_xlabel('Time since the current phase began (ms)', labelpad=14)
ax.axvline(activation, ymin=.08, ymax=.48, color='#3675b5', linestyle='--', linewidth=1)
ax.text(activation, -.48, f'B\u2032 active: {activation:.1f} ms', ha='center', fontsize=13)
fig.text(.04, .93, 'B\u2032 becomes available after a healthy phase finishes',
         fontsize=23, weight='bold')
fig.text(.04, .855, 'A continues sending throughout the wait and setup', fontsize=19)
fig.text(.04, .11, 'Descriptive means over phases 3\u201329 (zero-based), source 0 and source 15.\n'
         'Phase completion includes all workers. These bars summarize logged timing intervals,\n'
         'not a causal attribution of all lost performance. The physical B fault persists.',
         fontsize=12, color='#555d66')
for ext in ('png', 'svg'):
    fig.savefig(ROOT / f'phase_timing.{ext}', dpi=180, facecolor='white')
plt.close(fig)
print('Created two PNG figures and two SVG figures.')
