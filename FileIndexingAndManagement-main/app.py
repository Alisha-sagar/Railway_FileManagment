from flask import (
    Flask, render_template, request, redirect, jsonify,
    send_file, session, flash, url_for, get_flashed_messages
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, BadSignature
from functools import wraps
import pandas as pd
import os
import json
from datetime import datetime
from sqlalchemy import or_, text

from models import db, User, File

app = Flask(__name__)
app.secret_key = 'yK@p1A$9vTz3!mB2#qW8^LrXeCfHsJ0u'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Project2004@localhost/file_management'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
serializer = URLSafeTimedSerializer(app.secret_key)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ------------------- Middleware -------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            flash('Login required.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ------------------- Auth Routes -------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed = generate_password_hash(password)

        if User.query.filter_by(username=username).first():
            flash('Username already exists. Try a different one.', 'signup')
        else:
            new_user = User(username=username, email=email, password=hashed)
            db.session.add(new_user)
            db.session.commit()
            flash('Signup successful! You can now login.', 'signup')
    categories = [cat for cat, msg in get_flashed_messages(with_categories=True)]
    return render_template('login.html', flash_categories=json.dumps(categories))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user'] = username
            session['user_id'] = user.id
            flash('Login successful!', 'login')
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials. Try again.', 'login')
    categories = [cat for cat, msg in get_flashed_messages(with_categories=True)]
    return render_template('login.html', flash_categories=json.dumps(categories))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username']
        user = User.query.filter_by(username=username).first()
        if not user:
            flash("Username doesn't exist", 'danger')
            return redirect(url_for('forgot_password'))
        token = serializer.dumps(username, salt='reset-password')
        reset_url = url_for('reset_password', token=token, _external=True)
        print(f"[RESET LINK] {reset_url}")
        flash("Reset link sent! Check console (dev mode).", 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        username = serializer.loads(token, salt='reset-password', max_age=3600)
    except BadSignature:
        flash("Invalid or expired link", 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_pass = request.form['password']
        hashed = generate_password_hash(new_pass)
        user = User.query.filter_by(username=username).first()
        if user:
            user.password = hashed
            db.session.commit()
            flash("Password updated! Please log in.", 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', username=username)

# ------------------- Main Routes -------------------
@app.route('/')
@login_required
def home():
    return render_template('add_file.html', username=session.get('user'))

@app.route('/search')
@login_required
def search_page():
    return render_template('search_file.html')

@app.route('/add', methods=['POST'])
@login_required
def add_file():
    data = request.form
    existing = File.query.filter_by(file_code=data['file_code']).first()
    if existing:
        flash("Duplicate file code.", "danger")
    else:
        new_file = File(
            filename=data['filename'],
            file_code=data['file_code'],
            tags=data.get('tags', ''),
            cabinet=data.get('cabinet', ''),
            shelf=data.get('shelf', ''),
            box=data.get('box', ''),
            filepath='',
            user_id=session['user_id']
        )
        db.session.add(new_file)
        db.session.commit()
        flash("File added successfully!", "success")
    return redirect(url_for('home'))

@app.route('/edit_file/<file_code>', methods=['GET', 'POST'])
@login_required
def edit_file(file_code):
    file = File.query.filter_by(file_code=file_code).first()
    if not file:
        flash("File not found.", "danger")
        return redirect(url_for('search_page'))

    if request.method == 'POST':
        file.filename = request.form['filename']
        file.tags = request.form['tags']
        file.cabinet = request.form['cabinet']
        file.shelf = request.form['shelf']
        file.box = request.form['box']
        db.session.commit()
        flash("File updated successfully!", "success")
        return redirect(url_for('search_page'))

    return render_template('edit_file.html', file=file)

@app.route('/api/search')
@login_required
def search():
    query = request.args.get('q', '').lower()
    results = File.query.filter(
        or_(
            File.filename.ilike(f'%{query}%'),
            File.file_code.ilike(f'%{query}%')
        )
    ).all()
    return jsonify([
        {
            'filename': f.filename,
            'file_code': f.file_code,
            'tags': f.tags,
            'location': f"{f.cabinet} > {f.shelf} > {f.box}"
        } for f in results
    ])

@app.route('/export')
@login_required
def export_excel():
    files = File.query.all()
    df = pd.DataFrame([{
        'filename': f.filename,
        'file_code': f.file_code,
        'tags': f.tags,
        'cabinet': f.cabinet,
        'shelf': f.shelf,
        'box': f.box
    } for f in files])
    path = os.path.join(app.config['UPLOAD_FOLDER'], 'exported_files.xlsx')
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)

@app.route('/import', methods=['POST'])
@login_required
def import_excel():
    file = request.files['excel_file']
    if file and file.filename.endswith('.xlsx'):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(filepath)
        df = pd.read_excel(filepath)
        for _, row in df.iterrows():
            if not File.query.filter_by(file_code=row['file_code']).first():
                new_file = File(
                    filename=row['filename'],
                    file_code=row['file_code'],
                    tags=row.get('tags', ''),
                    cabinet=row.get('cabinet', ''),
                    shelf=row.get('shelf', ''),
                    box=row.get('box', ''),
                    filepath='',
                    user_id=session['user_id']
                )
                db.session.add(new_file)
        db.session.commit()
        flash("Excel data imported!", "success")
    else:
        flash("Invalid file type. Please upload .xlsx", "danger")
    return redirect(url_for('home'))

# ------------------- Recycle Bin -------------------
@app.route('/delete_file', methods=['POST'])
@login_required
def delete_file():
    data = request.get_json()
    file = None
    if 'file_code' in data:
        file = File.query.filter_by(file_code=data['file_code']).first()
    elif 'filename' in data:
        file = File.query.filter_by(filename=data['filename']).first()

    if not file:
        return jsonify({'error': 'File not found'}), 404

    db.session.execute(text("""
        INSERT INTO recycle_bin (file_code, filename, filepath, user_id)
        VALUES (:code, :name, :path, :user_id)
    """), {
        'code': file.file_code,
        'name': file.filename,
        'path': file.filepath,
        'user_id': file.user_id
    })

    db.session.delete(file)
    db.session.commit()
    return jsonify({'message': f'File "{file.filename}" moved to Recycle Bin'}), 200

@app.route('/recycle_bin')
@login_required
def view_recycle_bin():
    result = db.session.execute(text("""
        SELECT id, file_code, filename, filepath, deleted_at
        FROM recycle_bin
        WHERE user_id = :uid
        ORDER BY deleted_at DESC
    """), {'uid': session['user_id']})

    files = [dict(row._mapping) for row in result]
    return jsonify(files), 200

@app.route('/restore_file', methods=['POST'])
@login_required
def restore_file():
    data = request.get_json()
    file_code = data.get('file_code')

    result = db.session.execute(text("""
        SELECT * FROM recycle_bin
        WHERE file_code = :code AND user_id = :uid
    """), {'code': file_code, 'uid': session['user_id']}).first()

    if not result:
        return jsonify({'error': 'File not found in Recycle Bin'}), 404

    new_file = File(
        file_code=result.file_code,
        filename=result.filename,
        filepath=result.filepath,
        user_id=session['user_id']
    )
    db.session.add(new_file)

    db.session.execute(text("DELETE FROM recycle_bin WHERE id = :id"), {'id': result.id})
    db.session.commit()

    return jsonify({'message': f'File "{result.filename}" restored successfully'}), 200

@app.route('/empty_recycle_bin', methods=['DELETE'])
@login_required
def empty_recycle_bin():
    db.session.execute(text("""
        DELETE FROM recycle_bin
        WHERE user_id = :uid
    """), {'uid': session['user_id']})
    db.session.commit()
    return jsonify({'message': 'Recycle Bin emptied successfully'}), 200

# ------------------- Init -------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
