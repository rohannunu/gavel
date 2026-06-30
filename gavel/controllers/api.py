from gavel import app
from gavel.models import *
import gavel.utils as utils
from flask import Response, request

@app.route('/api/items.csv')
@app.route('/api/projects.csv')
@utils.requires_auth
def item_dump():
    path_filter = request.args.get('path')
    query = Item.query
    if path_filter:
        query = query.filter(Item.path == path_filter.lower())
    items = query.order_by(desc(Item.mu)).all()
    data = [['Mu', 'Sigma Squared', 'Path', 'Prize UI/UX', 'Prize Social Impact', 'Prize Creative', 'Prize Useless', 'Name', 'Location', 'Description', 'Active']]
    data += [[
        str(item.mu),
        str(item.sigma_sq),
        item.path,
        item.prize_ui_ux,
        item.prize_social_impact,
        item.prize_creative,
        item.prize_useless,
        item.name,
        item.location,
        item.description,
        item.active
    ] for item in items]
    return Response(utils.data_to_csv_string(data), mimetype='text/csv')


@app.route('/api/prizes.csv')
@utils.requires_auth
def prizes_dump():
    path_filter = request.args.get('path')
    query = Item.query.filter(
        (Item.prize_ui_ux == True) |
        (Item.prize_social_impact == True) |
        (Item.prize_creative == True) |
        (Item.prize_useless == True)
    )
    if path_filter:
        query = query.filter(Item.path == path_filter.lower())
    items = query.order_by(desc(Item.mu)).all()
    data = [['Mu', 'Path', 'Prize UI/UX', 'Prize Social Impact', 'Prize Creative', 'Prize Useless', 'Name', 'Location', 'Description', 'Active']]
    data += [[
        str(item.mu),
        item.path,
        item.prize_ui_ux,
        item.prize_social_impact,
        item.prize_creative,
        item.prize_useless,
        item.name,
        item.location,
        item.description,
        item.active
    ] for item in items]
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
