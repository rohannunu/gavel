#!/usr/bin/env python3
"""
Gavel judging simulation.

Drives synthetic votes for all active annotators using existing DB data.
Vote outcomes use a Bradley-Terry weighted coin flip based on current mu values.

Usage:
    python simulate.py                    # 2-hour window, 3-5 min demos, 2-3 min walks
    python simulate.py --time 90          # 90-minute window
    python simulate.py --no-time-limit    # run every judge to full exhaustion
    python simulate.py --reset            # undo all simulation data and restore priors
"""

import sys
import math
import argparse

sys.path.insert(0, '.')

from numpy.random import choice, random, uniform

from gavel import app
from gavel.models import db, Annotator, Item, Decision, ignore_table, view_table
import gavel.crowd_bt as crowd_bt
from gavel.controllers.judge import preferred_items, choose_next, perform_vote


def simulate_winner(item_a, item_b):
    """Bradley-Terry weighted coin flip. Equal mu → 50/50."""
    p = 1.0 / (1.0 + math.exp(-(item_a.mu - item_b.mu)))
    return item_a if random() < p else item_b


def run_simulation(time_budget=120, demo_min=3, demo_max=5, walk_min=2, walk_max=3):
    with app.app_context():
        annotators = Annotator.query.filter_by(active=True).all()
        all_items = Item.query.filter_by(active=True).all()
        timed = time_budget is not None
        print(f'Running simulation for {len(annotators)} judges across {len(all_items)} projects...')
        if timed:
            print(f'Time budget: {time_budget} min | Demo: {demo_min}-{demo_max} min | Walk: {walk_min}-{walk_max} min')
        else:
            print('No time limit — running each judge to full exhaustion.')
        print()

        total_votes = 0

        for annotator in annotators:
            pool = preferred_items(annotator)
            if not pool:
                print(f'  [skip] {annotator.name} ({annotator.path_preference or "any"}): no eligible projects')
                continue

            elapsed = 0.0

            # First project costs only demo time (no walk needed)
            elapsed += uniform(demo_min, demo_max) if timed else 0.0
            if timed and elapsed >= time_budget:
                print(f'  [skip] {annotator.name}: out of time before first vote')
                continue

            # Pick first item (mirrors maybe_init_annotator)
            annotator.update_next(choice(pool))

            # View first item without a comparison (mirrors the "begin" page)
            annotator.ignore.append(annotator.next)
            annotator.next.viewed.append(annotator)
            annotator.prev = annotator.next
            annotator.update_next(choose_next(annotator))

            votes = 0
            while annotator.next is not None:
                if timed:
                    cost = uniform(walk_min, walk_max) + uniform(demo_min, demo_max)
                    if elapsed + cost > time_budget:
                        break
                    elapsed += cost

                winner = simulate_winner(annotator.prev, annotator.next)
                next_won = (winner == annotator.next)
                perform_vote(annotator, next_won=next_won)
                loser = annotator.prev if next_won else annotator.next
                db.session.add(Decision(annotator, winner=winner, loser=loser))
                annotator.next.viewed.append(annotator)
                annotator.prev = annotator.next
                annotator.ignore.append(annotator.prev)
                annotator.update_next(choose_next(annotator))
                votes += 1

            db.session.commit()
            total_votes += votes
            time_str = f'  ({elapsed:.0f}/{time_budget} min)' if timed else ''
            print(f'  [sim] {annotator.name} ({annotator.path_preference or "any"}): {votes} votes{time_str}')

        print()
        print_rankings()
        print(f'Done. {total_votes:,} decisions recorded. Run with --reset to undo.')


def print_rankings():
    CATEGORIES = [
        ('General Path',       lambda q: q.filter(Item.path == 'general')),
        ('Pro Path (HackVoyagers)', lambda q: q.filter(Item.path == 'pro')),
        ('Best UI/UX Design',  lambda q: q.filter(Item.prize_ui_ux == True)),
        ('Best Social Impact', lambda q: q.filter(Item.prize_social_impact == True)),
        ('Most Creative',      lambda q: q.filter(Item.prize_creative == True)),
        ('Most Useless',       lambda q: q.filter(Item.prize_useless == True)),
    ]
    for label, filt in CATEGORIES:
        ranked = filt(Item.query.filter_by(active=True)).order_by(Item.mu.desc()).limit(10).all()
        if not ranked:
            continue
        print(f'=== {label} (Top 10) ===')
        for i, item in enumerate(ranked, 1):
            print(f'  {i:2}. {item.name[:52]:<52}  mu={item.mu:+.4f}')
        print()


def run_reset():
    with app.app_context():
        n_decisions = Decision.query.count()
        Decision.query.delete()
        db.session.execute(view_table.delete())
        db.session.execute(ignore_table.delete())
        for item in Item.query.all():
            item.mu = crowd_bt.MU_PRIOR
            item.sigma_sq = crowd_bt.SIGMA_SQ_PRIOR
        for ann in Annotator.query.all():
            ann.alpha = crowd_bt.ALPHA_PRIOR
            ann.beta = crowd_bt.BETA_PRIOR
            ann.next = None
            ann.prev = None
        db.session.commit()
        print(f'Reset complete. Deleted {n_decisions} decisions. All mu/sigma_sq/alpha/beta restored to priors.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Gavel judging simulation')
    parser.add_argument('--reset', action='store_true',
                        help='Delete all decisions and restore all scores to priors')
    parser.add_argument('--time', type=float, default=120,
                        help='Judging window in minutes (default: 120)')
    parser.add_argument('--demo-min', type=float, default=3.0,
                        help='Min demo time per project in minutes (default: 3)')
    parser.add_argument('--demo-max', type=float, default=5.0,
                        help='Max demo time per project in minutes (default: 5)')
    parser.add_argument('--walk-min', type=float, default=2.0,
                        help='Min walk time between projects in minutes (default: 2)')
    parser.add_argument('--walk-max', type=float, default=3.0,
                        help='Max walk time between projects in minutes (default: 3)')
    parser.add_argument('--no-time-limit', action='store_true',
                        help='Run each judge to full exhaustion, ignoring time')
    args = parser.parse_args()

    if args.reset:
        run_reset()
    else:
        run_simulation(
            time_budget=None if args.no_time_limit else args.time,
            demo_min=args.demo_min,
            demo_max=args.demo_max,
            walk_min=args.walk_min,
            walk_max=args.walk_max,
        )
