from gavel import app
from gavel.models import *
from gavel.constants import *
import gavel.settings as settings
import gavel.utils as utils
import gavel.stats as stats
from flask import (
    redirect,
    render_template,
    request,
    url_for,
)
import urllib.parse
import xlrd

ALLOWED_EXTENSIONS = set(['csv', 'xlsx', 'xls'])
ITEM_PATHS = ('general', 'pro')
PRIZE_JUDGE_TYPES = ('ui_ux', 'social_impact', 'creative', 'useless')
VALID_JUDGE_PREFERENCES = ITEM_PATHS + PRIZE_JUDGE_TYPES

@app.route('/admin/')
@utils.requires_auth
def admin():
    stats.check_send_telemetry()
    annotators = Annotator.query.order_by(Annotator.id).all()
    items = Item.query.order_by(Item.id).all()
    general_ranked = Item.query.filter(Item.path == 'general').order_by(desc(Item.mu)).all()
    pro_ranked = Item.query.filter(Item.path == 'pro').order_by(desc(Item.mu)).all()
    decisions = Decision.query.all()
    counts = {}
    item_counts = {}
    for d in decisions:
        a = d.annotator_id
        w = d.winner_id
        l = d.loser_id
        counts[a] = counts.get(a, 0) + 1
        item_counts[w] = item_counts.get(w, 0) + 1
        item_counts[l] = item_counts.get(l, 0) + 1
    viewed = {i.id: {a.id for a in i.viewed} for i in items}
    skipped = {}
    for a in annotators:
        for i in a.ignore:
            if a.id not in viewed[i.id]:
                skipped[i.id] = skipped.get(i.id, 0) + 1
    # settings
    setting_closed = Setting.value_of(SETTING_CLOSED) == SETTING_TRUE
    prize_ui_ux_items = Item.query.filter_by(prize_ui_ux=True, active=True).order_by(desc(Item.mu)).all()
    prize_social_impact_items = Item.query.filter_by(prize_social_impact=True, active=True).order_by(desc(Item.mu)).all()
    prize_creative_items = Item.query.filter_by(prize_creative=True, active=True).order_by(desc(Item.mu)).all()
    prize_useless_items = Item.query.filter_by(prize_useless=True, active=True).order_by(desc(Item.mu)).all()
    return render_template(
        'admin.html',
        annotators=annotators,
        counts=counts,
        item_counts=item_counts,
        skipped=skipped,
        items=items,
        general_ranked=general_ranked,
        pro_ranked=pro_ranked,
        votes=len(decisions),
        setting_closed=setting_closed,
        prize_ui_ux_items=prize_ui_ux_items,
        prize_social_impact_items=prize_social_impact_items,
        prize_creative_items=prize_creative_items,
        prize_useless_items=prize_useless_items,
    )

@app.route('/admin/item', methods=['POST'])
@utils.requires_auth
def item():
    action = request.form['action']
    if action == 'Submit':
        data = parse_upload_form()
        if data:
            default_path = (request.form.get('default_path') or 'general').lower()
            if default_path not in ITEM_PATHS:
                return utils.user_error('Default path "%s" is invalid (expected "general" or "pro")' % default_path)

            VALID_PRIZE_KEYS = {'ui_ux', 'social_impact', 'creative', 'useless'}

            def normalize_row(index, row):
                if len(row) < 3 or len(row) > 5:
                    raise ValueError('row %d has %d elements (expecting 3 to 5)' % (index + 1, len(row)))
                path_value = (row[3] if len(row) >= 4 else default_path)
                path_value = str(path_value).strip().lower() if path_value is not None else default_path
                if path_value not in ITEM_PATHS:
                    raise ValueError('row %d has invalid path "%s" (expected "general" or "pro")' % (index + 1, path_value))
                prizes = set()
                if len(row) >= 5 and row[4]:
                    for key in str(row[4]).split(';'):
                        key = key.strip().lower()
                        if key in VALID_PRIZE_KEYS:
                            prizes.add(key)
                return (row[0], row[1], row[2], path_value, prizes)

            try:
                normalized = [normalize_row(index, row) for index, row in enumerate(data)]
            except ValueError as e:
                return utils.user_error('Bad data: %s' % str(e))
            def tx():
                for row in normalized:
                    _item = Item(row[0], row[1], row[2], path=row[3], prizes=row[4])
                    db.session.add(_item)
                db.session.commit()
            with_retries(tx)
    elif action == 'Prioritize' or action == 'Cancel':
        item_id = request.form['item_id']
        target_state = action == 'Prioritize'
        def tx():
            Item.by_id(item_id).prioritized = target_state
            db.session.commit()
        with_retries(tx)
    elif action == 'Disable' or action == 'Enable':
        item_id = request.form['item_id']
        target_state = action == 'Enable'
        def tx():
            Item.by_id(item_id).active = target_state
            db.session.commit()
        with_retries(tx)
    elif action == 'Delete':
        item_id = request.form['item_id']
        try:
            def tx():
                db.session.execute(ignore_table.delete(ignore_table.c.item_id == item_id))
                Item.query.filter_by(id=item_id).delete()
                db.session.commit()
            with_retries(tx)
        except IntegrityError as e:
            if isinstance(e.orig, psycopg2.errors.ForeignKeyViolation):
                return utils.server_error("Projects can't be deleted once they have been voted on by a judge. You can use the 'disable' functionality instead, which has a similar effect, preventing the project from being shown to judges.")
            else:
                return utils.server_error(str(e))
    return redirect(url_for('admin'))


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_upload_form():
    f = request.files.get('file')
    data = []
    if f and allowed_file(f.filename):
        extension = str(f.filename.rsplit('.', 1)[1].lower())
        if extension == "xlsx" or extension == "xls":
            workbook = xlrd.open_workbook(file_contents=f.read())
            worksheet = workbook.sheet_by_index(0)
            data = list(utils.cast_row(worksheet.row_values(rx, 0, 5)) for rx in range(worksheet.nrows) if worksheet.row_len(rx) >= 3)
        elif extension == "csv":
            data = utils.data_from_csv_string(f.read().decode("utf-8"))
    else:
        csv = request.form['data']
        data = utils.data_from_csv_string(csv)
    cleaned = []
    for row in data:
        # drop trailing empty cells so row lengths match provided data
        while len(row) > 0 and (row[-1] is None or str(row[-1]).strip() == ''):
            row = row[:-1]
        cleaned.append(row)
    return cleaned


def _parse_bool(value, default=False):
    '''
    Normalize truthy/falsey strings or numbers into a boolean, falling back to
    the provided default if the value is empty or unknown.
    '''
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('1', 'true', 'yes', 'y', 'on'):
            return True
        if lowered in ('0', 'false', 'no', 'n', 'off'):
            return False
    try:
        intval = int(value)
        return bool(intval)
    except Exception:
        return default


@app.route('/admin/item_patch', methods=['POST'])
@utils.requires_auth
def item_patch():
    def tx():
        item = Item.by_id(request.form['item_id'])
        if not item:
            return utils.user_error('Item %s not found ' % request.form['item_id'])
        if 'location' in request.form:
            item.location = request.form['location']
        if 'name' in request.form:
            item.name = request.form['name']
        if 'description' in request.form:
            item.description = request.form['description']
        if 'path' in request.form:
            path_value = request.form['path'].lower()
            if path_value not in ITEM_PATHS:
                return utils.user_error('Path "%s" is invalid (expected "general" or "pro")' % path_value)
            item.path = path_value
        for field in ('prize_ui_ux', 'prize_social_impact', 'prize_creative', 'prize_useless'):
            if field in request.form:
                setattr(item, field, _parse_bool(request.form[field], getattr(item, field)))
        db.session.commit()
    with_retries(tx)
    return redirect(request.referrer or url_for('item_detail', item_id=item.id))

@app.route('/admin/annotator', methods=['POST'])
@utils.requires_auth
def annotator():
    action = request.form['action']
    if action == 'Submit':
        data = parse_upload_form()
        added = []
        if data:
            # validate data
            for index, row in enumerate(data):
                if len(row) < 3 or len(row) > 4:
                    return utils.user_error('Bad data: row %d has %d elements (expecting 3 or 4: name,email,description[,path]))' % (index + 1, len(row)))
            def tx():
                for row in data:
                    path_pref = None
                    if len(row) == 4 and row[3]:
                        normalized_path = row[3].strip().lower()
                        if normalized_path not in VALID_JUDGE_PREFERENCES:
                            return utils.user_error('Bad data: row %d has invalid preference "%s" (expected one of: %s)' % (index + 1, row[3], ', '.join(VALID_JUDGE_PREFERENCES)))
                        path_pref = normalized_path
                    annotator = Annotator(row[0], row[1], row[2], path_preference=path_pref)
                    added.append(annotator)
                    db.session.add(annotator)
                db.session.commit()
            with_retries(tx)
            try:
                email_invite_links(added)
            except Exception as e:
                return utils.server_error(str(e))
    elif action == 'Email':
        annotator_id = request.form['annotator_id']
        try:
            email_invite_links(Annotator.by_id(annotator_id))
        except Exception as e:
            return utils.server_error(str(e))
    elif action == 'Disable' or action == 'Enable':
        annotator_id = request.form['annotator_id']
        target_state = action == 'Enable'
        def tx():
            Annotator.by_id(annotator_id).active = target_state
            db.session.commit()
        with_retries(tx)
    elif action == 'Patch':
        annotator_id = request.form['annotator_id']
        path_pref = request.form.get('path_preference')
        if path_pref and path_pref not in VALID_JUDGE_PREFERENCES:
            return utils.user_error('Preference "%s" is invalid (expected one of: %s)' % (path_pref, ', '.join(VALID_JUDGE_PREFERENCES)))
        def tx():
            annotator = Annotator.by_id(annotator_id)
            if not annotator:
                return utils.user_error('Annotator %s not found ' % annotator_id)
            annotator.path_preference = path_pref if path_pref else None
            db.session.commit()
        with_retries(tx)
    elif action == 'Delete':
        annotator_id = request.form['annotator_id']
        try:
            def tx():
                db.session.execute(ignore_table.delete(ignore_table.c.annotator_id == annotator_id))
                Annotator.query.filter_by(id=annotator_id).delete()
                db.session.commit()
            with_retries(tx)
        except IntegrityError as e:
            if isinstance(e.orig, psycopg2.errors.ForeignKeyViolation):
                return utils.server_error("Judges can't be deleted once they have voted on a project. You can use the 'disable' functionality instead, which has a similar effect, locking out the judge and preventing them from voting on any other projects.")
            else:
                return utils.server_error(str(e))
    return redirect(url_for('admin'))

@app.route('/admin/setting', methods=['POST'])
@utils.requires_auth
def setting():
    key = request.form['key']
    if key == 'closed':
        action = request.form['action']
        new_value = SETTING_TRUE if action == 'Close' else SETTING_FALSE
        Setting.set(SETTING_CLOSED, new_value)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/item/<item_id>/')
@utils.requires_auth
def item_detail(item_id):
    item = Item.by_id(item_id)
    if not item:
        return utils.user_error('Item %s not found ' % item_id)
    else:
        assigned = Annotator.query.filter(Annotator.next == item).all()
        viewed_ids = {i.id for i in item.viewed}
        if viewed_ids:
            skipped = Annotator.query.filter(
                Annotator.ignore.contains(item) & ~Annotator.id.in_(viewed_ids)
            )
        else:
            skipped = Annotator.query.filter(Annotator.ignore.contains(item))
        return render_template(
            'admin_item.html',
            item=item,
            assigned=assigned,
            skipped=skipped
        )

@app.route('/admin/annotator/<annotator_id>/')
@utils.requires_auth
def annotator_detail(annotator_id):
    annotator = Annotator.by_id(annotator_id)
    if not annotator:
        return utils.user_error('Annotator %s not found ' % annotator_id)
    else:
        seen = Item.query.filter(Item.viewed.contains(annotator)).all()
        ignored_ids = {i.id for i in annotator.ignore}
        if ignored_ids:
            skipped = Item.query.filter(
                Item.id.in_(ignored_ids) & ~Item.viewed.contains(annotator)
            )
        else:
            skipped = []
        return render_template(
            'admin_annotator.html',
            annotator=annotator,
            login_link=annotator_link(annotator),
            seen=seen,
            skipped=skipped
        )

def annotator_link(annotator):
        return url_for('login', secret=annotator.secret, _external=True)

def email_invite_links(annotators):
    if settings.DISABLE_EMAIL or annotators is None:
        return
    if not isinstance(annotators, list):
        annotators = [annotators]

    emails = []
    for annotator in annotators:
        link = annotator_link(annotator)
        raw_body = settings.EMAIL_BODY.format(name=annotator.name, link=link)
        body = '\n\n'.join(utils.get_paragraphs(raw_body))
        emails.append((annotator.email, settings.EMAIL_SUBJECT, body))

    if settings.USE_SENDGRID and settings.SENDGRID_API_KEY != None:
        utils.send_sendgrid_emails(emails)
    else:
        utils.send_emails.delay(emails)
