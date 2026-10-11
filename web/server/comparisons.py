"""Read and regenerate six saved image comparisons."""
from consolidate_reports import ROOT, LOCK, read_json, consolidate
from compare_environments import analyze, options, agreement, agreement_files, PAIR_IDS, SOURCES
from comparison_summaries import accuracy, summary_files, FILES


class Comparisons:
    def __init__(self, root=ROOT):
        self.root = root
        self.cached = None
        self.signature = None

    def query(self, args):
        with LOCK:
            path = self.root / 'analysis/comparisons/report.json'
            if not path.exists():
                source = self.root / 'analysis/consolidated.json'
                data = read_json(source) if source.exists() else None
                return dict(exists=False, options=options(data, 'drowsiness') if data else {}, selected={})
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature != self.signature:
                self.cached = read_json(path)
                for saved_pair in self.cached['pairs']:
                    saved_pair.update(agreement(saved_pair))
                self.cached['accuracy'] = accuracy(self.cached)
                self.signature = signature
            data = self.cached
            requested = args.get('pair', [PAIR_IDS[0]])[0]
            pair = next((p for p in data['pairs'] if p['id'] == requested), None)
            if pair is None:
                raise ValueError('Unknown comparison')
            items = pair['images']
            search = args.get('search', [''])[0].casefold()
            status = args.get('status', [''])[0]
            if search:
                items = [i for i in items if search in i['name_image'].casefold()]
            if status:
                items = [i for i in items if i['status'] == status]
            if args.get('class_changed') == ['1']:
                items = [i for i in items if i['class_changed'] is True]
            if args.get('sort') == ['maximum']:
                items = sorted(items, key=lambda i: (-(i['quantized']['maximum'] or 0), i['name_image']))
            pages = max(1, (len(items)+24)//25)
            page = max(1, min(pages, int(args.get('page', ['1'])[0])))
            source = self.root / data['source']
            stale = not source.exists() or source.stat().st_mtime_ns != data['source_mtime_ns']
            return dict(exists=True, generated_at=data['generated_at'], model=data['model'],
                selected=data['selected'], options=data['options'], stale=stale,
                accuracy=data['accuracy'],
                pairs=[{key: value for key, value in p.items() if key != 'images'} for p in data['pairs']],
                pair=pair['id'], images=items[(page-1)*25:page*25], matched=len(items), page=page, pages=pages)

    def rebuild(self, selections=None):
        if selections is not None and (not isinstance(selections, dict) or set(selections) - set(SOURCES)):
            raise ValueError('Invalid execution selection')
        with LOCK:
            consolidate(self.root)
            analyze(self.root, selections=selections)
            return self.query({})

    def download(self, filename):
        if filename not in ['report.json', 'images.csv', 'summary.csv', 'agreement.csv', 'agreement.md'] + list(FILES) + [p+'.csv' for p in PAIR_IDS]:
            raise ValueError('Unknown comparison report')
        with LOCK:
            if filename in FILES:
                return summary_files(read_json(self.root / 'analysis/comparisons/report.json'))[filename]
            if filename in ('agreement.csv', 'agreement.md'):
                # Derive the download from the same saved data shown on screen,
                # including reports generated before agreement was introduced.
                report = read_json(self.root / 'analysis/comparisons/report.json')
                return agreement_files(report)[filename]
            return (self.root / 'analysis/comparisons' / filename).read_bytes()
