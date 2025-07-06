from flask import Blueprint, request, jsonify
from .models import db, User, Group, Note, Meetup, ChatMessage
from datetime import datetime
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import secrets
import string

api_bp = Blueprint('api', __name__)

def generate_join_code(length=6):
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(length))
        if not Group.query.filter_by(join_code=code).first(): return code

@api_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(force=True)
    if User.query.filter_by(username=data['username']).first(): return jsonify({'message': 'User already exists'}), 409
    user = User(username=data['username'], email=data['email']); user.set_password(data['password'])
    db.session.add(user); db.session.commit()
    return jsonify({'message': 'User registered successfully'}), 201

@api_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(force=True)
    user = User.query.filter_by(username=data['username']).first()
    if user and user.check_password(data['password']):
        return jsonify(access_token=create_access_token(identity=str(user.id)), user_id=user.id), 200
    return jsonify({'message': 'Invalid credentials'}), 401

@api_bp.route('/groups', methods=['GET'])
@jwt_required()
def get_groups():
    user = User.query.get(get_jwt_identity())
    return jsonify([{'id': g.id, 'name': g.name, 'course_code': g.course_code, 'member_count': len(g.members), 'join_code': g.join_code} for g in user.joined_groups])

@api_bp.route('/groups/<int:group_id>', methods=['GET'])
@jwt_required()
def get_group_details(group_id):
    group = Group.query.get_or_404(group_id)
    return jsonify({'id': group.id, 'name': group.name})


@api_bp.route('/groups', methods=['POST'])
@jwt_required()
def create_group():
    user_id = get_jwt_identity()
    data = request.get_json(force=True)
    new_group = Group(name=data.get('name'), course_code=data.get('course_code', ''), description=data.get('description', ''), join_code=generate_join_code(), creator_id=user_id)
    new_group.members.append(User.query.get(user_id))
    db.session.add(new_group); db.session.commit()
    return jsonify({'message': 'Group created', 'group_id': new_group.id}), 201

@api_bp.route('/groups/join', methods=['POST'])
@jwt_required()
def join_group_by_code():
    user = User.query.get(get_jwt_identity())
    data = request.get_json(force=True)
    group = Group.query.filter_by(join_code=data.get('join_code', '').upper()).first()
    if not group: return jsonify({'message': 'Invalid join code'}), 404
    if user in group.members: return jsonify({'message': 'You are already a member'}), 409
    group.members.append(user); db.session.commit()
    return jsonify({"message": f"Successfully joined group: {group.name}"}), 200

@api_bp.route('/groups/<int:group_id>/notes', methods=['GET'])
@jwt_required()
def get_notes_for_group(group_id):
    notes = Note.query.filter_by(group_id=group_id).order_by(Note.created_at.desc()).all()
    return jsonify([{'id': n.id, 'title': n.title, 'content': n.content, 'uploader': n.uploader.username, 'created_at': n.created_at.isoformat()} for n in notes])

@api_bp.route('/groups/<int:group_id>/notes', methods=['POST'])
@jwt_required()
def add_note_to_group(group_id):
    data = request.get_json(force=True)
    new_note = Note(title=data['title'], content=data['content'], uploader_id=get_jwt_identity(), group_id=group_id)
    db.session.add(new_note); db.session.commit()
    return jsonify({'id': new_note.id, 'title': new_note.title, 'content': new_note.content, 'uploader': new_note.uploader.username, 'created_at': new_note.created_at.isoformat()}), 201

@api_bp.route('/groups/<int:group_id>/meetups', methods=['GET'])
@jwt_required()
def get_meetups(group_id):
    meetups = Meetup.query.filter_by(group_id=group_id).order_by(Meetup.scheduled_time.asc()).all()
    return jsonify([{'id': m.id, 'topic': m.topic, 'description': m.description, 'link': m.meetup_link, 'time': m.scheduled_time.isoformat(), 'creator': m.creator.username} for m in meetups])

@api_bp.route('/groups/<int:group_id>/meetups', methods=['POST'])
@jwt_required()
def schedule_meetup(group_id):
    data = request.get_json(force=True)
    new_meetup = Meetup(
        group_id=group_id,
        creator_id=get_jwt_identity(),
        topic=data['topic'],
        description=data.get('description', ''),
        meetup_link=data.get('link', ''),
        scheduled_time=datetime.fromisoformat(data['time'])
    )
    db.session.add(new_meetup); db.session.commit()
    return jsonify({'message': 'Meetup scheduled!'}), 201

@api_bp.route('/groups/<int:group_id>/chat', methods=['GET'])
@jwt_required()
def get_chat_messages(group_id):
    messages = ChatMessage.query.filter_by(group_id=group_id).order_by(ChatMessage.timestamp.asc()).limit(50).all()
    return jsonify([{'id': msg.id, 'text': msg.text, 'timestamp': msg.timestamp.isoformat(), 'author': msg.author.username} for msg in messages])

@api_bp.route('/groups/<int:group_id>/chat', methods=['POST'])
@jwt_required()
def post_chat_message(group_id):
    data = request.get_json(force=True)
    new_msg = ChatMessage(
        group_id=group_id,
        user_id=get_jwt_identity(),
        text=data['text']
    )
    db.session.add(new_msg); db.session.commit()
    return jsonify({'id': new_msg.id, 'text': new_msg.text, 'timestamp': new_msg.timestamp.isoformat(), 'author': new_msg.author.username}), 201


@api_bp.route('/groups/<int:group_id>/leave', methods=['POST'])
@jwt_required()
def leave_group(group_id):
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    group = Group.query.get(group_id)

    if not group:
        return jsonify({'message': 'Group not found'}), 404

    if user not in group.members:
        return jsonify({'message': 'You are not a member of this group'}), 400

    group.members.remove(user)
    
    if not group.members:
        db.session.delete(group)
        message = f"You have left the group '{group.name}', and it has been deleted as you were the last member."
    else:
        message = f"You have successfully left the group '{group.name}'."

    db.session.commit()
    return jsonify({'message': message}), 200