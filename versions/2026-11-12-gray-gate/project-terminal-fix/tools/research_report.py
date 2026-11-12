"""Render bounded results from a completed, immutable research campaign.

This postprocessor does not change registered cases, scoring, or attempts.
Matplotlib is required only for --plots. Use the frozen scorer and integrity
verifier before interpreting this report.
"""
import argparse
import csv
from copy import deepcopy
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
import tempfile


LABELS = {
    'healthy': ('Healthy', '健康'),
    'blackhole': ('Persistent blackhole', '持续黑洞'),
    'quarter': ('B capacity 25%', 'B 容量降至 25%'),
    'weak_loss': ('0.5% packet loss', '0.5% 弱丢包'),
    'delay': ('80 ms link delay', '链路延迟增至 80 ms'),
    'transient_2ms': ('2 ms transient', '2 ms 短暂故障'),
    'slow_proxy_1gbps': ('1 Gb/s helper, blackhole', '黑洞 + 1 Gb/s 慢代理'),
    'no_idle_helpers': ('No idle helpers', '无空闲代理'),
    'slow_proxy_quarter': ('1 Gb/s helper, B at 25%', 'B 降速 + 1 Gb/s 慢代理'),
}


def load(path):
    return json.loads(path.read_text())


def truth(value):
    if value not in ('True', 'False'):
        raise ValueError('Unexpected boolean: ' + str(value))
    return value == 'True'


def number(value):
    return float(value) if value not in ('', None) else None


def fmt(value, digits=2):
    return '∞ / 未确定' if value is None else f'{value:.{digits}f}'


def summary_matches(expected, retained):
    """Allow only sub-picosecond mean rounding across Python sum versions.

    Per-trial rows, pair rows, counts, identities and all other summary fields
    remain exact. Do not alter retained data or the campaign's frozen scorer.
    """
    if expected == retained:
        return True
    expected, retained = deepcopy(expected), deepcopy(retained)
    left, right = expected.get('groups'), retained.get('groups')
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if 'mean_capped_ms' in a and 'mean_capped_ms' in b:
            x, y = a.pop('mean_capped_ms'), b.pop('mean_capped_ms')
            if (type(x) not in (int, float) or type(y) not in (int, float)
                    or not math.isfinite(x) or not math.isfinite(y)
                    or not math.isclose(x, y, rel_tol=0, abs_tol=1e-9)):
                return False
    return expected == retained


def verify_aggregates(root):
    """Rebuild derived tables in isolation with this campaign's frozen scorer.

    Symlink read-only inputs into a temporary root; only derived outputs are
    written there. Never overwrite the retained aggregates to hide a mismatch.
    """
    spec = importlib.util.spec_from_file_location('_limer_report_integrity',
                Path(__file__).with_name('verify_research.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix='limer-report-aggregate-check-') as temporary:
        temporary = Path(temporary)
        for name in ('registration.json', 'build.json', 'tooling', 'cases', 'attempts', 'runs'):
            (temporary/name).symlink_to(root/name, target_is_directory=(root/name).is_dir())
        with helper.frozen_scorer(root/'tooling') as scorer:
            scorer.summarize(temporary)
        if not summary_matches(load(temporary/'research_summary.json'), load(root/'research_summary.json')):
            raise ValueError('Retained summary differs from frozen aggregate replay')
        for name in ('research_trials.csv', 'research_pairs.csv'):
            expected, actual = temporary/name, root/name
            if expected.exists() != actual.exists():
                raise ValueError('Derived table presence differs from frozen aggregate replay: '+name)
            if expected.exists():
                with expected.open(newline='') as stream:
                    expected_rows = list(csv.DictReader(stream))
                with actual.open(newline='') as stream:
                    actual_rows = list(csv.DictReader(stream))
                if expected_rows != actual_rows:
                    raise ValueError('Retained table differs from frozen aggregate replay: '+name)


def report(root, out, plots=False, independent_loss_campaign=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    verify_aggregates(root)
    summary, reg = load(root / 'research_summary.json'), load(root / 'registration.json')
    if not summary['complete'] or summary['attempted'] != summary['registered']:
        raise ValueError('Refusing to present an incomplete campaign as final')
    with (root / 'research_trials.csv').open() as stream:
        trials = list(csv.DictReader(stream))
    with (root / 'research_pairs.csv').open() as stream:
        pairs = list(csv.DictReader(stream))
    assert len(trials) == summary['registered']
    loss_root = Path(independent_loss_campaign).resolve() if independent_loss_campaign else None
    loss_trials, loss_summary, loss_reg = [], None, None
    if loss_root:
        verify_aggregates(loss_root)
        loss_summary, loss_reg = load(loss_root/'research_summary.json'), load(loss_root/'registration.json')
        if (not loss_summary['complete'] or loss_summary['attempted'] != loss_summary['registered']
            or loss_summary['primary_conditions'] != ['weak_loss']):
            raise ValueError('Independent loss confirmation is incomplete or has a different primary scope')
        if loss_reg['plan'].get('supplement', {}).get('reference_plan_sha256') != reg['plan_sha256']:
            raise ValueError('Independent confirmation is not linked to this reference plan')
        if (loss_reg['binary_sha256'] != reg['binary_sha256'] or
            loss_reg['source_hashes'] != reg['source_hashes'] or
            loss_reg['plan']['scoring']['detector_parameters'] != reg['plan']['scoring']['detector_parameters']):
            raise ValueError('Supplemental confirmation changed the native implementation or detector parameters')
        for module in ('detector/service_detector.py', 'service_replay.py', 'benefit_policy.py', 'policy_replay.py', 'audit.py'):
            name = 'python/limerlab/' + module
            if reg['tooling_hashes'][name] != loss_reg['tooling_hashes'][name]:
                raise ValueError('Supplemental confirmation changed a core algorithm or auditor: ' + name)
        with (loss_root/'research_trials.csv').open() as stream:
            loss_trials = list(csv.DictReader(stream))
        if len(loss_trials) != 60 or any(r['condition'] != 'weak_loss' or r['arm'] != 'benefit' for r in loss_trials):
            raise ValueError('Expected exactly 60 benefit-only independent loss trials')
        if len({int(r['seed'])+int(r['node']) for r in loss_trials}) != 60:
            raise ValueError('Supplemental confirmation still reuses derived loss streams')
        old_cases = {c['trial']: c for c in reg['plan']['cases']
                     if c['condition']=='weak_loss' and c['arm']=='benefit'}
        old_streams = {c['scene']['seed']+c['scene']['node'] for c in reg['plan']['cases']}
        for case in loss_reg['plan']['cases']:
            old_scene = old_cases[case['trial']]['scene']
            if any(value != old_scene[key] for key, value in case['scene'].items()
                   if key not in ('seed', 'node', 'fault_ns')):
                raise ValueError('Supplemental confirmation changed the reference workload')
            if case['scene']['seed']+case['scene']['node'] in old_streams:
                raise ValueError('Supplemental confirmation reused a reference loss stream')
    by_pair = defaultdict(dict)
    for row in trials:
        by_pair[row['pair_id']][row['arm']] = row
    primary, policy = [], []
    for condition in summary['primary_conditions']:
        source_summary = loss_summary if condition == 'weak_loss' and loss_root else summary
        source_trials = loss_trials if condition == 'weak_loss' and loss_root else trials
        group = next(g for g in source_summary['groups'] if g['condition'] == condition and
                     g['arm'] == 'benefit' and g['detector'] == 'service')
        members = [r for r in source_trials if r['condition'] == condition and r['arm'] == 'benefit']
        unique_streams = len({int(r['seed'])+int(r['node']) for r in members}) if condition == 'weak_loss' else None
        confidence_eligible = condition != 'weak_loss' or unique_streams == len(members)
        finite = [number(r['all_paths_delay_ms']) if truth(r['valid']) else None for r in members]
        primary.append(dict(condition=condition, registered=group['registered'],
            timely=group['timely_trials'], classifications=group['classifications'],
            p95_ms=group['p95_all_trials_ms'], max_ms=(max(finite) if finite and None not in finite else None),
            exact_one_sided_95_lower=group['exact_one_sided_95_lower'] if confidence_eligible else None,
            unique_derived_loss_stream_pairs=unique_streams,
            campaign=loss_root.name if condition == 'weak_loss' and loss_root else root.name,
            invalid=group['invalid_or_missing']))
    pair_groups = defaultdict(list)
    for pair in pairs:
        arms = by_pair[pair['pair_id']]
        assert set(arms) == {'benefit', 'always', 'no_proxy'}
        assert len({(r['seed'], r['node'], r['fault_ns'], r['horizon_ms']) for r in arms.values()}) == 1
        pair_groups[pair['condition']].append((pair, arms))
    for condition, members in pair_groups.items():
        caps = {float(r['horizon_ms']) - 1 for _, arms in members for r in arms.values()}
        assert len(caps) == 1
        row = dict(condition=condition, pairs=len(members), cap_ms=caps.pop(),
                   valid_pairs=sum(truth(p['valid']) for p, _ in members))
        for arm in ('no_proxy', 'always', 'benefit'):
            row[arm + '_completed'] = sum(truth(arms[arm]['completed']) for _, arms in members)
            row[arm + '_mean_capped_ms'] = mean(float(arms[arm]['capped_ms']) for _, arms in members)
        for baseline in ('always', 'no_proxy'):
            deltas = [float(p['benefit_minus_' + baseline + '_capped_ms']) for p, _ in members]
            row['benefit_minus_' + baseline + '_mean_capped_ms'] = mean(deltas)
            row['benefit_faster_than_' + baseline] = sum(d < -1e-6 for d in deltas)
            row['benefit_slower_than_' + baseline] = sum(d > 1e-6 for d in deltas)
        policy.append(row)
    healthy = [r for r in trials if r['condition'] == 'healthy' and r['arm'] == 'benefit']
    healthy_status = [load(root / 'runs' / r['name'] / 'run_status.json') for r in healthy]
    # Each source originates A/B canaries: 16 * 2 physical 10 Gb/s paths.
    # Bytes are serialized data-side bytes, excluding transport ACKs. Healthy
    # cases have no proxy probe routes, so probe_wire_bytes is only canaries.
    assert all(s['health_probe_routes'] == 0 for s in healthy_status)
    overhead = [s['probe_wire_bytes'] * 8 / (32 * 10 * s['monitor_end_ns']) * 100
                for s in healthy_status]
    mechanism = defaultdict(lambda: defaultdict(int))
    proxy_execution = defaultdict(lambda: dict(runs=0, activated_runs=0,
        rescued_chunks=0, new_proxy_completions=0, sustained_new_proxy_runs=0))
    for r in trials:
        if truth(r['valid']):
            native = load(root / 'runs' / r['name'] / 'result.json')
            execution = proxy_execution[r['condition'] + ':' + r['arm']]
            execution['runs'] += 1
            execution['activated_runs'] += bool(native['performance']['first_activations_ns'])
            execution['rescued_chunks'] += native['status']['rescued_chunks']
            execution['new_proxy_completions'] += native['performance']['new_Bprime_completions']
            execution['sustained_new_proxy_runs'] += native['performance']['sustained_new_proxy_observed']
        if r['arm'] != 'benefit':
            continue
        attempt = load(root / 'attempts' / (r['name'] + '.json'))
        for reason, count in attempt.get('score', {}).get('policy_decision_counts', {}).items():
            mechanism[r['condition']][reason] += count
    boundary_detection = [g for g in summary['groups'] if g['arm'] == 'benefit'
                          and g['condition'] not in summary['primary_conditions'] + ['healthy']]
    total_registered = summary['registered'] + (loss_summary['registered'] if loss_summary else 0)
    total_verified = summary['verified'] + (loss_summary['verified'] if loss_summary else 0)
    target_met = all(r['timely']/r['registered'] >= .95 for r in primary)
    output = dict(schema='limer-research-report-v1', plan_sha256=reg['plan_sha256'],
        frozen_aggregate_replay_checked=True,
        supplemental_plan_sha256=loss_reg['plan_sha256'] if loss_reg else None,
        binary_sha256=reg['binary_sha256'], registered=total_registered, verified=total_verified,
        main_registered=summary['registered'], main_verified=summary['verified'],
        selected_primary_empirical_target_met=target_met,
        primary_detection=primary, boundary_detection=boundary_detection, paired_policy=policy,
        healthy_false_alarm_trials=summary['healthy_false_alarm_trials'],
        healthy_trajectories='60 deterministic repetitions, not independent traffic samples',
        healthy_canary_data_wire_capacity_percent=mean(overhead),
        policy_decision_counts=dict(mechanism), proxy_execution=dict(proxy_execution))
    out.mkdir(parents=True, exist_ok=False)
    (out / 'report.json').write_text(json.dumps(output, indent=2) + '\n')
    for name, records in (('detection', primary), ('policy', policy)):
        with (out / (name + '.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    lines = [
        '# LIMER：2026-10-28 冻结仿真实验结果', '',
        f"主矩阵注册 {summary['registered']} 次、执行 {summary['attempted']} 次；" +
        (f"加上独立丢包补充后共 {total_registered} 次，" if loss_root else '') +
        f"通过执行审计与独立重放 {total_verified} 次。检测验收结论："
        + ('选定的四类队列均达到至少 95% 的试验严格 <100 ms。' if target_met else '本轮未建立全部主条件达标。'), '',
        '## 检测：一次试验要把受影响路径都找对', '',
        '每行 60 个 held-out 故障 trial；表中延迟取同次试验所有受影响方向的最慢报警，'
        '从注入到控制器实际收到报警。提前报、报错路径、漏报及错误都不能计入及时成功。', '',
        '| 条件 | 来源 | <100 ms / 注册数 | 分类计数 | p95 ms | 最大值 ms | 单侧 95% 成功率下界 |',
        '| --- | --- | ---: | --- | ---: | ---: | ---: |',
    ]
    for r in primary:
        counts = ', '.join(f'{k}={v}' for k, v in r['classifications'].items())
        lower = f"{100*r['exact_one_sided_95_lower']:.2f}%" if r['exact_one_sided_95_lower'] is not None else '不解释：随机流复用'
        lines.append(f"| {LABELS[r['condition']][1]} | {r['campaign']} | {r['timely']}/{r['registered']} | {counts} | {fmt(r['p95_ms'])} | {fmt(r['max_ms'])} | {lower} |")
    original_loss = [r for r in trials if r['condition'] == 'weak_loss' and r['arm'] == 'benefit']
    original_unique = len({int(r['seed'])+int(r['node']) for r in original_loss})
    lines += ['', f'主矩阵的弱丢包原队列包含 {original_unique} 个不同的派生随机流对（注册 {len(original_loss)} 次），'
        f"及时成功 {sum(truth(r['all_paths_timely']) for r in original_loss)}/{len(original_loss)}。"
        '原注入器使用 seed+node，故相邻 seed 可能复用丢包序列，不能把名义二项式下界当作独立抽样证据。']
    if loss_root:
        lines += [f'弱丢包检测行改由提前注册的 {loss_root.name} 提供：60 个不复用序列的新 trial，'
            '原生代码、检测参数和核心审计器均保持相同。不把两队列池化提高通过率。'
            '其余三行及后面的策略配对仍来自主矩阵；策略表仅解释注册配对的经验差值。']
    lines += ['', '下界按条件单独计算，未做多条件同时保证的校正。不能据此宣称任意灰故障都可检测。', '',
        '以下边界也保留检测成绩，单独展示，不用于扩大四类主条件的通过率：', '',
        '| 边界 | <100 ms / 注册数 | 分类计数 | 全分母 p95 ms |',
        '| --- | ---: | --- | ---: |']
    for g in boundary_detection:
        counts = ', '.join(f'{k}={v}' for k,v in g['classifications'].items())
        lines.append(f"| {LABELS[g['condition']][1]} | {g['timely_trials']}/{g['registered']} | {counts} | {fmt(g['p95_all_trials_ms'])} |")
    lines += ['',
        f"健康对照误报 {summary['healthy_false_alarm_trials']}/{len(healthy)}；它们是同一确定性健康轨迹的重复，不能当成 60 类业务覆盖。"
        f"Canary 数据侧实际线上负载占 32 个发送端 NIC/平面出口总容量的平均值约 {mean(overhead):.2f}%；"
        '每出口 10 Gb/s，不能泛化成任意 fabric 链路占用。'
        '此值含数据头，不含 transport ACK，控制消息另计。监测持续到观察上限，业务提前结束也不停止。', '',
        '## 换路：同一输入下比较三种策略', '',
        '无代理是 G10 自适应分流；直接换路是 G11 在告警、代理资格和计费探测通过后就协调换路；'
        '收益门控是 G11 再比较预计留下和换路的完成代价。两种 G11 使用相同 64 KiB 三段探测和 96 B 健康报告。'
        '这些是内部机制消融，不是与 OptCC、VCCL 等外部系统的完整头对头复现。', '',
        '下表只用完整注册配对，主条件各 20 对，边界各 10 对。时间从业务启动的 1 ms 算起；'
        '未完成或错误按观察上限计入截尾成本，因此不是精确完成时间，也不能直接换算加速比。', '',
        '| 条件 | 有效 / 注册配对 | 截尾上限 ms | 完成数：无代理 / 直接换 / 收益门控 | 平均截尾成本 ms：无代理 / 直接换 / 收益门控 | 门控 − 直接换 ms |',
        '| --- | ---: | ---: | --- | --- | ---: |',
    ]
    for r in policy:
        completes = ' / '.join(str(r[a+'_completed']) for a in ('no_proxy', 'always', 'benefit'))
        times = ' / '.join(fmt(r[a+'_mean_capped_ms']) for a in ('no_proxy', 'always', 'benefit'))
        lines.append(f"| {LABELS[r['condition']][1]} | {r['valid_pairs']}/{r['pairs']} | {r['cap_ms']:.0f} | {completes} | {times} | {r['benefit_minus_always_mean_capped_ms']:+.2f} |")
    lines += ['', '在全部配对有效时，负差值表示门控的截尾成本更低，正值表示更高。'
        '若存在无效配对，惩罚值仍留在表中，但不能把差值当成可靠的性能效果。门控使用近 10 ms ACK 服务、剩余工作、'
        '三段候选路线实测、控制排队、协调和最终确认，预计收益须超过 max(1 ms, 10% 留下代价)。'
        '它不知道未来故障何时结束，也不保证每种场景都赢。无空闲代理时，及时检测不等于能够恢复。', '',
        '## 如何达到快速检测', '',
        '同物理路径每 2 ms 发 64 KiB canary；先用健康的前 20 ms 冻结服务参考。'
        '40 ms 窗口内有三个异常 canary，且发送跨度至少 4 ms，就可报警。'
        '异常来自真实超时或重传；真实业务 ACK 40 ms 无进展提供另一条信号。'
        'v4 还汇总同路径所有业务和探测包的接收间隔：前 20 ms 校准 P10，'
        '之后连续两个 10 ms 窗口（每窗至少 64 个间隔）的 P10 超过 2×基线+100 ns 就报警。'
        '这使持续异常通常不用等 100 ms 才积累证据，报警仍支付实际控制消息运输时间。', '',
        '## 正确性、证据和边界', '',
        '执行审计检查物理双平面、NIC/代理 credits、ACK 前缀、epoch、三段到达及最终确认；'
        f'独立重放从实际 QP、重传、ACK、接收包间隔和控制 FIFO 重建检测和决策。全量归档完整性结果见 [主矩阵核验](integrity-{root.name}.json)。'
        + (f'独立丢包补充另见 [补充队列核验](integrity-{loss_root.name}.json)。' if loss_root else ''), '',
        '该模拟器不执行张量数值、CUDA、HBM 或计算重叠；当前结论限定在 16-GPU 拓扑、'
        '正常启动校准和注册的故障/业务分布。收益估计是 sender/phase 层近似，未实现全局 DAG 最优选择。'
        '代理发现仍依赖阶段状态；启动即退化、代理二次故障、恢复旧 B 和任意拥塞背景尚未验收。', '',
        '一次迁移完成不等于后续 B′持续承担新业务；需同时查看 performance.json 的 '
        'new_Bprime_completions/sustained_new_proxy_observed，不能把在途抢救描述成恢复健康双平面吞吐。', '',
        f"冻结计划 SHA-256：`{reg['plan_sha256']}`。", '',
        f"原生二进制 SHA-256：`{reg['binary_sha256']}`。", '',
        '开发失败与正式验证分开保存。全量原始数据留在 otakotak；本地导出仅做紧凑证据核验。', '',
    ]
    primary_proxy = [proxy_execution[c + ':benefit'] for c in summary['primary_conditions']]
    lines += [f"主矩阵四类主条件的收益门控共 {sum(r['runs'] for r in primary_proxy)} 次："
        f"{sum(r['activated_runs'] for r in primary_proxy)} 次实际激活代理，"
        f"{sum(r['rescued_chunks'] for r in primary_proxy)} 个在途 chunk 发起抢救，"
        f"{sum(r['new_proxy_completions'] for r in primary_proxy)} 个新分配 B′ chunk 完成，"
        f"{sum(r['sustained_new_proxy_runs'] for r in primary_proxy)} 次满足至少两个 phase 有新 B′完成。"
        '各条件/方法的细分与决策原因计数在 report.json；原因计数是评估次数，不等于实际切换次数。', '']
    if plots:
        detection_trials = [r for r in trials if not (loss_root and r['condition'] == 'weak_loss')] + loss_trials
        render_plots(primary, policy, detection_trials, out)
        lines += ['## 图', '', '![Detection CDF](detection_cdf.png)', '',
                  '![Paired policy comparison](policy_comparison.png)', '']
    (out / 'README.md').write_text('\n'.join(lines))
    return output


def render_plots(primary, policy, trials, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'savefig.dpi': 180, 'pdf.fonttype': 42})
    fig, ax = plt.subplots(figsize=(7.4, 4.4), layout='constrained')
    for group in primary:
        rows = [r for r in trials if r['condition'] == group['condition'] and r['arm'] == 'benefit']
        finite = sorted(number(r['all_paths_delay_ms']) for r in rows
                        if truth(r['valid']) and number(r['all_paths_delay_ms']) is not None)
        xs, ys = [0], [0]
        visible = [x for x in finite if x <= 105]
        for i, x in enumerate(visible, 1):
            xs += [x, x]; ys += [(i-1)/len(rows), i/len(rows)]
        xs.append(105); ys.append(len(visible)/len(rows))
        ax.plot(xs, ys, label=f"{LABELS[group['condition']][0]} (n={len(rows)})")
    ax.axvline(100, color='#aa3333', linestyle='--', linewidth=1)
    ax.axhline(.95, color='#777777', linestyle=':', linewidth=1)
    ax.set(xlabel='Slowest affected-path alarm delay per trial (ms)', ylabel='Fraction of all registered trials',
           xlim=(0, 105), ylim=(0, 1.03), title='Detection: all affected paths, controller arrival time')
    ax.legend(loc='lower right', frameon=False, fontsize=9)
    ax.grid(alpha=.15)
    for ext in ('png', 'pdf'):
        fig.savefig(out / ('detection_cdf.' + ext))
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9.4, 5.8), layout='constrained')
    arms = ('no_proxy', 'always', 'benefit')
    colors = ('#a5a5a5', '#527cba', '#139b8e')
    for j, (arm, color) in enumerate(zip(arms, colors)):
        y = [i + (j-1)*.23 for i in range(len(policy))]
        bars = ax.barh(y, [r[arm+'_mean_capped_ms'] for r in policy], height=.22,
                      color=color, label={'no_proxy':'G10: no proxy', 'always':'G11: always replace', 'benefit':'G11: benefit gate'}[arm])
        for bar, r in zip(bars, policy):
            ax.text(bar.get_width()+3, bar.get_y()+bar.get_height()/2,
                    f"{r[arm+'_completed']}/{r['pairs']}", va='center', fontsize=8)
    ax.set_yticks(range(len(policy)), [LABELS[r['condition']][0] for r in policy])
    ax.invert_yaxis()
    ax.set(xlabel='Mean capped communication cost (ms); labels = completed / paired trials',
           title='Matched inputs: switching can help or hurt')
    ax.set_xlim(0, max(r[a+'_mean_capped_ms'] for r in policy for a in arms)*1.16)
    ax.legend(loc='lower right', frameon=False, fontsize=8)
    ax.grid(axis='x', alpha=.15)
    fig.supxlabel('Observation cap: 399 ms; slow helper + B at 25%: 799 ms. Censored costs are not exact completion times.', fontsize=8)
    for ext in ('png', 'pdf'):
        fig.savefig(out / ('policy_comparison.' + ext))
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plots', action='store_true')
    parser.add_argument('--independent-loss-campaign', type=Path)
    args = parser.parse_args()
    result = report(args.campaign, args.out, args.plots, args.independent_loss_campaign)
    print(json.dumps({k: result[k] for k in ('registered', 'verified', 'plan_sha256')}))
