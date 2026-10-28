"""M13 causal class-separated observations; injector state is never accepted."""
from limer_v0.hybrid_delivery import HybridDeliveryDetector
from limer_v0.early_delivery import EarlyDeliveryDetector


class BusinessDeliveryDetector:
    RULE_VERSION = 'business-delivery-v1'
    GAP_GUARD_NS = 40_000_000
    FIELDS = HybridDeliveryDetector.FIELDS | {
        'data_count','probe_count','data_gaps','probe_gaps',
        'data_gap_age_ns','probe_gap_age_ns'}

    def __init__(self):
        self.baseline=HybridDeliveryDetector()
        self.business=EarlyDeliveryDetector()
        self.alarmed=set()
        self.seen={}

    def advance(self, now_ns):
        expired=self.baseline.advance(now_ns)+self.business.advance(now_ns)
        for key in list(self.seen):
            if now_ns>(key[1]+1)*10_000_000+200_000_000: del self.seen[key]
        return expired

    def _emit(self, row, signal, missing, batches, age=0):
        if row['path'] in self.alarmed: return None
        self.alarmed.add(row['path'])
        return dict(rule_version=self.RULE_VERSION,path=row['path'],
                    decision_t_ns=row['arrival_t_ns'],signal=signal,
                    missing_packets=missing,evidence_batches=batches,gap_age_ns=age,
                    claim='Observed delivery impairment; cause unresolved')

    def observe(self, report):
        if set(report)!=self.FIELDS: raise ValueError('only class-separated observed report fields allowed')
        for key in self.FIELDS-{'path','side'}:
            if type(report[key]) is not int or report[key]<0:
                raise ValueError('report numbers must be nonnegative integers')
        if report['count']!=report['data_count']+report['probe_count']:
            raise ValueError('class counters must conserve total count')
        for kind in ('data','probe'):
            n,age=report[kind+'_gaps'],report[kind+'_gap_age_ns']
            if (not n and age) or age>report['sample_t_ns'] or (report['side']=='tx' and (n or age)):
                raise ValueError('invalid receiver-only gap observation')
        projected={k:report[k] for k in HybridDeliveryDetector.FIELDS}
        old=self.baseline.observe(projected)
        self.advance(report['arrival_t_ns'])
        if report['arrival_t_ns']>(report['batch']+1)*10_000_000+200_000_000: return None
        key=(report['path'],report['batch'],report['side'],report['guard_ns'])
        content={k:v for k,v in report.items() if k!='arrival_t_ns'}
        if key in self.seen:
            if self.seen[key]!=content: raise ValueError('conflicting class-report duplicate')
            return None
        self.seen[key]=content
        emitted=None
        if old:
            emitted=self._emit(report,'global_early' if old['rule_version']=='hybrid-early-v4'
                               else 'global_mature',old['missing_packets'],old['evidence_batches'])
        if report['side']=='rx':
            for kind in ('data','probe'):
                if report[kind+'_gaps'] and report[kind+'_gap_age_ns']>=self.GAP_GUARD_NS:
                    candidate=self._emit(report,kind+'_gap',report[kind+'_gaps'],
                                         [report['batch']],report[kind+'_gap_age_ns'])
                    if candidate: emitted=candidate
        if report['guard_ns']==10_000_000:
            business={k:report[k] for k in EarlyDeliveryDetector.FIELDS}
            business['count']=report['data_count']
            early=self.business.observe(business)
            if early:
                candidate=self._emit(report,'data_service',early['missing_packets'],early['evidence_batches'])
                if candidate: emitted=candidate
        return emitted
