from datetime import datetime, timezone
from app import db

class DictionaryCategory(db.Model):
    __tablename__ = 'dictionary_categories'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(20), default='📁')  # 图标或emoji
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, index=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    items = db.relationship('DictionaryItem', backref='category', lazy='dynamic',
                          cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DictionaryCategory {self.code}: {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'icon': self.icon,
            'description': self.description,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'items_count': self.items.count()
        }

class DictionaryItem(db.Model):
    __tablename__ = 'dictionary_items'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('dictionary_categories.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('dictionary_items.id'), nullable=True, index=True)
    value = db.Column(db.String(100), nullable=False, index=True)
    label = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    extra_data = db.Column(db.Text)  # JSON格式存储扩展信息
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    parent = db.relationship('DictionaryItem', remote_side=[id], backref='children')

    __table_args__ = (
        db.UniqueConstraint('category_id', 'value', name='unique_category_value'),
        db.Index('idx_dict_item_category_sort', 'category_id', 'sort_order'),
    )

    def __repr__(self):
        return f'<DictionaryItem {self.category.code}: {self.label}>'

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'parent_id': self.parent_id,
            'value': self.value,
            'label': self.label,
            'description': self.description,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'extra_data': self.extra_data
        }

    @staticmethod
    def get_options(category_code, only_active=True):
        """获取指定分类的所有选项"""
        from . import DictionaryCategory
        category = DictionaryCategory.query.filter_by(code=category_code).first()

        if not category:
            return []

        query = DictionaryItem.query.filter_by(category_id=category.id)

        if only_active:
            query = query.filter_by(is_active=True)

        return query.order_by(DictionaryItem.sort_order, DictionaryItem.label).all()

    @staticmethod
    def get_options_dict(category_code, only_active=True):
        """获取选项的字典形式 {value: label}"""
        items = DictionaryItem.get_options(category_code, only_active)
        return {item.value: item.label for item in items}

    @staticmethod
    def init_default_data():
        """初始化默认字典数据"""
        from . import DictionaryCategory

        categories_data = {
            'school': {
                'name': '学校',
                'icon': '🏫',
                'description': '学校列表',
                'items': [
                    {'value': 'XX中学', 'label': 'XX中学'},
                    {'value': 'YY高中', 'label': 'YY高中'},
                    {'value': 'ZZ实验学校', 'label': 'ZZ实验学校'}
                ]
            },
            'grade': {
                'name': '年级',
                'icon': '📚',
                'description': '年级列表',
                'items': [
                    {'value': '高一', 'label': '高一'},
                    {'value': '高二', 'label': '高二'},
                    {'value': '高三', 'label': '高三'}
                ]
            },
            'major': {
                'name': '专业/方向',
                'icon': '🎓',
                'description': '学科方向或专业分类',
                'items': [
                    {'value': '文科', 'label': '文科'},
                    {'value': '理科', 'label': '理科'},
                    {'value': '艺术', 'label': '艺术'},
                    {'value': '体育', 'label': '体育'}
                ]
            },
            'class_name': {
                'name': '班级',
                'icon': '👥',
                'description': '班级列表（可按需添加）',
                'items': [
                    {'value': '高一(1)班', 'label': '高一(1)班'},
                    {'value': '高一(2)班', 'label': '高一(2)班'},
                    {'value': '高一(3)班', 'label': '高一(3)班'},
                    {'value': '高二(1)班', 'label': '高二(1)班'},
                    {'value': '高二(2)班', 'label': '高二(2)班'},
                    {'value': '高二(3)班', 'label': '高二(3)班'},
                    {'value': '高三(1)班', 'label': '高三(1)班'},
                    {'value': '高三(2)班', 'label': '高三(2)班'}
                ]
            }
        }

        for code, data in categories_data.items():
            category = DictionaryCategory.query.filter_by(code=code).first()

            if not category:
                category = DictionaryCategory(
                    code=code,
                    name=data['name'],
                    icon=data.get('icon', '📁'),
                    description=data.get('description', '')
                )
                db.session.add(category)
                db.session.flush()  # 获取ID

                for idx, item_data in enumerate(data['items']):
                    item = DictionaryItem(
                        category_id=category.id,
                        value=item_data['value'],
                        label=item_data['label'],
                        sort_order=idx
                    )
                    db.session.add(item)

        db.session.commit()
