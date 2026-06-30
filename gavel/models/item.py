from gavel.models import db
import gavel.crowd_bt as crowd_bt
from sqlalchemy.orm.exc import NoResultFound

view_table = db.Table('view',
    db.Column('item_id', db.Integer, db.ForeignKey('item.id')),
    db.Column('annotator_id', db.Integer, db.ForeignKey('annotator.id'))
)

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    name = db.Column(db.Text, nullable=False)
    location = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    viewed = db.relationship('Annotator', secondary=view_table)
    prioritized = db.Column(db.Boolean, default=False, nullable=False)
    path = db.Column(db.Enum('general', 'pro', name='item_path'), default='general', nullable=False)
    prize_ui_ux = db.Column(db.Boolean, default=False, nullable=False)
    prize_social_impact = db.Column(db.Boolean, default=False, nullable=False)
    prize_creative = db.Column(db.Boolean, default=False, nullable=False)
    prize_useless = db.Column(db.Boolean, default=False, nullable=False)

    mu = db.Column(db.Float)
    sigma_sq = db.Column(db.Float)

    @property
    def prizes(self):
        mapping = {
            'Best UI/UX Design': self.prize_ui_ux,
            'Best Social Impact': self.prize_social_impact,
            'Most Creative': self.prize_creative,
            'Most Useless': self.prize_useless,
        }
        return [name for name, eligible in mapping.items() if eligible]

    def __init__(self, name, location, description, path='general', prizes=None):
        self.name = name
        self.location = location
        self.description = description
        self.mu = crowd_bt.MU_PRIOR
        self.sigma_sq = crowd_bt.SIGMA_SQ_PRIOR
        self.path = (path or 'general').lower()
        if prizes:
            self.prize_ui_ux = 'ui_ux' in prizes
            self.prize_social_impact = 'social_impact' in prizes
            self.prize_creative = 'creative' in prizes
            self.prize_useless = 'useless' in prizes

    @classmethod
    def by_id(cls, uid):
        if uid is None:
            return None
        try:
            item = cls.query.get(uid)
        except NoResultFound:
            item = None
        return item
