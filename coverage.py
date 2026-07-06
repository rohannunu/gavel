#!/usr/bin/env python3
"""
Judge pool coverage analysis.

Shows which pools have unseen projects and how many judges are needed
to achieve full coverage within a 2-hour window.

Usage:
    python coverage.py              # analyze existing simulation data
    python coverage.py --time 120   # run a fresh 2-hour sim first, then analyze
"""

import sys
import math
import argparse

sys.path.insert(0, '.')

from gavel import app
from gavel.models import db, Annotator, Item, Decision
from gavel.controllers.judge import PRIZE_PREFERENCE_FIELDS

POOLS = [
    ('general',      'General Path',          lambda: Item.query.filter_by(active=True, path='general').all()),
    ('pro',          'Pro Path',               lambda: Item.query.filter_by(active=True, path='pro').all()),
    ('ui_ux',        'Best UI/UX Design',      lambda: Item.query.filter_by(active=True, prize_ui_ux=True).all()),
    ('social_impact','Best Social Impact',     lambda: Item.query.filter_by(active=True, prize_social_impact=True).all()),
    ('creative',     'Most Creative',          lambda: Item.query.filter_by(active=True, prize_creative=True).all()),
    ('useless',      'Most Useless',           lambda: Item.query.filter_by(active=True, prize_useless=True).all()),
]


def projects_per_judge(time_budget, demo_min, demo_max, walk_min, walk_max):
    avg_demo = (demo_min + demo_max) / 2
    avg_walk = (walk_min + walk_max) / 2
    return int(time_budget / (avg_demo + avg_walk))


def comparison_count(item):
    return (Decision.query.filter_by(winner_id=item.id).count() +
            Decision.query.filter_by(loser_id=item.id).count())


def pool_summary(time_budget=120, demo_min=3.0, demo_max=5.0, walk_min=2.0, walk_max=3.0):
    ppj = projects_per_judge(time_budget, demo_min, demo_max, walk_min, walk_max)
    with app.app_context():
        print('=== Pool Summary (no simulation needed) ===')
        print(f'    Window: {time_budget} min | Demo: {demo_min}-{demo_max} min | '
              f'Walk: {walk_min}-{walk_max} min | ~{ppj} projects/judge')
        print()
        print(f'  {"Pool":<22} {"Judges":>7} {"Projects":>9} {"Slots":>7} {"Factor":>8}')
        print('  ' + '-' * 58)
        for key, label, get_items in POOLS:
            items = get_items()
            if not items:
                continue
            judges = Annotator.query.filter_by(active=True, path_preference=key).count()
            slots = judges * ppj
            factor = slots / len(items)
            flag = '  <-- thin' if factor < 2.0 else ''
            print(f'  {label:<22} {judges:>7} {len(items):>9} {slots:>7} {factor:>7.1f}x{flag}')
        print()
        print(f'  Factor = (judges × {ppj} projects/judge) / projects. Aim for 2x+.')


def analyze(time_budget=120, demo_min=3.0, demo_max=5.0, walk_min=2.0, walk_max=3.0):
    ppj = projects_per_judge(time_budget, demo_min, demo_max, walk_min, walk_max)

    with app.app_context():
        total_decisions = Decision.query.count()
        if total_decisions == 0:
            print('No simulation data found. Run simulate.py first, or pass --time to run one now.')
            return

        print(f'=== Pool Coverage Report ({total_decisions:,} total decisions) ===')
        print(f'    Window: {time_budget} min | Demo: {demo_min}-{demo_max} min | '
              f'Walk: {walk_min}-{walk_max} min | ~{ppj} projects/judge')
        print()
        print(f'  {"Pool":<22} {"Judges":>6} {"Projects":>9} {"Unseen":>7} {"Need":>5} {"Gap":>5}  {"Status"}')
        print('  ' + '-' * 72)

        any_gap = False
        unseen_by_pool = {}
        pool_stats = []

        for key, label, get_items in POOLS:
            items = get_items()
            if not items:
                continue

            judges = Annotator.query.filter_by(active=True, path_preference=key).count()
            unseen_items = [item for item in items if comparison_count(item) == 0]
            n_unseen = len(unseen_items)
            judges_needed = math.ceil(len(items) / ppj)
            gap = max(0, judges_needed - judges)
            status = 'OK' if gap == 0 and n_unseen == 0 else ('ADD JUDGES' if gap > 0 else 'thin')

            unseen_by_pool[key] = unseen_items
            pool_stats.append((key, label, judges, len(items), n_unseen, judges_needed, gap, status))
            if gap > 0 or n_unseen > 0:
                any_gap = True

            print(f'  {label:<22} {judges:>6} {len(items):>9} {n_unseen:>7} {judges_needed:>5} {gap:>5}  {status}')

        print()
        print(f'  Columns: Judges=assigned, Need=ceil(projects/{ppj}), Gap=judges to add')
        print(f'  thin = enough judges by formula but randomness left some projects unseen')
        print()

        # Recommendations: target 2x coverage factor to account for randomness
        recs = []
        for key, label, judges, n_items, n_unseen, judges_needed, gap, status in pool_stats:
            comfortable = math.ceil(n_items * 2.0 / ppj)
            add = max(0, comfortable - judges)
            if add == 0:
                continue
            coverage_now = round(judges * ppj / n_items, 1)
            reason = f'required' if gap > 0 else f'2x coverage (currently {coverage_now}x)'
            recs.append((label, add, judges, judges + add, reason))

        if recs:
            print('  === Recommended judge additions (targeting 2x coverage) ===')
            for label, add, current, target, reason in recs:
                print(f'  {label:<22}  add {add}  ({current} → {target}, {reason})')
            print(f'  Total to add: {sum(r[1] for r in recs)}')
            print()

        # Unseen project details
        for key, label, _ in POOLS:
            unseen = unseen_by_pool.get(key, [])
            if unseen:
                print(f'  Unseen in {label}:')
                for item in unseen:
                    prizes = [p for p in PRIZE_PREFERENCE_FIELDS if getattr(item, f'prize_{p}')]
                    extra = f'  (also: {", ".join(prizes)})' if prizes and key not in prizes else ''
                    print(f'    - {item.name}{extra}')
                print()

        if not any_gap:
            print('  All pools adequately covered.')


def run_sim_then_analyze(time_budget, demo_min, demo_max, walk_min, walk_max):
    import simulate as sim
    with app.app_context():
        sim._do_reset()
    print(f'Running fresh {time_budget}-min simulation...')
    print()
    with app.app_context():
        sim._sim_one(time_budget, demo_min, demo_max, walk_min, walk_max)
    analyze(time_budget, demo_min, demo_max, walk_min, walk_max)


def run_what_if(time_budget=120, demo_min=3.0, demo_max=5.0, walk_min=2.0, walk_max=3.0):
    """Temporarily add recommended judges, simulate, report, then clean up."""
    import simulate as sim

    ppj = projects_per_judge(time_budget, demo_min, demo_max, walk_min, walk_max)
    SIM_PREFIX = '__sim__'

    with app.app_context():
        additions = []
        for key, label, get_items in POOLS:
            items = get_items()
            if not items:
                continue
            judges = Annotator.query.filter_by(active=True, path_preference=key).count()
            judges_needed = math.ceil(len(items) * 2.0 / ppj)
            gap = max(0, judges_needed - judges)
            additions.append((key, label, gap))

        if not any(g > 0 for _, _, g in additions):
            print('All pools already at or above recommended staffing. Nothing to add.')
            return

        print(f'=== What-if simulation: adding recommended judges ===')
        print(f'Window: {time_budget} min | Demo: {demo_min}-{demo_max} | Walk: {walk_min}-{walk_max} | ~{ppj} projects/judge')
        print()

        added_ids = []
        if any(g > 0 for _, _, g in additions):
            print('  Adding synthetic judges:')
            for key, label, gap in additions:
                for i in range(gap):
                    ann = Annotator(
                        name=f'{SIM_PREFIX}{key}_{i+1}',
                        email=f'{SIM_PREFIX}{key}_{i+1}@sim.local',
                        description='synthetic judge for what-if simulation',
                        path_preference=key,
                    )
                    db.session.add(ann)
                    db.session.flush()
                    added_ids.append(ann.id)
                print(f'    {label:<22}  +{gap}')
            db.session.commit()
            print()

        sim._do_reset()
        print(f'Running simulation...')
        print()
        sim._sim_one(time_budget, demo_min, demo_max, walk_min, walk_max)

    analyze(time_budget, demo_min, demo_max, walk_min, walk_max)

    with app.app_context():
        sim._do_reset()
        if added_ids:
            from sqlalchemy import text
            id_list = ','.join(str(i) for i in added_ids)
            db.session.execute(text(f'DELETE FROM view WHERE annotator_id IN ({id_list})'))
            db.session.execute(text(f'DELETE FROM ignore WHERE annotator_id IN ({id_list})'))
            db.session.execute(text(f'DELETE FROM decision WHERE annotator_id IN ({id_list})'))
            db.session.execute(text(f'UPDATE annotator SET next_id=NULL, prev_id=NULL WHERE id IN ({id_list})'))
            db.session.execute(text(f'DELETE FROM annotator WHERE id IN ({id_list})'))
            db.session.commit()
            print('Synthetic judges removed. Simulation data cleared.')
        else:
            print('Simulation data cleared.')


def run_guarantee(time_budget=120, n_trials=10, demo_min=3.0, demo_max=5.0, walk_min=2.0, walk_max=3.0):
    """Find the minimum judge count per pool so 0 projects go unseen in every one of n_trials runs."""
    import simulate as sim

    ppj = projects_per_judge(time_budget, demo_min, demo_max, walk_min, walk_max)
    SIM_PREFIX = '__sim__'
    MAX_ITER = 20

    with app.app_context():
        pool_info = []
        for key, label, get_items in POOLS:
            items = get_items()
            if not items:
                continue
            current = Annotator.query.filter_by(active=True, path_preference=key).count()
            needed = math.ceil(len(items) / ppj)
            extra = max(0, needed - current)
            pool_info.append({
                'key': key, 'label': label, 'get_items': get_items,
                'n_items': len(items), 'current': current, 'extra': extra,
            })

        print(f'=== Guarantee mode: finding judge counts for 0 unseen in all {n_trials} runs ===')
        print(f'Window: {time_budget} min | Demo: {demo_min}-{demo_max} | Walk: {walk_min}-{walk_max} | ~{ppj} projects/judge')
        print()

        converged = False
        for iteration in range(MAX_ITER):
            # Insert synthetic judges for this round
            added_ids = []
            for info in pool_info:
                for i in range(info['extra']):
                    ann = Annotator(
                        name=f'{SIM_PREFIX}{info["key"]}_{i+1}',
                        email=f'{SIM_PREFIX}{info["key"]}_{i+1}@sim.local',
                        description='synthetic',
                        path_preference=info['key'],
                    )
                    db.session.add(ann)
                    db.session.flush()
                    added_ids.append(ann.id)
            db.session.commit()

            # Run n_trials, count how many trials each pool had unseen
            fail_counts = {info['key']: 0 for info in pool_info}
            for _ in range(n_trials):
                sim._do_reset()
                sim._sim_one(time_budget, demo_min, demo_max, walk_min, walk_max)
                for info in pool_info:
                    items = info['get_items']()
                    if any(comparison_count(item) == 0 for item in items):
                        fail_counts[info['key']] += 1

            # Clean up synthetic judges before next round
            sim._do_reset()
            if added_ids:
                from sqlalchemy import text
                id_list = ','.join(str(i) for i in added_ids)
                db.session.execute(text(f'DELETE FROM view WHERE annotator_id IN ({id_list})'))
                db.session.execute(text(f'DELETE FROM ignore WHERE annotator_id IN ({id_list})'))
                db.session.execute(text(f'DELETE FROM decision WHERE annotator_id IN ({id_list})'))
                db.session.execute(text(f'UPDATE annotator SET next_id=NULL, prev_id=NULL WHERE id IN ({id_list})'))
                db.session.execute(text(f'DELETE FROM annotator WHERE id IN ({id_list})'))
                db.session.commit()

            total_extra = sum(info['extra'] for info in pool_info)
            failed = [info for info in pool_info if fail_counts[info['key']] > 0]
            fail_summary = ', '.join(
                f'{info["label"]} ({fail_counts[info["key"]]}/{n_trials})'
                for info in failed
            )
            print(f'  Round {iteration+1} (+{total_extra} judges): {len(failed)} pools still had gaps'
                  + (f' — {fail_summary}' if failed else ''))

            if not failed:
                converged = True
                break

            # Add one more judge to each pool that failed in any trial
            for info in pool_info:
                fc = fail_counts[info['key']]
                if fc > 0:
                    fail_rate = fc / n_trials
                    info['extra'] += max(1, round(fail_rate * 4))

        print()
        if not converged:
            print(f'Did not converge in {MAX_ITER} rounds. Try --trials with a lower value or increase --time.')
            return

        print(f'Judge counts that guarantee full coverage ({n_trials}/{n_trials} runs pass):')
        print()
        print(f'  {"Pool":<22} {"Current":>8} {"Add":>5} {"Final":>7}')
        print('  ' + '-' * 46)
        total_add = 0
        for info in pool_info:
            add_str = f'+{info["extra"]}' if info['extra'] > 0 else '—'
            print(f'  {info["label"]:<22} {info["current"]:>8} {add_str:>5} {info["current"] + info["extra"]:>7}')
            total_add += info['extra']
        print()
        print(f'  Total to add: {total_add}')
        print(f'  (0 unseen verified across {n_trials} independent simulation runs)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Judge pool coverage analysis')
    parser.add_argument('--time', type=float, default=None,
                        help='Run a fresh simulation with this time budget (minutes) before analyzing')
    parser.add_argument('--what-if', action='store_true',
                        help='Temporarily add recommended judges, simulate, and show if all pools reach OK')
    parser.add_argument('--guarantee', action='store_true',
                        help='Find the minimum judge count per pool for 0 unseen in every simulation run')
    parser.add_argument('--pools', action='store_true',
                        help='Show judge/project counts and coverage factor per pool (no simulation needed)')
    parser.add_argument('--trials', type=int, default=10,
                        help='Number of simulation runs for --guarantee mode (default: 10)')
    parser.add_argument('--demo-min', type=float, default=3.0)
    parser.add_argument('--demo-max', type=float, default=5.0)
    parser.add_argument('--walk-min', type=float, default=2.0)
    parser.add_argument('--walk-max', type=float, default=3.0)
    args = parser.parse_args()

    if args.pools:
        pool_summary(
            time_budget=args.time or 120,
            demo_min=args.demo_min, demo_max=args.demo_max,
            walk_min=args.walk_min, walk_max=args.walk_max,
        )
    elif args.guarantee:
        run_guarantee(
            time_budget=args.time or 120,
            n_trials=args.trials,
            demo_min=args.demo_min, demo_max=args.demo_max,
            walk_min=args.walk_min, walk_max=args.walk_max,
        )
    elif args.what_if:
        run_what_if(
            time_budget=args.time or 120,
            demo_min=args.demo_min, demo_max=args.demo_max,
            walk_min=args.walk_min, walk_max=args.walk_max,
        )
    elif args.time:
        run_sim_then_analyze(args.time, args.demo_min, args.demo_max, args.walk_min, args.walk_max)
    else:
        analyze(demo_min=args.demo_min, demo_max=args.demo_max,
                walk_min=args.walk_min, walk_max=args.walk_max)
