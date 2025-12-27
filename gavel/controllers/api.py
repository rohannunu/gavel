from gavel import app
from gavel.models import *
import gavel.utils as utils
from flask import Response, request
from sqlalchemy.sql import func

@app.route('/api/items.csv')
@app.route('/api/projects.csv')
@utils.requires_auth
def item_dump():
    path_filter = request.args.get('path')
    query = Item.query
    if path_filter:
        query = query.filter(Item.path == path_filter.lower())
    items = query.order_by(desc(Item.mu)).all()
    data = [['Mu', 'Sigma Squared', 'Path', 'Best Developer Tool', 'Name', 'Location', 'Description', 'Active']]
    data += [[
        str(item.mu),
        str(item.sigma_sq),
        item.path,
        item.best_dev_tool,
        item.name,
        item.location,
        item.description,
        item.active
    ] for item in items]
    return Response(utils.data_to_csv_string(data), mimetype='text/csv')


@app.route('/api/devtool.csv')
@utils.requires_auth
def dev_tool_dump():
    path_filter = request.args.get('path')
    query = db.session.query(
        Item,
        func.avg(DevToolScore.score).label('avg_score'),
        func.count(DevToolScore.id).label('score_count')
    ).outerjoin(DevToolScore).filter(Item.best_dev_tool == True)
    if path_filter:
        query = query.filter(Item.path == path_filter.lower())
    results = query.group_by(Item.id).order_by(desc('avg_score')).all()
    data = [['Avg Score', 'Score Count', 'Path', 'Mu', 'Name', 'Location', 'Description', 'Active']]
    data += [[
        str(avg_score) if avg_score is not None else '',
        str(score_count),
        item.path,
        str(item.mu),
        item.name,
        item.location,
        item.description,
        item.active
    ] for (item, avg_score, score_count) in results]
    return Response(utils.data_to_csv_string(data), mimetype='text/csv')

@app.route('/api/annotators.csv')
@app.route('/api/judges.csv')
@utils.requires_auth
def annotator_dump():
    annotators = Annotator.query.all()
    data = [['Name', 'Email', 'Description', 'Secret']]
    data += [[
        str(a.name),
        a.email,
        a.description,
        a.secret
    ] for a in annotators]
    return Response(utils.data_to_csv_string(data), mimetype='text/csv')

@app.route('/api/decisions.csv')
@utils.requires_auth
def decisions_dump():
    decisions = Decision.query.all()
    data = [['Annotator ID', 'Winner ID', 'Loser ID', 'Time']]
    data += [[
        str(d.annotator.id),
        str(d.winner.id),
        str(d.loser.id),
        str(d.time)
    ] for d in decisions]
    return Response(utils.data_to_csv_string(data), mimetype='text/csv')
