from datetime import datetime

from gavel.models import db


class DevToolScore(db.Model):
    __tablename__ = 'dev_tool_score'
    __table_args__ = (
        db.UniqueConstraint('item_id', 'annotator_id', name='uq_dev_tool_score_item_annotator'),
    )

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    annotator_id = db.Column(db.Integer, db.ForeignKey('annotator.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    item = db.relationship('Item', back_populates='dev_tool_scores')
    annotator = db.relationship('Annotator', back_populates='dev_tool_scores')

    def __init__(self, annotator, item, score):
        self.annotator = annotator
        self.item = item
        self.score = score
