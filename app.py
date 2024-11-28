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

# Configure logging
logging.basicConfig(level=logging.DEBUG)
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
DATABASE = 'greenpill.db'

def get_db():
    """Connect to the database."""
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = sqlite3.connect(DATABASE)
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
            assistant_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
@login_required
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
@login_required
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
@login_required
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

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

def create_assistant():
    try:
        assistant = client.beta.assistants.create(
            name="Sina",
            instructions="You are Sina, a natural healing assistant. You help users with natural remedies and holistic health advice.",
            model="gpt-4-1106-preview"
        )
        logger.info(f"Created new assistant with ID: {assistant.id}")
        return assistant.id
    except Exception as e:
        logger.error(f"Error creating assistant: {str(e)}")
        raise

def open_new_session():
    assistant_id = create_assistant()
    conn = sqlite3.connect('chat.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (assistant_id) VALUES (?)", (assistant_id,))
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id, assistant_id

@app.route('/chat_message', methods=['POST'])
def handle_chat_message():
    data = request.get_json()
    message = data.get('message')

    # Open a new session if needed
    session_id, assistant_id = open_new_session()

    try:
        # Create a thread
        thread = client.beta.threads.create()
        
        # Add message to thread
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message
        )
        
        # Run the assistant
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )
        
        # Wait for completion
        while run.status in ["queued", "in_progress"]:
            run = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
        
        # Get response
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        ai_response = messages.data[0].content[0].text.value

        # Save conversation to JSON
        conversation = {
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": message},
                {"role": "assistant", "content": ai_response}
            ]
        }
        with open(f'conversation_{session_id}.json', 'w') as f:
            json.dump(conversation, f)

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        ai_response = "I'm sorry, I couldn't process your request."

    return jsonify({'response': ai_response})

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
            error = 'Incorrect username.'
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
@login_required
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

if __name__ == '__main__':
    init_db()  # Initialize the database
    app.run(debug=True) 