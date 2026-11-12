"""Plot matched measured completion times; no illustrative performance values."""
import json
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def main(report):
    full = read(report)['rows']
    matched = {row['family']: row for row in full
               if row['seed'] == 111210016 and row['helper_mode'] == 'shared'}
    prior = ROOT.parent / '2026-11-12-integration/results'
    old = {row['family']: row for group in ('development-v1', 'gray-full-v1')
           for row in read(prior / group / 'report.json')['rows']
           if row['name'].startswith('full-ring-') and row['method'] == 'G11'
           and row['policy'] == 'always'}
    healthy = matched['healthy']['communication_ms']
    assert abs(healthy - 480.178448) < 1e-9
    labels, values, times, colors = [], [], [], []
    for family, label in (('blackhole', 'Blackhole'), ('weak_loss', '0.5% packet loss')):
        for version, duration, color in (
                ('Previous', old[family]['completion_ms'], '#99A4B2'),
                ('Revised', matched[family]['communication_ms'], '#147D92')):
            labels.append(label + '\n' + version)
            times.append(duration)
            values.append(100 * healthy / duration)
            colors.append(color)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12,
                         'svg.fonttype': 'none'})
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    ax.axvspan(70, 80, color='#D7EDE8', zorder=0)
    ax.axvline(100, color='#707D8C', linestyle='--', linewidth=1)
    ax.barh(range(4), values, color=colors, height=.58)
    for y, value, duration in zip(range(4), values, times):
        ax.text(value + 1, y, f'{value:.1f}%  /  {duration:.1f} ms',
                ha='left', va='center', fontsize=11, color='#192A3D')
    ax.set_yticks(range(4), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 110)
    ax.set_xticks([0, 25, 50, 70, 80, 100])
    ax.set_xlabel('Whole-job useful throughput relative to healthy (%)')
    ax.text(75, -.56, 'Target\n70–80%', ha='center', va='bottom', fontsize=10, color='#147D75')
    ax.set_title('Recovery throughput under faults', loc='left', fontsize=20, pad=35)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=10)
    ax.grid(axis='x', alpha=.12)
    ax.set_axisbelow(True)
    fig.text(.02, .045, 'Same 15-GiB workload • Healthy reference: 480.18 ms • Original matched seed',
             fontsize=10, color='#526174')
    pending = any(row['status']=='not_run' for row in full)
    footer = ('Fresh-seed checks are still running.' if pending else 'See RESULTS.md for fresh-seed checks.')
    fig.text(.02, .01, 'Simulation; direct recovery. Revised design includes shared helpers. ' + footer,
             fontsize=9, color='#526174')
    fig.subplots_adjust(left=.2, right=.98, top=.77, bottom=.17)
    out = ROOT / 'figures'
    out.mkdir(exist_ok=True)
    for extension in ('png', 'svg', 'pdf'):
        fig.savefig(out / ('throughput-comparison.' + extension), dpi=180, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'results/full-v2/report.json')
    main(parser.parse_args().report)
