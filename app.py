from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFProtect
import sqlite3
import json
from datetime import datetime
import os
from flask import g
import logging
from openai import OpenAI
from sessions import SessionManager
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev'
csrf = CSRFProtect(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Enable CSRF protection globally
csrf.init_app(app)

# Database configuration
app.config['DATABASE'] = 'greenpill.db'
api_key = os.getenv("SECRET_KEY")
# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# Temporary development settings - ADD THIS AT THE TOP after imports
DEVELOPMENT = True  # Set this to False when deploying

if DEVELOPMENT:
    # Create a development user session
    @app.before_request
    def dev_login():
        if not current_user.is_authenticated:
            # Create a mock user
            dev_user = User(1, 'developer')
            login_user(dev_user)

# Modify the login_required decorator - ADD THIS BEFORE your routes
def dev_login_required(f):
    if DEVELOPMENT:
        return f
    return login_required(f)

def get_db():
    """Connect to the database."""
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = sqlite3.connect(app.config['DATABASE'])
        g.sqlite_db.row_factory = sqlite3.Row
    return g.sqlite_db

@app.teardown_appcontext
def close_db(error):
    """Close the database at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()

def init_db():
    """Initialize the database."""
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            assistant_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if user:
        return User(user['id'], user['username'])
    return None

@app.route('/')
def home():
    # Fetch some featured remedies and resources for the home page
    db = get_db()
    featured_remedies = db.execute('''
        SELECT r.*, u.username 
        FROM user_remedies r 
        JOIN users u ON r.user_id = u.id 
        ORDER BY r.created_at DESC LIMIT 3
    ''').fetchall()
    return render_template('home.html', 
                         featured_remedies=featured_remedies,
                         current_user=current_user)

@app.route('/submit_remedy', methods=['POST'])
@dev_login_required
def submit_remedy():
    if request.method == 'POST':
        name = request.form.get('name')
        remedy_details = request.form.get('remedy_details')
        
        if not name or not remedy_details:
            flash('Please fill in all fields', 'error')
            return redirect(url_for('home'))
        
        try:
            db = get_db()
            db.execute('''
                INSERT INTO user_remedies (user_id, name, remedy_details, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (current_user.id, name, remedy_details))
            db.commit()
            flash('Thank you for sharing your remedy!', 'success')
        except Exception as e:
            flash('An error occurred while submitting your remedy.', 'error')
            print(e)
        
        return redirect(url_for('home'))

@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        if not all([name, email, message]):
            flash('Please fill in all fields', 'error')
            return redirect(url_for('home'))
        
        try:
            db = get_db()
            db.execute('''
                INSERT INTO contact_messages (name, email, message, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (name, email, message))
            db.commit()
            flash('Thank you for your message! We will get back to you soon.', 'success')
        except Exception as e:
            flash('An error occurred while sending your message.', 'error')
            print(e)
        
        return redirect(url_for('home'))

@app.route('/get_sessions')
@dev_login_required
def get_sessions():
    db = get_db()
    sessions = db.execute('''
        SELECT id, title, created_at 
        FROM chat_sessions 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (current_user.id,)).fetchall()
    
    return jsonify({
        'sessions': [{
            'id': row['id'],
            'title': row['title'],
            'created_at': row['created_at']
        } for row in sessions]
    })

@app.route('/get_session_messages/<int:session_id>')
@dev_login_required
def get_session_messages(session_id):
    db = get_db()
    # Verify session belongs to current user
    session = db.execute('''
        SELECT id FROM chat_sessions 
        WHERE id = ? AND user_id = ?
    ''', (session_id, current_user.id)).fetchone()
    
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    messages = db.execute('''
        SELECT content, is_bot, created_at 
        FROM chat_messages 
        WHERE session_id = ? 
        ORDER BY created_at
    ''', (session_id,)).fetchall()
    
    return jsonify({
        'messages': [{
            'content': row['content'],
            'isBot': bool(row['is_bot']),
            'timestamp': row['created_at']
        } for row in messages]
    })

# Initialize session manager
session_manager = SessionManager(app)

@app.route('/chat')
@dev_login_required
def chat():
    session_id = request.args.get('session_id')
    if not session_id:
        # Create new session
        session_id = session_manager.create_session(current_user.id)
        return redirect(url_for('chat', session_id=session_id))
    
    session = session_manager.get_session(session_id)
    if not session or session.user_id != current_user.id:
        return redirect(url_for('chat'))
    
    # Get all user sessions for the sidebar
    user_sessions = session_manager.get_user_sessions(current_user.id)
    
    return render_template('chat.html', 
                         session_id=session_id,
                         current_session=session,
                         sessions=user_sessions)

@app.route('/chat_message', methods=['POST'])
@dev_login_required
def handle_chat_message():
    data = request.get_json()
    message = data.get('message')
    session_id = data.get('session_id')
    
    if not message or not session_id:
        return jsonify({'error': 'Invalid request'}), 400
    
    # Add user message
    if not session_manager.add_message(session_id, message, 'user'):
        return jsonify({'error': 'Failed to save message'}), 500
    
    try:
        # Get AI response
        response = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=[{"role": "user", "content": message}]
        )
        ai_response = response.choices[0].message.content
        
        # Add AI message
        session_manager.add_message(session_id, ai_response, 'assistant')
        
        return jsonify({
            'response': ai_response,
            'session_id': session_id
        })
    except Exception as e:
        logger.error(f"Error in chat_message: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        logger.debug(f"Form data received: {request.form}")
        logger.debug(f"CSRF token present: {'csrf_token' in request.form}")
        
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        age = request.form.get('age')
        gender = request.form.get('gender')
        allergies = request.form.get('allergies')
        health_condition = request.form.get('health_condition')
        
        db = get_db()
        error = None

        if not username:
            error = 'Username is required.'
        elif not email:
            error = 'Email is required.'
        elif not password:
            error = 'Password is required.'

        if error is None:
            try:
                db.execute(
                    'INSERT INTO users (username, email, password, age, gender, allergies, health_condition) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (username, email, generate_password_hash(password), age, gender, allergies, health_condition)
                )
                db.commit()
                flash('Registration successful! Please login.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                error = f'User {username} or email {email} is already registered.'
        
        flash(error)
        print("Error:", error)  # Debug print

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        error = None
        user = db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user is None:
            error = 'Please register first.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'

        if error is None:
            login_user(User(user['id'], user['username']))
            flash('You were successfully logged in')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))

        flash(error)

    return render_template('login.html')

@app.route('/logout')
@dev_login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))

# CLI command to initialize the database
@app.cli.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    print('Initialized the database.')

@app.route('/test_csrf', methods=['POST'])
def test_csrf():
    return "CSRF token is working!"

@app.route('/chat/<int:session_id>')
@dev_login_required
def chat_session(session_id):
    db = get_db()
    session = db.execute('''
        SELECT * FROM chat_sessions 
        WHERE id = ? AND user_id = ?
    ''', (session_id, current_user.id)).fetchone()
    
    if not session:
        return redirect(url_for('chat'))
        
    # Load conversation history from JSON
    try:
        with open(f'conversation_{session_id}.json', 'r') as f:
            conversation = json.load(f)
    except FileNotFoundError:
        conversation = {"messages": []}
    
    return render_template('chat.html', 
                         session_id=session_id,
                         conversation=conversation)

@app.route('/delete_session/<session_id>', methods=['POST'])
@dev_login_required
def delete_session(session_id):
    if session_manager.delete_session(session_id, current_user.id):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to delete session'}), 500

if __name__ == '__main__':
    init_db()  # Initialize the database
    app.run(debug=True) 